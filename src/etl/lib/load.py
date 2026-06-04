"""
The Glass - ETL Database Loader

Bulk-write primitives and high-level row writers used by the executor.

ID model:
    Profile tables (``profiles.{entity}s`` — e.g. ``profiles.players``)
        - PK: ``the_glass_id`` (auto-allocated by ``profiles.the_glass_id_seq``)
        - Per-source identity columns: ``{source}_id`` (UNIQUE)
        - Conflict key on upsert is the per-source identity column

    Stats tables (``stats.{entity}_seasons`` — e.g. ``stats.player_seasons``)
        - PK: composite, includes ``the_glass_id`` and (for player) ``team_id``
        - Source IDs are resolved to the_glass_id values before write
        - Rows that cannot resolve all FK references are dropped with a warning
"""

import logging
from io import StringIO
from typing import Any, Dict, List, Set, Union

from psycopg2.extras import execute_values

from src.core.lib.postgres import db_connection, quote_col
from src.core.definitions.schema import TABLES
from src.etl.lib.sources_resolver import get_default_external_source, get_source_id_column
from src.etl.lib.fk_resolver import load_fk_mapping, resolve_fk_value_columns
from src.etl.definitions.execution import DEFAULT_BATCH_SIZE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bulk primitives
# ---------------------------------------------------------------------------

