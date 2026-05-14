"""
The Glass - DDL Generator

Idempotent schema synchronization driven entirely by the central config dicts.
Builds the ``core`` schema (profiles + junctions + the_glass_id sequence),
the per-league stats schemas, and operational ETL tables.

Public surface:
    ensure_core_schema(conn)            - core schema + sequence + profile + junction tables
    ensure_league_schema(league, conn)  - league schema + stats tables + ETL operational tables
    ensure_league_profile(league, conn) - upsert a core.league_profiles row for a league key
    ensure_all(league, conn=None)       - one-shot orchestrator (called from the CLI)

The generator is purely additive: it CREATEs missing tables and ADDs
missing columns, but never drops or alters existing structures.  Schema
changes that require destructive migrations must be performed deliberately
outside this module.
"""

import logging
from typing import Any, Dict, Iterable, List, Tuple

from src.core.lib.postgres import get_db_connection, quote_col
from src.core.definitions.leagues import LEAGUES
from src.core.definitions.tables import (
    CORE_SCHEMA,
    JUNCTION_TABLES,
    OPERATIONAL_TABLES,
    PROFILE_TABLES,
    STATS_TABLES,
    THE_GLASS_ID_COLUMN,
    THE_GLASS_ID_SEQUENCE,
    THE_GLASS_ID_TYPE,
)
from src.core.definitions.columns import DB_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source ID column resolution (private helper for DDL)
# ---------------------------------------------------------------------------

def _get_source_id_columns_for_entity(entity: str) -> List[Tuple[str, str]]:
    """Source-id columns to add to ``entity``'s profile table, in stable order.

    A source contributes a column when it has a non-null ``entity_id_type``
    and includes ``entity`` in its ``applies_to`` list.
    """
    from src.etl.definitions.sources import SOURCES
    from src.etl.lib.sources_resolver import get_source_id_column

    columns: List[Tuple[str, str]] = []
    for source_key in sorted(SOURCES):
        meta = SOURCES[source_key]
        if meta.get('entity_id_type') is None:
            continue
        if entity not in meta.get('applies_to', []):
            continue
        columns.append((get_source_id_column(source_key), meta['entity_id_type']))
    return columns


# ---------------------------------------------------------------------------
# Column-set assembly
# ---------------------------------------------------------------------------

def _matches(col_meta: Dict[str, Any], scope: str, entity: str) -> bool:
    """Whether a DB_COLUMNS entry contributes to the given (scope, entity) table."""
    col_scope = col_meta.get('scope', [])
    # Normalize scope to list for comparison
    if isinstance(col_scope, str):
        col_scope = [col_scope]
    # Check if column scope includes target scope
    if scope not in col_scope:
        return False
    # If entity is None, skip entity_types check (for junction/operational tables)
    if entity is None:
        return True
    return entity in col_meta.get('entity_types', [])


def _data_columns_for(scope: str, entity: str,
                      has_opponent_columns: bool = False) -> List[Tuple[str, Dict[str, Any]]]:
    """Return ``[(col_name, col_meta), ...]`` for every DB_COLUMNS entry that
    belongs in the table identified by (scope, entity).

    For tables with ``has_opponent_columns``, also emits ``opp_<col>`` for
    columns whose ``entity_types`` lists ``'opponent'``.
    """
    out: List[Tuple[str, Dict[str, Any]]] = []
    for name, meta in DB_COLUMNS.items():
        if not _matches(meta, scope, entity):
            continue
        out.append((name, meta))
        if has_opponent_columns and 'opponent' in meta.get('entity_types', []):
            out.append((f'opp_{name}', meta))
    return out


# ---------------------------------------------------------------------------
# Single-column DDL fragment
# ---------------------------------------------------------------------------

