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
from src.core.definitions.tables import TABLES
from src.core.definitions.db_columns import DB_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source ID column resolution
# ---------------------------------------------------------------------------

def _get_source_id_columns_for_entity(entity: str) -> List[Tuple[str, str]]:
    """Source-id columns to add to ``entity``'s profile table, in stable order."""
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
    # Strictly trust the List[str] contract defined in TypedDict
    if scope not in col_meta.get('scope', []):
        return False
    if entity is None:
        return True
    return entity in (col_meta.get('entity_types') or [])


def _data_columns_for(scope: str, entity: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Return ``[(col_name, col_meta), ...]`` for every DB_COLUMNS entry."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for name, meta in DB_COLUMNS.items():
        if not _matches(meta, scope, entity):
            continue
        out.append((name, meta))
    return out


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


def _foreign_key_ddl(fk: Dict[str, Any], default_schema: str = 'core') -> str:
    """Render a ``FOREIGN KEY`` clause."""
    ref_schema = fk.get('ref_schema') or default_schema
    target = f"{ref_schema}.{fk['ref_table']}"
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


# ---------------------------------------------------------------------------
# Core Schema Build Engine
# ---------------------------------------------------------------------------

def _create_table(cur, schema_name: str, table_name: str, meta: Dict[str, Any]) -> int:
    """Unified CREATE TABLE builder driven strictly by registry config."""
    fragments: List[str] = []
    seen_columns: set = set()

    pk_cols = meta.get('primary_key') or []

    # 1. Primary Keys
    for col in pk_cols:
        # If a PK entry is missing from DB_COLUMNS (e.g. run_id/task_id),
        # fall back to a reasonable identity/BIGINT default rather than
        # raising a KeyError. Registries are preferred, but this keeps
        # the sync resilient during iterative migration work.
        default_meta = {'type': 'BIGINT GENERATED BY DEFAULT AS IDENTITY', 'nullable': False}
        col_meta = DB_COLUMNS.get(col, default_meta)
        if col not in seen_columns:
            fragments.append(_column_ddl(col, col_meta))
            seen_columns.add(col)

    # 2. Foreign Keys
    for fk in meta.get('foreign_keys', []):
        col = fk['column']
        if col not in seen_columns:
            col_meta = DB_COLUMNS.get(col, {'type': 'BIGINT', 'nullable': False})
            fragments.append(_column_ddl(col, col_meta))
            seen_columns.add(col)

    # 3. Data Columns
    col_scope = meta.get('scope', '')
    for col_name, col_def in _data_columns_for(scope=col_scope, entity=meta.get('entity')):
        if col_name not in seen_columns:
            fragments.append(_column_ddl(col_name, col_def))
            seen_columns.add(col_name)

    # 4. Source IDs
    if meta.get('source_ids', False) and meta.get('entity'):
        for src_col, pg_type in _get_source_id_columns_for_entity(meta['entity']):
            if src_col not in seen_columns:
                fragments.append(f"{quote_col(src_col)} {pg_type}")
                seen_columns.add(src_col)

    # 5. Unique Constraints (Column Level)
    for name, m in _data_columns_for(scope=col_scope, entity=meta.get('entity')):
        if m.get('unique') and name not in pk_cols:
            fragments.append(f"UNIQUE ({quote_col(name)})")

    # 6. Table Constraints (PK, FK, Unique Arrays)
    if pk_cols:
        pk_str = ', '.join(quote_col(c) for c in pk_cols)
        fragments.append(f"PRIMARY KEY ({pk_str})")

    for fk in meta.get('foreign_keys', []):
        ref_schema = 'core' if fk['ref_schema'] == 'core' else schema_name
        fragments.append(_foreign_key_ddl(fk, default_schema=ref_schema))

    for uc in meta.get('unique_constraints') or []:
        uc_cols = ', '.join(quote_col(c) for c in uc)
        fragments.append(f"UNIQUE ({uc_cols})")

    # Build Statement
    cur.execute(f"CREATE TABLE {schema_name}.{table_name} (\n  " + ",\n  ".join(fragments) + "\n)")

    # 7. Indexes
    for idx in meta.get('indexes', []):
        idx_name = f"idx_{table_name}_{idx['name']}"
        cols = ', '.join(quote_col(c) for c in idx['columns'])
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {schema_name}.{table_name} ({cols})")

    return len(fragments)


# ---------------------------------------------------------------------------
# Additive ALTER TABLE helpers
# ---------------------------------------------------------------------------

def _sync_table(cur, table_name: str, meta: Dict[str, Any], schema_name: str) -> List[str]:
    """Dynamically syncs table structure by diffing against config."""
    actions: List[str] = []

    if not _table_exists(cur, schema_name, table_name):
        n = _create_table(cur, schema_name, table_name, meta)
        actions.append(f'created ({n} columns)')
        return actions

    expected: List[Tuple[str, str]] = []

    for pk in meta.get('primary_key') or []:
        pk_meta = DB_COLUMNS[pk] # STRICT enforcement
        expected.append((pk, pk_meta['type']))

    for fk in meta.get('foreign_keys', []):
        col = fk['column']
        if not any(col == e[0] for e in expected):
            fk_meta = DB_COLUMNS[col] # STRICT enforcement
            expected.append((col, fk_meta['type']))

    col_scope = meta.get('scope', '')
    fk_set = {c for c, _ in expected}
    for name, m in _data_columns_for(scope=col_scope, entity=meta.get('entity')):
        if name not in fk_set:
            expected.append((name, m['type']))

    if meta.get('source_ids', False) and meta.get('entity'):
        for src_col, pg_type in _get_source_id_columns_for_entity(meta['entity']):
            if not any(src_col == e[0] for e in expected):
                expected.append((src_col, pg_type))

    existing = _existing_columns(cur, schema_name, table_name)
    for col_name, pg_type in expected:
        if col_name not in existing:
            cur.execute(f'ALTER TABLE {schema_name}.{table_name} ADD COLUMN IF NOT EXISTS {quote_col(col_name)} {pg_type}')
            actions.append(f'added {col_name}')

    return actions


# ---------------------------------------------------------------------------
# Unified Orchestrator
# ---------------------------------------------------------------------------

def ensure_schema(schema_name: str, conn=None) -> Dict[str, List[str]]:
    """Dynamically builds and validates any schema mapped in the TABLES config."""
    own = conn is None
    if own:
        conn = get_db_connection()

    actions: Dict[str, List[str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

            for name, meta in TABLES.items():
                target_schema = 'core' if meta.get('schema') == 'core' else schema_name
                
                if target_schema != schema_name:
                    continue

                qualified = f'{target_schema}.{name}'
                acts = _sync_table(cur, name, meta, schema_name=target_schema)
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