def bulk_upsert(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
    conflict_columns: List[str],
    update_columns: Union[List[str], None] = None,
    skip_unchanged: bool = False,
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
        if skip_unchanged:
            conflict_clause = (
                f'ON CONFLICT ({conflict_sql}) DO UPDATE SET '
                f'{update_sql}, updated_at = NOW() '
                f'WHERE (target.*) IS DISTINCT FROM (EXCLUDED.*)'
            )
            table_sql = f'{table} AS target'
        else:
            conflict_clause = (
                f'ON CONFLICT ({conflict_sql}) DO UPDATE SET '
                f'{update_sql}, updated_at = NOW()'
            )
            table_sql = table
    else:
        conflict_clause = f'ON CONFLICT ({conflict_sql}) DO NOTHING'
        table_sql = table

    query = f'INSERT INTO {table_sql} ({cols_sql}) VALUES %s {conflict_clause}'

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


def _bulk_merge_upsert(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
    conflict_columns: List[str],
    update_columns: Union[List[str], None] = None,
    skip_unchanged: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """``INSERT ... ON CONFLICT DO UPDATE`` merge that preserves non-null values."""
    if not data:
        return 0

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    cols_sql = ', '.join(quote_col(c) for c in columns)
    conflict_sql = ', '.join(quote_col(c) for c in conflict_columns)
    update_sql = ', '.join(
        f'{quote_col(c)} = COALESCE(EXCLUDED.{quote_col(c)}, {table}.{quote_col(c)})'
        for c in update_columns
    )
    if skip_unchanged and update_columns:
        conflict_clause = (
            f'ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql} '
            f'WHERE (target.*) IS DISTINCT FROM (EXCLUDED.*)'
        )
        table_sql = f'{table} AS target'
    else:
        conflict_clause = (
            f'ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}'
            if update_columns else
            f'ON CONFLICT ({conflict_sql}) DO NOTHING'
        )
        table_sql = table

    query = f'INSERT INTO {table_sql} ({cols_sql}) VALUES %s {conflict_clause}'
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


# ---------------------------------------------------------------------------
# ID resolution helpers
# ---------------------------------------------------------------------------

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
    source_key: Union[str, None] = None,
) -> int:
    """Write extracted rows to the database.

    Args:
        entity:       ``'league'``, ``'team'`` or ``'player'``.
        scope:        ``'profiles'`` or ``'stats'``.
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

    if scope == 'profiles':
        return write_staged_entity_rows(entity, rows, league_key, source_key)

    if scope == 'stats':
        return _write_stats_rows(
            entity, rows, season, season_type, league_key, source_key,
        )

    raise ValueError(f"Unsupported scope: {scope!r}")


def write_staged_entity_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    league_key: str,
    source_key: str,
) -> int:
    """Replace the staged snapshot for ``league_key``/``source_key``."""
    _STAGING_TABLES = {'player': 'staging.unmatched_players', 'team': 'staging.unmatched_teams'}
    table = _STAGING_TABLES[entity]

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard('league_id')
    data_cols.discard('source')
    data_cols.discard('source_id')
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT the_glass_id FROM profiles.leagues WHERE code = %s",
                (league_key,),
            )
            row = cur.fetchone()
            league_id = int(row[0]) if row else None

        if league_id is None:
            raise ValueError(f"League {league_key!r} not found in profiles.leagues")

        columns = ['league_id', 'source', 'source_id'] + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            row_values = [league_id, source_key, str(source_id)] + [vals.get(c) for c in sorted_data_cols]
            data.append(tuple(row_values))

        if not data:
            return 0

        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {table} WHERE league_id = %s AND source = %s",
                (league_id, source_key),
            )
        return bulk_copy(conn, table, columns, data)


def merge_staged_entity_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    league_key: str,
    source_key: str,
) -> int:
    """Merge roster or overlay fields into an existing staged snapshot."""
    _STAGING_TABLES = {'player': 'staging.unmatched_players', 'team': 'staging.unmatched_teams'}
    table = _STAGING_TABLES[entity]

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard('league_id')
    data_cols.discard('source')
    data_cols.discard('source_id')
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT the_glass_id FROM profiles.leagues WHERE code = %s",
                (league_key,),
            )
            row = cur.fetchone()
            league_id = int(row[0]) if row else None

        if league_id is None:
            raise ValueError(f"League {league_key!r} not found in profiles.leagues")

        columns = ['league_id', 'source', 'source_id'] + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            row_values = [league_id, source_key, str(source_id)] + [vals.get(c) for c in sorted_data_cols]
            data.append(tuple(row_values))

        if not data:
            return 0

        return _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=['league_id', 'source', 'source_id'],
            skip_unchanged=True,
        )


def write_core_profile_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    source_key: str,
) -> int:
    """Upsert ``{source_id: {col: val}}`` rows into ``profiles.{entity}s``.

    Conflict key: per-source identity column (UNIQUE).  ``the_glass_id`` is allocated
    automatically by the sequence.
    """
    _PROFILE_TABLES = {'player': 'profiles.players', 'team': 'profiles.teams'}
    table = _PROFILE_TABLES[entity]
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
            skip_unchanged=True,
        )


def _write_stats_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    source_key: str,
) -> int:
    """Upsert source-id-keyed stats rows into ``stats.{entity}_seasons``.

    Resolves the row key (entity source_id) to ``{entity}_id`` (the internal
    ``the_glass_id``) and translates every FK-bearing data column from source-id
    to ``the_glass_id`` form.  Rows that cannot be fully resolved are skipped.
    """
    _STATS_TABLES = {'player': 'stats.player_seasons', 'team': 'stats.team_seasons'}
    table = _STATS_TABLES[entity]
    schema_name, bare_name = table.split('.', 1)
    qualified_key = f'{schema_name}.{bare_name}'
    meta = TABLES[qualified_key]
    pk_columns: List[str] = meta['primary_key']
    entity_id_col = f'{entity}_id'

    with db_connection() as conn:
        # Resolve the row-key source ids -> the_glass_id via the profile table
        _PROFILE_TABLES = {'player': 'profiles.players', 'team': 'profiles.teams'}
        entity_table = _PROFILE_TABLES[entity]
        _, entity_bare = entity_table.split('.', 1)
        glass_ids = load_fk_mapping(
            conn, 'profiles', entity_bare, 'the_glass_id', source_key, list(rows.keys()),
        )

        translated: Dict[Any, Dict[str, Any]] = {}
        unresolved_keys = 0
        for source_id, vals in rows.items():
            glass_id = glass_ids.get(str(source_id))
            if glass_id is None:
                unresolved_keys += 1
                continue
            row = dict(vals)
            row[entity_id_col] = glass_id
            row['season'] = season
            row['season_type'] = season_type
            translated[source_id] = row

        if unresolved_keys:
            logger.warning(
                'Skipping %d %s stats rows: source_id not found in core profile',
                unresolved_keys, entity,
            )

        # Translate any remaining source-id columns to the_glass_id (e.g. team_id)
        translated, dropped = resolve_fk_value_columns(
            translated, conn, league_key, source_key, qualified_key,
        )
        if dropped:
            logger.warning(
                'Skipping %d %s stats rows: FK source_id unresolved',
                dropped, entity,
            )

        if not translated:
            return 0

        # Inject league_id after FK resolution so it is not double-resolved.
        # Leagues are keyed by league_key, not by source_id.
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT the_glass_id FROM profiles.leagues WHERE code = %s',
                (league_key,),
            )
            row = cur.fetchone()
            league_id = int(row[0]) if row else None

        if league_id is not None:
            for row in translated.values():
                row['league_id'] = league_id

        # Build the column order: PK first, then sorted data columns
        all_cols: Set[str] = set()
        for r in translated.values():
            all_cols.update(r.keys())
        non_pk_cols = sorted(c for c in all_cols if c not in set(pk_columns))
        columns = list(pk_columns) + non_pk_cols

        data = [tuple(r.get(c) for c in columns) for r in translated.values()]

        return bulk_upsert(
            conn, table, columns, data, conflict_columns=pk_columns,
            skip_unchanged=True,
        )