def _format_default(default: Any, pg_type: str) -> str:
    """Render a default-value clause."""
    if default is None:
        return ''
    if isinstance(default, bool):
        return f"DEFAULT {'TRUE' if default else 'FALSE'}"
    if isinstance(default, (int, float)):
        return f'DEFAULT {default}'
    return f'DEFAULT {default}'  # already a SQL literal / function call


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
    return (
        f"FOREIGN KEY ({quote_col(fk['column'])}) "
        f"REFERENCES {fk['ref_schema']}.{fk['ref_table']}"
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


# ---------------------------------------------------------------------------
# Core schema bootstrap
# ---------------------------------------------------------------------------

def _ensure_sequence(cur) -> None:
    """Create the_glass_id sequence in the core schema if absent."""
    schema, _, name = THE_GLASS_ID_SEQUENCE.rpartition('.')
    cur.execute(
        f"CREATE SEQUENCE IF NOT EXISTS {THE_GLASS_ID_SEQUENCE} "
        f"AS {THE_GLASS_ID_TYPE} START 1 MINVALUE 1 NO CYCLE"
    )


def _the_glass_id_pk_clause() -> str:
    """Render the PK column clause used by every profile table."""
    return (
        f"{quote_col(THE_GLASS_ID_COLUMN)} {THE_GLASS_ID_TYPE} "
        f"PRIMARY KEY DEFAULT nextval('{THE_GLASS_ID_SEQUENCE}')"
    )


def _create_profile_table(cur, table_name: str, meta: Dict[str, Any]) -> int:
    """CREATE TABLE for a profile table.  Returns column count."""
    entity = meta['entity']
    qualified = f'{CORE_SCHEMA}.{table_name}'

    columns = _data_columns_for(scope='entities', entity=entity)
    source_id_cols = _get_source_id_columns_for_entity(entity)

    fragments: List[str] = [_the_glass_id_pk_clause()]
    fragments.extend(_column_ddl(name, m) for name, m in columns)
    for src_col, pg_type in source_id_cols:
        fragments.append(f"{quote_col(src_col)} {pg_type}")

    # UNIQUE constraints: source ID columns and DB_COLUMNS entries marked unique.
    for src_col, _ in source_id_cols:
        fragments.append(f"UNIQUE ({quote_col(src_col)})")
    for name, m in columns:
        if m.get('unique'):
            fragments.append(f"UNIQUE ({quote_col(name)})")

    cur.execute(f"CREATE TABLE {qualified} (\n  " + ",\n  ".join(fragments) + "\n)")
    return len(fragments)


def _create_junction_table(cur, table_name: str, meta: Dict[str, Any]) -> int:
    """CREATE TABLE for a junction table.  Returns column count.

    FK columns are derived from ``meta['foreign_keys']`` (BIGINT NOT NULL).
    Shared operational columns (is_active, season, timestamps) come from
    DB_COLUMNS with scope='junction'.
    """
    qualified = f'{CORE_SCHEMA}.{table_name}'
    # Emit FK columns first, in declaration order
    fk_col_names = [fk['column'] for fk in meta['foreign_keys']]
    # Deduplicate while preserving order (a column may appear in multiple FKs)
    seen: set = set()
    unique_fk_cols = [c for c in fk_col_names if not (c in seen or seen.add(c))]

    fragments: List[str] = []
    for col in unique_fk_cols:
        fragments.append(f"{quote_col(col)} BIGINT NOT NULL")

    # Operational data columns
    data_columns = _data_columns_for(scope='junction', entity=None)
    fk_set = set(unique_fk_cols)
    for col_name, col_def in data_columns:
        if col_name in fk_set:
            continue  # already emitted above
        ddl = f"{quote_col(col_name)} {col_def['type']}"
        if not col_def.get('nullable', True):
            ddl += ' NOT NULL'
        default_val = col_def.get('default')
        if default_val is not None:
            ddl += f' DEFAULT {default_val}'
        fragments.append(ddl)

    # Table-specific extra columns (e.g. jersey_num on team_rosters)
    for extra in meta.get('extra_columns', []):
        ddl = f"{quote_col(extra['name'])} {extra['type']}"
        if not extra.get('nullable', True):
            ddl += ' NOT NULL'
        if extra.get('default') is not None:
            ddl += f" DEFAULT {extra['default']}"
        fragments.append(ddl)

    pk_cols = ', '.join(quote_col(c) for c in meta['primary_key'])
    fragments.append(f"PRIMARY KEY ({pk_cols})")
    for fk in meta['foreign_keys']:
        fragments.append(_foreign_key_ddl(fk))
    cur.execute(f"CREATE TABLE {qualified} (\n  " + ",\n  ".join(fragments) + "\n)")

    # Create indexes
    for idx in meta.get('indexes', []):
        idx_name = f"idx_{table_name}_{idx['name']}"
        idx_cols = ', '.join(quote_col(c) for c in idx['columns'])
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qualified} ({idx_cols})")
    return len(fragments)


