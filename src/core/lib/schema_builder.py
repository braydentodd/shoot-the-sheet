"""
Shoot the Sheet - Schema Builder

Idempotent schema synchronization driven entirely by the central config dicts.
The generator is purely additive: it CREATEs missing tables and ADDs
missing columns, but never drops or alters existing structures. Schema
changes that require destructive migrations must be performed deliberately
outside this module.
"""

import logging
from typing import Any, Dict, List, Tuple

from src.core.definitions.db_columns import DB_COLUMNS
from src.core.definitions.schema import SEQUENCES, TABLES
from src.core.lib.postgres import get_db_connection, quote_col

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column-set assembly
# ---------------------------------------------------------------------------


def _column_in_table(col_meta: Any, table_name: str) -> bool:
    """Whether a DB_COLUMNS entry contributes to *table_name*.

    Supports the ``'all'`` wildcard, which means the column belongs to
    every table.  Staging tables must be declared explicitly in each
    column's ``tables`` list.
    """
    tables = col_meta.get("tables", [])
    if isinstance(tables, str):
        tables = [tables]
    return table_name in tables or "all" in tables


def _data_columns_for_table(table_name: str) -> List[Tuple[str, Any]]:
    """Return ``[(col_name, col_meta), ...]`` for every matching DB_COLUMNS entry."""
    return [
        (name, meta)
        for name, meta in DB_COLUMNS.items()
        if _column_in_table(meta, table_name)
    ]


def _data_columns_for_tables(
    table_names: List[str],
) -> List[Tuple[str, Any]]:
    """Return matching DB columns across several tables without duplicates."""
    ordered: List[Tuple[str, Any]] = []
    seen = set()
    for table_name in table_names:
        for name, meta in _data_columns_for_table(table_name):
            if name in seen:
                continue
            seen.add(name)
            ordered.append((name, meta))
    return ordered


# ---------------------------------------------------------------------------
# Single-column DDL fragments
# ---------------------------------------------------------------------------


def _format_default(default: Any, pg_type: str) -> str:
    """Render a default-value clause."""
    if default is None:
        return ""
    if isinstance(default, bool):
        return f"DEFAULT {'TRUE' if default else 'FALSE'}"
    return f"DEFAULT {default}"


def _column_ddl(name: str, col_meta: Any) -> str:
    """Render a single ``CREATE TABLE`` column fragment."""
    parts = [quote_col(name), col_meta["type"]]
    if not col_meta.get("nullable", True):
        parts.append("NOT NULL")
    default = _format_default(col_meta.get("default"), col_meta["type"])
    if default:
        parts.append(default)
    return " ".join(parts)


def _foreign_key_ddl(fk: Dict[str, Any]) -> str:
    """Render a ``FOREIGN KEY`` clause."""
    target = f"{fk['ref_schema']}.{fk['ref_table']}"
    return (
        f"FOREIGN KEY ({', '.join(quote_col(c) for c in fk['columns'])}) "
        f"REFERENCES {target}"
        f"({', '.join(quote_col(c) for c in fk['ref_columns'])}) "
        f"ON UPDATE {fk['on_update']} ON DELETE {fk['on_delete']}"
    )


# ---------------------------------------------------------------------------
# Existence helpers
# ---------------------------------------------------------------------------


def _table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return cur.fetchone() is not None


def _existing_columns(cur, schema: str, table: str) -> set:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return {row[0] for row in cur.fetchall()}


def _existing_unique_column_sets(cur, schema: str, table: str) -> set:
    cur.execute(
        """
        SELECT tc.constraint_name, array_agg(kcu.column_name ORDER BY kcu.ordinal_position)
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
           AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        GROUP BY tc.constraint_name
        """,
        (schema, table),
    )
    return {tuple(row[1]) for row in cur.fetchall()}


def _insert_row(
    cur,
    schema_name: str,
    table_name: str,
    values: Dict[str, Any],
    conflict_columns: List[str],
) -> None:
    """Insert a row if missing using only the provided table metadata."""
    if not values:
        return

    columns = list(values.keys())
    column_sql = ", ".join(quote_col(col) for col in columns)
    values_sql = ", ".join(["%s"] * len(columns))
    params = [values[col] for col in columns]

    if conflict_columns:
        conflict_sql = ", ".join(quote_col(col) for col in conflict_columns)
        on_conflict = f"ON CONFLICT ({conflict_sql}) DO NOTHING"
    else:
        on_conflict = "ON CONFLICT DO NOTHING"

    cur.execute(
        f"INSERT INTO {schema_name}.{table_name} ({column_sql}) "
        f"VALUES ({values_sql}) {on_conflict}",
        params,
    )


