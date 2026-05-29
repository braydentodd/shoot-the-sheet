"""
The Glass - DDL Generator

Idempotent schema synchronization driven entirely by the central config dicts.
The generator is purely additive: it CREATEs missing tables and ADDs
missing columns, but never drops or alters existing structures. Schema
changes that require destructive migrations must be performed deliberately
outside this module.
"""

import logging
from typing import Any, Dict, List, Tuple

from src.core.lib.postgres import get_db_connection, quote_col
from src.core.definitions.schema import TABLES, SCHEMAS, SEQUENCES
from src.core.definitions.db_columns import DB_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source ID column resolution
# ---------------------------------------------------------------------------

def _get_source_id_columns_for_entity(entity: str) -> List[Tuple[str, str]]:
    """Source-id columns to add to ``entity``'s profile table, in stable order.

    Imports are deferred to avoid making ``core.lib.ddl`` depend on ETL-layer
    modules at import time. If ``SOURCES`` ever moves to ``core.definitions``,
    these can be hoisted to module level.
    """
    from src.etl.definitions.sources import SOURCES
    from src.etl.lib.sources_resolver import get_source_id_column

    columns: List[Tuple[str, str]] = []
    seen: set = set()
    for source_key in sorted(SOURCES):
        meta = SOURCES[source_key]
        if meta.get('entity_id_type') is None:
            continue
        if not meta.get('external', False):
            continue
        if entity not in meta.get('applies_to', []):
            continue
        col_name = get_source_id_column(source_key)
        if col_name in seen:
            continue
        seen.add(col_name)
        columns.append((col_name, meta['entity_id_type']))
    return columns


# ---------------------------------------------------------------------------
# Column-set assembly
# ---------------------------------------------------------------------------

def _matches(col_meta: Dict[str, Any], scope: str, entity: str) -> bool:
    """Whether a DB_COLUMNS entry contributes to the given (scope, entity) table."""
    if scope not in col_meta.get('scope', []):
        return False
    if entity is None:
        return True
    return entity in (col_meta.get('entity_types') or [])


