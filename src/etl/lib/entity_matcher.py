"""Staged entity promotion and roster matching.

This module promotes staged entity rows into the core profile tables and then
materializes roster relationships from staged source ids.
"""

import logging
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from psycopg2.extras import RealDictCursor

from src.core.definitions.schema import TABLES, THE_GLASS_ID
from src.core.lib.tables_resolver import get_table_name
from src.etl.lib.fk_resolver import load_fk_mapping
from src.core.lib.postgres import db_connection, quote_col
from src.core.definitions.db_columns import DB_COLUMNS
from src.etl.lib.load import write_core_profile_rows

logger = logging.getLogger(__name__)

# Cache for config-driven column table lookups
_TABLE_COLS_CACHE: Dict[str, set] = {}


def _get_table_columns(table_name: str) -> set:
    """Return column names that belong to *table_name* (including 'all' wildcard)."""
    if table_name not in _TABLE_COLS_CACHE:
        _TABLE_COLS_CACHE[table_name] = {
            col_name
            for col_name, col_def in DB_COLUMNS.items()
            if table_name in (col_def.get('tables') or [])
            or 'all' in (col_def.get('tables') or [])
        }
    return _TABLE_COLS_CACHE[table_name]


def _fetch_staged_rows(
    conn: Any,
    entity: str,
    league_id: int,
    source_key: str,
) -> List[Dict[str, Any]]:
    table_name = get_table_name(entity, 'staging')
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE league_id = %s
              AND source = %s
            ORDER BY source_id
            """,
            (league_id, source_key),
        )
        return list(cur.fetchall())


def _filter_staged_rows_by_table(
    rows: Sequence[Dict[str, Any]],
    table_name: str,
) -> Dict[Any, Dict[str, Any]]:
    """Filter staged rows down to columns defined for the given table.

    The returned mapping is keyed by ``source_id`` so that downstream writers
    can resolve each row to a ``the_glass_id``.
    """
    table_cols = _get_table_columns(table_name)
    result: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        source_id = row.get('source_id')
        if source_id is None:
            continue
        payload = {
            key: value
            for key, value in row.items()
            if key in table_cols
        }
        result[source_id] = payload
    return result


def _league_glass_id(conn: Any, league_key: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {quote_col(THE_GLASS_ID)}
            FROM {get_table_name('league', 'profiles')}
            WHERE code = %s
            """,
            (league_key,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f'League {league_key!r} is missing from profiles.leagues')
        return int(row[0])


def _upsert_pairs(conn: Any, table_name: str, column_names: Tuple[str, str], pairs: Iterable[Tuple[int, int]]) -> int:
    values = list(pairs)
    if not values:
        return 0

    first_column, second_column = column_names
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO {table_name} ({quote_col(first_column)}, {quote_col(second_column)})
            VALUES (%s, %s)
            ON CONFLICT ({quote_col(first_column)}, {quote_col(second_column)}) DO NOTHING
            """,
            values,
        )
    return len(values)


def _upsert_roster_rows(conn: Any, rows: Iterable[Dict[str, Any]]) -> int:
    """Upsert roster rows into the player rosters table with all rosters-scoped columns."""
    values = list(rows)
    if not values:
        return 0

    table = get_table_name('player', 'rosters')
    pk_cols = TABLES[table.split('.', 1)[1]]['primary_key']

    extra_cols = sorted({
        k for row in values for k in row.keys()
        if k not in pk_cols
    })

    all_cols = pk_cols + extra_cols
    col_list = ', '.join(quote_col(c) for c in all_cols)
    placeholders = ', '.join('%s' for _ in all_cols)
    conflict_cols = ', '.join(quote_col(c) for c in pk_cols)

    if extra_cols:
        updates = [
            f"{quote_col(c)} = COALESCE(EXCLUDED.{quote_col(c)}, {table}.{quote_col(c)})"
            for c in extra_cols
        ]
        update_clause = ', '.join(updates)
        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_cols}) DO UPDATE
            SET {update_clause}
        """
    else:
        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_cols}) DO NOTHING
        """

    params = [tuple(row.get(c) for c in all_cols) for row in values]

    with conn.cursor() as cur:
        cur.executemany(sql, params)

    return len(values)


def promote_staged_entities(league_key: str, source_key: str) -> Dict[str, int]:
    """Promote staged entity rows into core tables and materialize roster links."""
    with db_connection() as conn:
        league_id = _league_glass_id(conn, league_key)
        team_rows = _fetch_staged_rows(conn, 'team', league_id, source_key)
        player_rows = _fetch_staged_rows(conn, 'player', league_id, source_key)

        if not team_rows and not player_rows:
            return {
                'teams_promoted': 0,
                'players_promoted': 0,
                'league_rosters_written': 0,
                'team_rosters_written': 0,
            }

        teams_promoted = write_core_profile_rows('team', _filter_staged_rows_by_table(team_rows, 'teams'), source_key)
        players_promoted = write_core_profile_rows('player', _filter_staged_rows_by_table(player_rows, 'players'), source_key)

        team_source_ids = [row['source_id'] for row in team_rows if row.get('source_id') is not None]
        player_source_ids = [row['source_id'] for row in player_rows if row.get('source_id') is not None]

        team_map = load_fk_mapping(
            conn,
            'profiles',
            'teams',
            THE_GLASS_ID,
            source_key,
            team_source_ids,
        )
        player_map = load_fk_mapping(
            conn,
            'profiles',
            'players',
            THE_GLASS_ID,
            source_key,
            player_source_ids,
        )
        league_roster_pairs = [
            (league_id, team_map[str(row['source_id'])])
            for row in team_rows
            if row.get('source_id') is not None and str(row['source_id']) in team_map
        ]
        rosters_cols = _get_table_columns('teams_players')
        roster_value_cols = {c for c in rosters_cols if c not in {'team_id', 'player_id', 'league_id'}}

        roster_pairs = [
            {
                'team_id': team_map[str(row['team_source_id'])],
                'player_id': player_map[str(row['source_id'])],
                **{
                    col: row.get(col)
                    for col in roster_value_cols
                    if col in row
                },
            }
            for row in player_rows
            if row.get('source_id') is not None
            and row.get('team_source_id') is not None
            and str(row['source_id']) in player_map
            and str(row['team_source_id']) in team_map
        ]

        league_rosters_written = _upsert_pairs(conn, get_table_name('team', 'rosters'), ('league_id', 'team_id'), league_roster_pairs)
        team_rosters_written = _upsert_roster_rows(conn, roster_pairs)

        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {get_table_name('team', 'staging')} WHERE league_id = %s AND source = %s",
                (league_id, source_key),
            )
            cur.execute(
                f"DELETE FROM {get_table_name('player', 'staging')} WHERE league_id = %s AND source = %s",
                (league_id, source_key),
            )

    counts = {
        'teams_promoted': teams_promoted,
        'players_promoted': players_promoted,
        'league_rosters_written': league_rosters_written,
        'team_rosters_written': team_rosters_written,
    }
    logger.info(
        'Promoted staged entities %s/%s: teams=%d players=%d league_rosters=%d team_rosters=%d',
        league_key,
        source_key,
        counts['teams_promoted'],
        counts['players_promoted'],
        counts['league_rosters_written'],
        counts['team_rosters_written'],
    )
    return counts