# ---------------------------------------------------------------------------
# Core Schema Build Engine
# ---------------------------------------------------------------------------


def _get_expected_columns(
    table_name: str,
    meta: Dict[str, Any],
) -> List[Tuple[str, Any]]:
    """Return the complete ordered set of (column_name, column_meta) for a table.

    Centralises column resolution so that both ``_create_table`` and
    ``_sync_table`` derive their column lists from a single source of truth.
    """
    expected: List[Tuple[str, Any]] = []
    seen: set = set()

    for col in meta.get("primary_key") or []:
        expected.append((col, DB_COLUMNS[col]))
        seen.add(col)

    for fk in meta.get("foreign_keys") or []:
        for col in fk["columns"]:
            if col not in seen:
                expected.append((col, DB_COLUMNS[col]))
                seen.add(col)

    for name, m in _data_columns_for_table(table_name):
        if name not in seen:
            expected.append((name, m))
            seen.add(name)

    return expected


def _create_table(
    cur,
    schema_name: str,
    table_name: str,
    meta: Dict[str, Any],
) -> int:
    """Unified CREATE TABLE builder driven strictly by registry config."""
    fragments: List[str] = []
    pk_cols = set(meta.get("primary_key") or [])

    for col_name, col_meta in _get_expected_columns(table_name, meta):
        fragments.append(_column_ddl(col_name, col_meta))

    # Column-level UNIQUE constraints (from DB_COLUMNS 'unique' flag)
    for name, m in _data_columns_for_table(table_name):
        if m.get("unique") and name not in pk_cols:
            fragments.append(f"UNIQUE ({quote_col(name)})")

    # Table-level constraints: PK, FK, multi-column UNIQUE
    if pk_cols:
        pk_str = ", ".join(quote_col(c) for c in pk_cols)
        fragments.append(f"PRIMARY KEY ({pk_str})")

    for fk in meta.get("foreign_keys") or []:
        fragments.append(_foreign_key_ddl(fk))

    for uc in meta.get("unique_constraints") or []:
        uc_cols = ", ".join(quote_col(c) for c in uc)
        fragments.append(f"UNIQUE ({uc_cols})")

    cur.execute(
        f"CREATE TABLE {schema_name}.{table_name} (\n  "
        + ",\n  ".join(fragments)
        + "\n)"
    )

    # Indexes — prefix with schema to avoid cross-schema name collisions
    for idx in meta.get("indexes") or []:
        idx_name = f"idx_{schema_name}_{table_name}_{idx['name']}"
        cols = ", ".join(quote_col(c) for c in idx["columns"])
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {schema_name}.{table_name} ({cols})"
        )

    return len(fragments)


# ---------------------------------------------------------------------------
# Additive ALTER TABLE
# ---------------------------------------------------------------------------