def _data_columns_for(scope: str, entity: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Return ``[(col_name, col_meta), ...]`` for every matching DB_COLUMNS entry."""
    return [
        (name, meta)
        for name, meta in DB_COLUMNS.items()
        if _matches(meta, scope, entity)
    ]


def _data_columns_for_scopes(scopes: List[str], entity: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Return matching DB columns across several scopes without duplicates."""
    ordered: List[Tuple[str, Dict[str, Any]]] = []
    seen = set()
    for scope in scopes:
        for name, meta in _data_columns_for(scope=scope, entity=entity):
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
        return ''
    if isinstance(default, bool):
        return f"DEFAULT {'TRUE' if default else 'FALSE'}"
    return f'DEFAULT {default}'


def _column_ddl(name: str, meta: Dict[str, Any]) -> str:
    """Render a single ``CREATE TABLE`` column fragment."""
    parts = [quote_col(name), meta['type']]
    if not meta.get('nullable', True):
        parts.append('NOT NULL')
    default = _format_default(meta.get('default'), meta['type'])
    if default:
        parts.append(default)
    return ' '.join(parts)


def _foreign_key_ddl(fk: Dict[str, Any]) -> str:
    """Render a ``FOREIGN KEY`` clause."""
    target = f"{fk['ref_schema']}.{fk['ref_table']}"
    return (
        f"FOREIGN KEY ({quote_col(fk['column'])}) "
        f"REFERENCES {target}"
        f"({quote_col(fk['ref_column'])}) "
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
    column_sql = ', '.join(quote_col(col) for col in columns)
    values_sql = ', '.join(['%s'] * len(columns))
    params = [values[col] for col in columns]

    if conflict_columns:
        conflict_sql = ', '.join(quote_col(col) for col in conflict_columns)
        on_conflict = f'ON CONFLICT ({conflict_sql}) DO NOTHING'
    else:
        on_conflict = 'ON CONFLICT DO NOTHING'

    cur.execute(
        f'INSERT INTO {schema_name}.{table_name} ({column_sql}) '
        f'VALUES ({values_sql}) {on_conflict}',
        params,
    )


# ---------------------------------------------------------------------------
# Core Schema Build Engine
# ---------------------------------------------------------------------------

def _get_expected_columns(meta: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Return the complete ordered set of (column_name, column_meta) for a table.

    Centralises column resolution so that both ``_create_table`` and
    ``_sync_table`` derive their column lists from a single source of truth.
    """
    expected: List[Tuple[str, Dict[str, Any]]] = []
    seen: set = set()
    source_scopes = meta.get('source_scopes') or [meta.get('scope', '')]

    for col in meta.get('primary_key') or []:
        expected.append((col, DB_COLUMNS[col]))
        seen.add(col)

    for fk in meta.get('foreign_keys', []):
        col = fk['column']
        if col not in seen:
            expected.append((col, DB_COLUMNS[col]))
            seen.add(col)

    for name, m in _data_columns_for_scopes(scopes=source_scopes, entity=meta.get('entity')):
        if name not in seen:
            expected.append((name, m))
            seen.add(name)

    if meta.get('source_ids', False) and meta.get('entity'):
        for src_col, pg_type in _get_source_id_columns_for_entity(meta['entity']):
            if src_col not in seen:
                expected.append((src_col, {'type': pg_type}))
                seen.add(src_col)

    return expected


def _create_table(cur, schema_name: str, table_name: str, meta: Dict[str, Any]) -> int:
    """Unified CREATE TABLE builder driven strictly by registry config."""
    fragments: List[str] = []
    pk_cols = set(meta.get('primary_key') or [])

    for col_name, col_meta in _get_expected_columns(meta):
        fragments.append(_column_ddl(col_name, col_meta))

    # Column-level UNIQUE constraints (from DB_COLUMNS 'unique' flag)
    source_scopes = meta.get('source_scopes') or [meta.get('scope', '')]
    for name, m in _data_columns_for_scopes(scopes=source_scopes, entity=meta.get('entity')):
        if m.get('unique') and name not in pk_cols:
            fragments.append(f"UNIQUE ({quote_col(name)})")

    # Source ID UNIQUE constraints
    if meta.get('source_ids', False) and meta.get('entity'):
        for src_col, _ in _get_source_id_columns_for_entity(meta['entity']):
            fragments.append(f"UNIQUE ({quote_col(src_col)})")

    # Table-level constraints: PK, FK, multi-column UNIQUE
    if pk_cols:
        pk_str = ', '.join(quote_col(c) for c in pk_cols)
        fragments.append(f"PRIMARY KEY ({pk_str})")

    for fk in meta.get('foreign_keys', []):
        fragments.append(_foreign_key_ddl(fk))

    for uc in meta.get('unique_constraints') or []:
        uc_cols = ', '.join(quote_col(c) for c in uc)
        fragments.append(f"UNIQUE ({uc_cols})")

    cur.execute(
        f"CREATE TABLE {schema_name}.{table_name} (\n  "
        + ",\n  ".join(fragments)
        + "\n)"
    )

    # Indexes — prefix with schema to avoid cross-schema name collisions
    for idx in meta.get('indexes', []):
        idx_name = f"idx_{schema_name}_{table_name}_{idx['name']}"
        cols = ', '.join(quote_col(c) for c in idx['columns'])
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


def _sync_table(cur, table_name: str, meta: Dict[str, Any], schema_name: str) -> List[str]:
    """Sync table structure against config; purely additive."""
    actions: List[str] = []

    if not _table_exists(cur, schema_name, table_name):
        n = _create_table(cur, schema_name, table_name, meta)
        _ensure_updated_at_trigger(cur, schema_name, table_name)
        actions.append(f'created ({n} columns)')
        return actions

    expected = _get_expected_columns(meta)

    existing_unique_sets = _existing_unique_column_sets(cur, schema_name, table_name)
    if meta.get('source_ids', False) and meta.get('entity'):
        for src_col, _ in _get_source_id_columns_for_entity(meta['entity']):
            if (src_col,) in existing_unique_sets:
                continue
            cur.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{table_name}_{src_col} '
                f'ON {schema_name}.{table_name} ({quote_col(src_col)})'
            )
            actions.append(f'added unique {src_col}')

    existing = _existing_columns(cur, schema_name, table_name)
    for col_name, col_meta in expected:
        if col_name not in existing:
            cur.execute(
                f'ALTER TABLE {schema_name}.{table_name} '
                f'ADD COLUMN IF NOT EXISTS {quote_col(col_name)} {col_meta["type"]}'
            )
            actions.append(f'added {col_name}')

    _ensure_updated_at_trigger(cur, schema_name, table_name)
    return actions


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

def _validate_sequence_coverage() -> None:
    """Ensure every nextval() default in DB_COLUMNS has a matching SEQUENCES entry."""
    import re
    for col_name, col_meta in DB_COLUMNS.items():
        default = col_meta.get('default') or ''
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
        if meta['schema'] == schema_name:
            cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")


def ensure_schema(schema_name: str, conn=None) -> Dict[str, List[str]]:
    """Build and validate any schema mapped in the TABLES config."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
            _ensure_sequences(cur, schema_name)

            for name, meta in TABLES.items():
                if meta.get('schema') != schema_name:
                    continue
                qualified = f'{schema_name}.{name}'
                acts = _sync_table(cur, name, meta, schema_name=schema_name)
                actions[qualified] = acts
                if acts:
                    logger.info('Table %s: %s', qualified, ', '.join(acts))

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def ensure_league_profile(league_key: str, conn=None) -> Dict[str, List[str]]:
    """Ensure the ``profiles.leagues`` row exists for a single league."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            from src.core.definitions.leagues import LEAGUES

            if league_key not in LEAGUES:
                raise ValueError(f"Unknown league {league_key!r}")

            cfg = LEAGUES[league_key]

            vals: Dict[str, Any] = {}
            for col, col_def in _data_columns_for(scope='profiles', entity='league'):
                if col in cfg:
                    vals[col] = cfg[col]
                elif col_def.get('manager') == 'execution_context':
                    if col == 'league_key':
                        vals[col] = league_key

            if not vals:
                raise ValueError(f"No seedable columns found for league {league_key!r}")

            constraints = TABLES['leagues'].get('unique_constraints')
            conflict_cols = constraints[0] if constraints else ['league_key']
            _insert_row(cur, 'profiles', 'leagues', vals, conflict_cols)
            actions['profiles.leagues'] = [f"seeded ({', '.join(sorted(vals.keys()))})"]

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def _topological_table_order() -> List[Tuple[str, Dict[str, Any]]]:
    """Return all tables in dependency order based on foreign key references.

    Uses Kahn's algorithm. Tables with no outbound FKs come first.
    Cross-schema dependencies are handled naturally.
    """
    from collections import deque

    # Build lookup from (schema, table_name) -> registry key
    key_by_location: Dict[Tuple[str, str], str] = {}
    for key, meta in TABLES.items():
        schema = meta.get('schema')
        if schema:
            key_by_location[(schema, key)] = key

    # Build dependency graph: table -> tables it depends on
    in_degree: Dict[str, int] = {key: 0 for key in TABLES}
    dependents: Dict[str, List[str]] = {key: [] for key in TABLES}

    for key, meta in TABLES.items():
        for fk in meta.get('foreign_keys', []):
            ref_schema = fk.get('ref_schema')
            ref_table = fk.get('ref_table')
            if not ref_schema or not ref_table:
                continue
            # Find the referenced table in our registry
            dep_key = key_by_location.get((ref_schema, ref_table))
            if dep_key and dep_key != key:  # skip self-references
                dependents[dep_key].append(key)
                in_degree[key] += 1

    # Kahn's algorithm
    queue = deque([k for k, d in in_degree.items() if d == 0])
    ordered: List[Tuple[str, Dict[str, Any]]] = []

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
        logger.error('Circular FK dependency detected among tables: %s', unresolved)
        raise RuntimeError(f'Circular FK dependency in TABLES registry: {unresolved}')

    return ordered


def bootstrap_schema(league_key: str, conn=None) -> Dict[str, List[str]]:
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
            # 1. Create all schemas first
            for schema_name in sorted(SCHEMAS):
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

            # 2. Create all sequences
            for schema_name in sorted(SCHEMAS):
                _ensure_sequences(cur, schema_name)

            # 3. Create tables in FK dependency order
            for table_key, meta in _topological_table_order():
                schema_name = meta['schema']
                acts = _sync_table(cur, table_key, meta, schema_name=schema_name)
                qualified = f"{schema_name}.{table_key}"
                actions[qualified] = acts
                if acts:
                    logger.info('Table %s: %s', qualified, ', '.join(acts))

        actions.update(ensure_league_profile(league_key, conn=conn))

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