def _create_stats_table(cur, league_key: str, table_name: str, meta: Dict[str, Any]) -> int:
    """CREATE TABLE for a per-league stats table.  Returns column count."""
    entity = meta['entity']
    qualified = f'{league_key}.{table_name}'
    has_opp = meta.get('has_opponent_columns', False)

    data_cols = _data_columns_for(scope='stats', entity=entity, has_opponent_columns=has_opp)
    declared = {n for n, _ in data_cols}

    fragments: List[str] = [
        f"{quote_col(THE_GLASS_ID_COLUMN)} {THE_GLASS_ID_TYPE} NOT NULL"
    ]
    fragments.extend(_column_ddl(name, m) for name, m in data_cols)

    pk_cols = meta['primary_key']
    pk_str = ', '.join(quote_col(c) for c in pk_cols)
    fragments.append(f"PRIMARY KEY ({pk_str})")

    for fk in meta['foreign_keys']:
        fragments.append(_foreign_key_ddl(fk))

    cur.execute(f"CREATE TABLE {qualified} (\n  " + ",\n  ".join(fragments) + "\n)")

    # Create indexes
    for idx in meta.get('indexes', []):
        idx_name = f"idx_{table_name}_{idx['name']}"
        idx_cols = ', '.join(quote_col(c) for c in idx['columns'])
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qualified} ({idx_cols})")

    return len(declared) + 1  # +1 for the_glass_id


def _create_operational_table(cur, league_key: str, table_name: str, meta: Dict[str, Any]) -> int:
    """CREATE TABLE for an operational table (runs / tasks)."""
    qualified = f'{league_key}.{table_name}'
    # Determine scope based on table name
    scope = 'runs' if table_name == 'runs' else 'tasks'
    columns = _data_columns_for(scope=scope, entity=None)
    
    fragments: List[str] = []
    # Auto-generate 'id' as SERIAL PRIMARY KEY
    fragments.append(f'{quote_col("id")} SERIAL PRIMARY KEY')
    for col_name, col_def in columns:
        parts = [quote_col(col_name), col_def['type']]
        if not col_def.get('nullable', True):
            parts.append('NOT NULL')
        default_val = col_def.get('default')
        if default_val is not None:
            parts.append(f"DEFAULT {default_val}")
        fragments.append(' '.join(parts))

    unique_key = meta.get('unique_key')
    if unique_key:
        uk_str = ', '.join(quote_col(c) for c in unique_key)
        fragments.append(f"UNIQUE ({uk_str})")

    for fk in meta.get('foreign_keys', []):
        # For operational tables, ref_schema may be None (same schema)
        if fk['ref_schema'] is None:
            fk_copy = fk.copy()
            fk_copy['ref_schema'] = league_key
            fragments.append(_foreign_key_ddl(fk_copy))
        else:
            fragments.append(_foreign_key_ddl(fk))

    cur.execute(f"CREATE TABLE {qualified} (\n  " + ",\n  ".join(fragments) + "\n)")

    # Create indexes
    for idx in meta.get('indexes', []):
        idx_name = f"idx_{table_name}_{idx['name']}"
        idx_cols = ', '.join(quote_col(c) for c in idx['columns'])
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qualified} ({idx_cols})")

    return len(fragments)