def _ensure_updated_at_trigger(cur, schema_name: str, table_name: str) -> None:
    """Ensure the BEFORE UPDATE trigger for updated_at is present on the table."""
    # 1. Create schema-level helper trigger function
    cur.execute(f"""
        CREATE OR REPLACE FUNCTION {schema_name}.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # 2. Create standard BEFORE UPDATE trigger (idempotent setup)
    trigger_name = f"trg_{table_name}_updated_at"
    cur.execute(f"""
        DROP TRIGGER IF EXISTS {trigger_name} ON {schema_name}.{table_name};
        CREATE TRIGGER {trigger_name}
        BEFORE UPDATE ON {schema_name}.{table_name}
        FOR EACH ROW
        EXECUTE FUNCTION {schema_name}.update_updated_at_column();
    """)


def _sync_table(
    cur,
    table_name: str,
    meta: Any,
    schema_name: str,
) -> List[str]:
    """Sync table structure against config; purely additive."""
    actions: List[str] = []

    if not _table_exists(cur, schema_name, table_name):
        n = _create_table(cur, schema_name, table_name, meta)
        _ensure_updated_at_trigger(cur, schema_name, table_name)
        actions.append(f"created ({n} columns)")
        return actions

    expected = _get_expected_columns(table_name, meta)

    existing = _existing_columns(cur, schema_name, table_name)
    for col_name, col_meta in expected:
        if col_name not in existing:
            cur.execute(
                f"ALTER TABLE {schema_name}.{table_name} "
                f"ADD COLUMN IF NOT EXISTS {quote_col(col_name)} {col_meta['type']}"
            )
            actions.append(f"added {col_name}")

    _ensure_updated_at_trigger(cur, schema_name, table_name)
    return actions


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------


def _validate_sequence_coverage() -> None:
    """Ensure every nextval() default in DB_COLUMNS has a matching SEQUENCES entry."""
    import re

    for col_name, col_meta in DB_COLUMNS.items():
        default = col_meta.get("default")
        if not default or not isinstance(default, str):
            continue
        m = re.search(r"nextval\('([^']+)'\)", default)
        if not m:
            continue
        seq_name = m.group(1)
        if seq_name not in SEQUENCES:
            raise RuntimeError(
                f"Column '{col_name}' references sequence '{seq_name}' "
                f"which is missing from SEQUENCES registry"
            )


def _ensure_sequences(cur, schema_name: str) -> None:
    """Create sequences declared in SEQUENCES that belong to this schema."""
    for seq_name, meta in SEQUENCES.items():
        if meta["schema"] == schema_name:
            cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")


def ensure_schema(
    schema_name: str,
    conn=None,
) -> Dict[str, List[str]]:
    """Build and validate any schema mapped in the TABLES config."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
            _ensure_sequences(cur, schema_name)

            for table_name, meta in TABLES.items():
                if meta.get("schema") != schema_name:
                    continue
                qualified = f"{schema_name}.{table_name}"
                acts = _sync_table(cur, table_name, meta, schema_name=schema_name)
                actions[qualified] = acts
                if acts:
                    logger.info("Table %s: %s", qualified, ", ".join(acts))

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def ensure_league_profile(league_code: str, conn=None) -> Dict[str, List[str]]:
    """Ensure the ``profiles.leagues`` row exists for a single league."""
    own = conn is None
    if own:
        conn = get_db_connection()

    leagues_meta = TABLES["leagues"]
    leagues_schema = leagues_meta["schema"]
    if not leagues_schema:
        raise RuntimeError("leagues table has no schema")

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            from src.core.definitions.leagues import LEAGUES

            if league_code not in LEAGUES:
                raise ValueError(f"Unknown league {league_code!r}")

            cfg = LEAGUES[league_code]

            vals: Dict[str, Any] = {}
            for col, col_def in _data_columns_for_table("leagues"):
                if col == "code":
                    vals[col] = league_code
                elif col in cfg:
                    vals[col] = cfg[col]

            if not vals:
                raise ValueError(
                    f"No seedable columns found for league {league_code!r}"
                )

            constraints = leagues_meta.get("unique_constraints")
            conflict_cols = constraints[0] if constraints else ["code"]
            _insert_row(cur, leagues_schema, "leagues", vals, conflict_cols)
            qualified = f"{leagues_schema}.leagues"
            actions[qualified] = [f"seeded ({', '.join(sorted(vals.keys()))})"]

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def _topological_table_order() -> List[Tuple[str, Any]]:
    """Return all tables in dependency order based on foreign key references.

    Uses Kahn's algorithm. Tables with no outbound FKs come first.
    Cross-schema dependencies are handled naturally.
    """
    from collections import deque

    # Build lookup from (schema, table_name) -> registry key
    key_by_location: Dict[Tuple[str, str], str] = {}
    for key, meta in TABLES.items():
        schema = meta.get("schema")
        if schema:
            key_by_location[(schema, key)] = key

    # Build dependency graph: table -> tables it depends on
    in_degree: Dict[str, int] = {key: 0 for key in TABLES}
    dependents: Dict[str, List[str]] = {key: [] for key in TABLES}

    for key, meta in TABLES.items():
        for fk in meta.get("foreign_keys") or []:
            ref_schema = fk.get("ref_schema")
            ref_table = fk.get("ref_table")
            if not ref_schema or not ref_table:
                continue
            # Find the referenced table in our registry
            dep_key = key_by_location.get((ref_schema, ref_table))
            if dep_key and dep_key != key:  # skip self-references
                dependents[dep_key].append(key)
                in_degree[key] += 1

    # Kahn's algorithm
    queue = deque([k for k, d in in_degree.items() if d == 0])
    ordered: List[Tuple[str, Any]] = []

    while queue:
        key = queue.popleft()
        ordered.append((key, TABLES[key]))
        for dependent in dependents[key]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(TABLES):
        # Cycle detected - log which tables weren't ordered
        unresolved = set(TABLES.keys()) - {k for k, _ in ordered}
        logger.error("Circular FK dependency detected among tables: %s", unresolved)
        raise RuntimeError(f"Circular FK dependency in TABLES registry: {unresolved}")

    return ordered


def ensure_countries(conn=None) -> Dict[str, int]:
    """Seed ``profiles.countries`` from the COUNTRIES registry.

    Inserts new country codes, updates existing ones, and deletes rows
    whose codes are no longer in the registry (config-driven pruning).

    Returns ``{'inserted': n, 'updated': n, 'deleted': n}``.
    """
    from src.core.definitions.countries import COUNTRIES

    countries_meta = TABLES["countries"]
    countries_schema = countries_meta["schema"]
    countries_table = f"{countries_schema}.countries"

    own = conn is None
    if own:
        conn = get_db_connection()

    result = {"inserted": 0, "updated": 0, "deleted": 0}
    try:
        with conn.cursor() as cur:
            # Delete countries no longer in the registry
            cur.execute(f"SELECT code FROM {countries_table}")
            existing = {row[0] for row in cur.fetchall()}
            to_delete = existing - set(COUNTRIES.keys())
            if to_delete:
                cur.execute(
                    f"DELETE FROM {countries_table} WHERE code = ANY(%s)",
                    (list(to_delete),),
                )
                result["deleted"] = cur.rowcount
                logger.info(
                    "Pruned %d countries no longer in registry: %s",
                    result["deleted"],
                    sorted(to_delete),
                )

            # Upsert current country definitions in two passes to handle
            # self-referencing FK (sovereign_country references countries.code).
            # Pass 1: insert all countries without sovereign codes.
            for code, cfg in COUNTRIES.items():
                cur.execute(
                    f"""
                    INSERT INTO {countries_table} (code, name)
                    VALUES (%s, %s)
                    ON CONFLICT (code) DO UPDATE
                       SET name = EXCLUDED.name,
                           updated_at = NOW()
                    """,
                    (code, cfg.get("name", "")),
                )
                if cur.rowcount:
                    result["inserted" if code not in existing else "updated"] += 1

            # Pass 2: set sovereign_country references now that all rows exist.
            for code, cfg in COUNTRIES.items():
                sovereign = cfg.get("sovereign")
                if sovereign:
                    cur.execute(
                        f"UPDATE {countries_table} SET sovereign_country = %s, updated_at = NOW() WHERE code = %s",
                        (sovereign, code),
                    )
                else:
                    cur.execute(
                        f"UPDATE {countries_table} SET sovereign_country = NULL, updated_at = NOW() WHERE code = %s",
                        (code,),
                    )

        conn.commit()
        logger.info(
            "Countries: %d inserted, %d updated, %d deleted",
            result["inserted"],
            result["updated"],
            result["deleted"],
        )
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def bootstrap_schema(
    league_code: str,
    conn=None,
) -> Dict[str, List[str]]:
    """Unified bootstrap: ensure all schemas and seed the league profile row.

    Tables are created in topological order so cross-schema foreign keys
    are always valid by the time they are declared.
    """
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        # Validate config before touching the database
        _validate_sequence_coverage()

        with conn.cursor() as cur:
            schemas_set: set[str] = set()
            for m in TABLES.values():
                schema = m.get("schema")
                if isinstance(schema, str):
                    schemas_set.add(schema)
            schemas = sorted(schemas_set)
            # 1. Create all schemas first
            for schema_name in schemas:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

            # 2. Create all sequences
            for schema_name in schemas:
                _ensure_sequences(cur, schema_name)

            # 3. Create tables in FK dependency order
            for table_key, meta in _topological_table_order():
                schema_name = meta["schema"]
                acts = _sync_table(cur, table_key, meta, schema_name=schema_name)
                qualified = f"{schema_name}.{table_key}"
                actions[qualified] = acts
                if acts:
                    logger.info("Table %s: %s", qualified, ", ".join(acts))

        actions.update(ensure_league_profile(league_code, conn=conn))
        country_result = ensure_countries(conn=conn)
        countries_meta = TABLES["countries"]
        actions[f"{countries_meta['schema']}.countries"] = [
            f"seeded ({country_result['inserted']} new, {country_result['updated']} updated, {country_result['deleted']} deleted)"
        ]

        if own:
            conn.commit()
        return actions
    except Exception:
        if own:
            conn.rollback()
        raise
    finally:
        if own:
            conn.close()
