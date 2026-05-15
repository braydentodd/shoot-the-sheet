"""
The Glass - ETL Database Loader

Bulk-write primitives and high-level row writers used by the executor.

ID model:
    Profile tables (``core.{entity}_profiles``)
        - PK: ``the_glass_id`` (auto-allocated by ``core.the_glass_id_seq``)
        - Per-source identity columns: ``{source_key}_id`` (UNIQUE)
        - Conflict key on upsert is the per-source identity column

    Stats tables (``{league}.{entity}_season_stats``)
        - PK: composite, includes ``the_glass_id`` and (for player) ``team_id``
        - Source IDs are resolved to the_glass_id values before write
        - Rows that cannot resolve all FK references are dropped with a warning
"""

import logging
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from psycopg2.extras import execute_values

from src.core.lib.postgres import db_connection, quote_col
from src.core.definitions.tables import (
    PROFILE_TABLES,
    STATS_TABLES,
    THE_GLASS_ID_COLUMN,
)
from src.etl.lib.sources_resolver import get_default_external_source, get_source_id_column
from src.core.lib.tables_resolver import get_table_name
from src.etl.lib.entity_matcher import approve_entities

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Bulk primitives
# ---------------------------------------------------------------------------

def bulk_upsert(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
    conflict_columns: List[str],
    update_columns: Optional[List[str]] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """``INSERT ... ON CONFLICT DO UPDATE SET`` for a batch of rows.

    Args:
        conn:             psycopg2 connection.
        table:            Schema-qualified table name.
        columns:          Ordered column names matching ``data`` tuples.
        data:             List of value tuples (one per row).
        conflict_columns: Unique-constraint columns for conflict detection.
        update_columns:   Columns to overwrite on conflict.  ``None`` -> all
                          non-conflict columns.
        batch_size:       Rows per ``execute_values`` call.

    Returns:
        Number of rows written.
    """
    if not data:
        return 0

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    cols_sql = ', '.join(quote_col(c) for c in columns)
    conflict_sql = ', '.join(quote_col(c) for c in conflict_columns)

    if update_columns:
        update_sql = ', '.join(
            f'{quote_col(c)} = EXCLUDED.{quote_col(c)}' for c in update_columns
        )
        conflict_clause = (
            f'ON CONFLICT ({conflict_sql}) DO UPDATE SET '
            f'{update_sql}, updated_at = NOW()'
        )
    else:
        conflict_clause = f'ON CONFLICT ({conflict_sql}) DO NOTHING'

    query = f'INSERT INTO {table} ({cols_sql}) VALUES %s {conflict_clause}'

    cursor = conn.cursor()
    written = 0

    for offset in range(0, len(data), batch_size):
        batch = data[offset:offset + batch_size]
        try:
            execute_values(cursor, query, batch, page_size=batch_size)
            written += len(batch)
        except Exception:
            logger.error('Batch failed at offset %d in %s', offset, table)
            conn.rollback()
            raise

    conn.commit()
    return written


def bulk_copy(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
) -> int:
    """Ultra-fast initial load via PostgreSQL ``COPY FROM``.

    Does **not** handle conflicts -- intended for empty-table initial loads.
    """
    if not data:
        return 0

    buf = StringIO()
    for row in data:
        line = '\t'.join(str(v) if v is not None else '\\N' for v in row)
        buf.write(line + '\n')
    buf.seek(0)

    cursor = conn.cursor()
    try:
        cursor.copy_from(buf, table, columns=columns, null='\\N')
        conn.commit()
        return len(data)
    except Exception:
        logger.error('COPY into %s failed', table)
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# ID resolution helpers
# ---------------------------------------------------------------------------

def _load_glass_id_map(
    conn: Any,
    entity: str,
    source_key: str,
    source_ids: Iterable[Any] = None,
) -> Dict[str, int]:
    """Load ``{str(source_id): the_glass_id}`` mapping from a profile table.

    If ``source_ids`` is provided, only rows for those IDs are fetched.
    """
    profile_table = get_table_name(entity, 'entity')
    src_col = get_source_id_column(source_key)

    sql_base = (
        f"SELECT {quote_col(src_col)}, {quote_col(THE_GLASS_ID_COLUMN)} "
        f"FROM {profile_table}"
    )

    with conn.cursor() as cur:
        if source_ids is None:
            cur.execute(sql_base)
        else:
            ids_list = [v for v in source_ids if v is not None]
            if not ids_list:
                return {}
            cur.execute(
                sql_base + f" WHERE {quote_col(src_col)} = ANY(%s)",
                (ids_list,),
            )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def _resolve_fk_value_columns(
    rows: Dict[Any, Dict[str, Any]],
    conn: Any,
    league_key: str,
    source_key: str,
    table_name: str,
) -> Tuple[Dict[Any, Dict[str, Any]], int]:
    """Translate source-id values in FK columns to the_glass_id values.

    Looks at every FK on the stats table whose ``column`` is not the synthetic
    ``the_glass_id`` and whose ``ref_table`` is a profile table.  For each
    such column, the raw value in row data is treated as a source ID and
    replaced with the profile's the_glass_id.

    Rows whose FK columns cannot be resolved are dropped.

    Returns ``(filtered_rows, dropped_count)``.
    """
    meta = STATS_TABLES[table_name]
    fks = [
        fk for fk in meta['foreign_keys']
        if fk['column'] != THE_GLASS_ID_COLUMN
        and fk['ref_table'].endswith('_profiles')
    ]
    if not fks:
        return rows, 0

    # Build {column -> ref_entity}
    profile_to_entity = {name: m['entity'] for name, m in PROFILE_TABLES.items()}

    # Batch: collect all raw values per FK column, then one query per FK column.
    fk_maps: Dict[str, Dict[str, int]] = {}
    for fk in fks:
        col = fk['column']
        raw_values = [row.get(col) for row in rows.values() if row.get(col) is not None]
        ref_entity = profile_to_entity[fk['ref_table']]
        fk_maps[col] = _load_glass_id_map(conn, ref_entity, source_key, raw_values)

    dropped = 0
    out: Dict[Any, Dict[str, Any]] = {}
    for source_id, row in rows.items():
        translated = dict(row)
        keep = True
        for fk in fks:
            col = fk['column']
            raw = translated.get(col)
            if raw is None:
                keep = False
                break
            glass_id = fk_maps[col].get(str(raw))
            if glass_id is None:
                keep = False
                break
            translated[col] = glass_id
        if keep:
            out[source_id] = translated
        else:
            dropped += 1
    return out, dropped


# ---------------------------------------------------------------------------
# High-level row writers
# ---------------------------------------------------------------------------

def write_entity_rows(
    entity: str,
    scope: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    source_key: Optional[str] = None,
) -> int:
    """Write extracted rows to the database.

    Args:
        entity:       ``'league'``, ``'team'`` or ``'player'``.
        scope:        ``'entity'`` or ``'stats'``.
        rows:         ``{source_entity_id: {col_name: value, ...}, ...}``.
        season:       Season label (``'2024-25'``).
        season_type:  Season type code (``'rs'``, ``'po'``, ``'pi'``, ...).
        league_key:   League key (e.g. ``'nba'``).  Used for stats scope.
        source_key:   Source registry key.  Defaults to the league's reader.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    if source_key is None:
        source_key = get_default_external_source(league_key)

    if scope == 'entity':
        approved_rows = approve_entities(
            entity,
            rows,
            league_key=league_key,
            source_key=source_key,
            season=season,
            season_type=season_type,
        )
        return _write_profile_rows(entity, approved_rows, source_key)

    if scope == 'stats':
        return _write_stats_rows(
            entity, rows, season, season_type, league_key, source_key,
        )

    raise ValueError(f"Unsupported scope: {scope!r}")


def _write_profile_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    source_key: str,
) -> int:
    """Upsert ``{source_id: {col: val}}`` rows into ``core.{entity}_profiles``.

    Conflict key: ``{source_key}_id`` (UNIQUE).  ``the_glass_id`` is allocated
    automatically by the core sequence.
    """
    table = get_table_name(entity, 'entity')
    src_col = get_source_id_column(source_key)

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard(src_col)
    sorted_data_cols = sorted(data_cols)

    columns = [src_col] + sorted_data_cols
    data: List[tuple] = []
    for source_id, vals in rows.items():
        if source_id is None:
            continue
        row_values = [str(source_id)] + [vals.get(c) for c in sorted_data_cols]
        data.append(tuple(row_values))

    if not data:
        return 0

    with db_connection() as conn:
        return bulk_upsert(
            conn, table, columns, data, conflict_columns=[src_col],
        )


def _write_stats_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    source_key: str,
) -> int:
    """Upsert source-id-keyed stats rows into ``{league}.{entity}_season_stats``.

    Resolves the row key (entity source_id) to ``the_glass_id`` and translates
    every FK-bearing data column from source-id to the_glass_id form.  Rows
    that cannot be fully resolved are skipped.
    """
    table = get_table_name(entity, 'stats', league_key=league_key)
    bare_table = table.split('.', 1)[1]
    meta = STATS_TABLES[bare_table]
    pk_columns: List[str] = meta['primary_key']

    with db_connection() as conn:
        # Resolve the row-key source ids -> the_glass_id for the entity
        glass_ids = _load_glass_id_map(conn, entity, source_key, list(rows.keys()))

        translated: Dict[Any, Dict[str, Any]] = {}
        unresolved_keys = 0
        for source_id, vals in rows.items():
            glass_id = glass_ids.get(str(source_id))
            if glass_id is None:
                unresolved_keys += 1
                continue
            row = dict(vals)
            row[THE_GLASS_ID_COLUMN] = glass_id
            row['season'] = season
            row['season_type'] = season_type
            translated[source_id] = row

        if unresolved_keys:
            logger.warning(
                'Skipping %d %s stats rows: source_id not found in core profile',
                unresolved_keys, entity,
            )

        # Translate any remaining source-id columns to the_glass_id (e.g. team_id)
        translated, dropped = _resolve_fk_value_columns(
            translated, conn, league_key, source_key, bare_table,
        )
        if dropped:
            logger.warning(
                'Skipping %d %s stats rows: FK source_id unresolved',
                dropped, entity,
            )

        if not translated:
            return 0

        # Build the column order: PK first, then sorted data columns
        all_cols: Set[str] = set()
        for r in translated.values():
            all_cols.update(r.keys())
        non_pk_cols = sorted(c for c in all_cols if c not in set(pk_columns))
        columns = list(pk_columns) + non_pk_cols

        data = [tuple(r.get(c) for c in columns) for r in translated.values()]

        return bulk_upsert(
            conn, table, columns, data, conflict_columns=pk_columns,
        )