# ---------------------------------------------------------------------------
# Additive ALTER TABLE helpers
# ---------------------------------------------------------------------------

def _add_missing_columns(
    cur,
    schema: str,
    table: str,
    expected: Iterable[Tuple[str, str]],
    actions: List[str],
) -> None:
    """Compare expected (name, pg_type) pairs against information_schema and
    issue ``ADD COLUMN IF NOT EXISTS`` for anything missing.
    """
    existing = _existing_columns(cur, schema, table)
    for col_name, pg_type in expected:
        if col_name in existing:
            continue
        cur.execute(
            f'ALTER TABLE {schema}.{table} '
            f'ADD COLUMN IF NOT EXISTS {quote_col(col_name)} {pg_type}'
        )
        actions.append(f'added {col_name}')


def _sync_profile_table(cur, table_name: str, meta: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    if not _table_exists(cur, CORE_SCHEMA, table_name):
        n = _create_profile_table(cur, table_name, meta)
        actions.append(f'created ({n} fragments)')
        return actions

    expected: List[Tuple[str, str]] = [(THE_GLASS_ID_COLUMN, THE_GLASS_ID_TYPE)]
    for name, m in _data_columns_for(scope='entities', entity=meta['entity']):
        expected.append((name, m['type']))
    for src_col, pg_type in _get_source_id_columns_for_entity(meta['entity']):
        expected.append((src_col, pg_type))

    _add_missing_columns(cur, CORE_SCHEMA, table_name, expected, actions)
    return actions


def _sync_junction_table(cur, table_name: str, meta: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    if not _table_exists(cur, CORE_SCHEMA, table_name):
        n = _create_junction_table(cur, table_name, meta)
        actions.append(f'created ({n} columns)')
        return actions

    # FK columns (BIGINT NOT NULL) derived from foreign_keys metadata
    seen: set = set()
    fk_expected = [
        (fk['column'], 'BIGINT')
        for fk in meta['foreign_keys']
        if not (fk['column'] in seen or seen.add(fk['column']))
    ]
    # Operational data columns from DB_COLUMNS
    op_columns = _data_columns_for(scope='junction', entity=None)
    fk_names = {c for c, _ in fk_expected}
    op_expected = [
        (name, col_meta['type'])
        for name, col_meta in op_columns
        if name not in fk_names
    ]
    # Table-specific extra columns
    extra_expected = [
        (col['name'], col['type'])
        for col in meta.get('extra_columns', [])
    ]
    expected = fk_expected + op_expected + extra_expected
    _add_missing_columns(cur, CORE_SCHEMA, table_name, expected, actions)
    return actions


def _sync_stats_table(cur, league_key: str, table_name: str,
                      meta: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    if not _table_exists(cur, league_key, table_name):
        n = _create_stats_table(cur, league_key, table_name, meta)
        actions.append(f'created ({n} columns)')
        return actions

    expected: List[Tuple[str, str]] = [(THE_GLASS_ID_COLUMN, THE_GLASS_ID_TYPE)]
    has_opp = meta.get('has_opponent_columns', False)
    for name, m in _data_columns_for(scope='stats', entity=meta['entity'],
                                     has_opponent_columns=has_opp):
        expected.append((name, m['type']))

    _add_missing_columns(cur, league_key, table_name, expected, actions)
    return actions


def _sync_operational_table(cur, league_key: str, table_name: str,
                            meta: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    if not _table_exists(cur, league_key, table_name):
        n = _create_operational_table(cur, league_key, table_name, meta)
        actions.append(f'created ({n} columns)')
        return actions

    # Determine scope based on table name
    scope = 'runs' if table_name == 'runs' else 'tasks'
    columns = _data_columns_for(scope=scope, entity=None)
    
    # 'id' is auto-generated, not in DB_COLUMNS
    expected = [('id', 'SERIAL')] + [(name, meta['type']) for name, meta in columns]
    _add_missing_columns(cur, league_key, table_name, expected, actions)
    return actions


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

def ensure_core_schema(conn=None) -> Dict[str, List[str]]:
    """Ensure the core schema, the_glass_id sequence, and profile + junction
    tables all exist, applying any additive column changes."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {CORE_SCHEMA}")
            _ensure_sequence(cur)

            for name, meta in PROFILE_TABLES.items():
                qualified = f'{CORE_SCHEMA}.{name}'
                acts = _sync_profile_table(cur, name, meta)
                actions[qualified] = acts
                if acts:
                    logger.info('Profile %s: %s', qualified, ', '.join(acts))

            for name, meta in JUNCTION_TABLES.items():
                qualified = f'{CORE_SCHEMA}.{name}'
                acts = _sync_junction_table(cur, name, meta)
                actions[qualified] = acts
                if acts:
                    logger.info('Junction %s: %s', qualified, ', '.join(acts))

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def ensure_league_schema(league_key: str, conn=None) -> Dict[str, List[str]]:
    """Ensure the league's schema + stats tables + ETL operational tables."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {league_key}")

            for name, meta in STATS_TABLES.items():
                qualified = f'{league_key}.{name}'
                acts = _sync_stats_table(cur, league_key, name, meta)
                actions[qualified] = acts
                if acts:
                    logger.info('Stats %s: %s', qualified, ', '.join(acts))

            for name, meta in OPERATIONAL_TABLES.items():
                qualified = f'{league_key}.{name}'
                acts = _sync_operational_table(cur, league_key, name, meta)
                actions[qualified] = acts
                if acts:
                    logger.info('Operational %s: %s', qualified, ', '.join(acts))

        conn.commit()
        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def ensure_all(league_key: str, conn=None) -> Dict[str, List[str]]:
    """Bootstrap entrypoint: core schema + the league's schema."""
    out: Dict[str, List[str]] = {}
    out.update(ensure_core_schema(conn))
    out.update(ensure_league_schema(league_key, conn))
    return out


# ---------------------------------------------------------------------------
# League profile row bootstrap
# ---------------------------------------------------------------------------

def ensure_league_profile(league_key: str, conn) -> int:
    """Ensure ``core.league_profiles`` has a row for ``league_key``.

    ``league_key`` is the pipeline's canonical identifier for the league
    (e.g. ``'nba'``) and is stored in the ``league_key`` column, which
    carries a UNIQUE constraint.  Idempotent: if a row already exists its
    the_glass_id is returned unchanged.

    Columns to populate are auto-derived from DB_COLUMNS: any column whose
    scope includes 'entities', entity_types includes 'league', sources is None,
    and whose name appears as a key in the LEAGUES config entry.  This means
    adding a new league-level field only requires updating DB_COLUMNS and
    LEAGUES — this function never needs to change.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    league = LEAGUES[league_key]
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {quote_col(THE_GLASS_ID_COLUMN)} "
            f"FROM {CORE_SCHEMA}.league_profiles WHERE league_key = %s",
            (league_key,),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row[0])

        # Derive which columns to populate: any column that applies to league
        # profiles and whose name appears in the LEAGUES config entry.
        # league_key is handled separately since its value is the dict key itself.
        profile_cols = {
            col_name: league[col_name]
            for col_name, col_meta in DB_COLUMNS.items()
            if 'league' in (col_meta.get('entity_types') or [])
            and 'entities' in (col_meta.get('scope') or [])
            and col_name in league
        }

        cols = ['league_key'] + list(profile_cols.keys())
        values = [league_key] + list(profile_cols.values())
        col_str = ', '.join(quote_col(c) for c in cols)
        placeholders = ', '.join(['%s'] * len(cols))

        cur.execute(
            f"INSERT INTO {CORE_SCHEMA}.league_profiles ({col_str}) "
            f"VALUES ({placeholders}) RETURNING {quote_col(THE_GLASS_ID_COLUMN)}",
            values,
        )
        new_id = int(cur.fetchone()[0])
        logger.info(
            'Registered league %r in core.league_profiles (the_glass_id=%d)',
            league_key, new_id,
        )
        return new_id
