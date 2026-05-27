"""
The Glass - Roster Maintainer

Single responsibility: keep the two membership roster tables in the ``core``
schema in sync with a roster snapshot pulled from the league's reader source.

    core.league_rosters  : (league_id, team_id, is_active, ...)
    core.team_rosters    : (team_id,   player_id, is_active, ...)

A sync run accepts a snapshot of ``(team_source_id, player_source_id)``
pairs, resolves each to its ``the_glass_id`` via the relevant
``core.*_profiles`` table, and:

    1. Upserts every (league, team) pair into league_rosters  (is_active=TRUE).
    2. Upserts every (team, player) pair into team_rosters    (is_active=TRUE).
    3. Deactivates rows that existed before but are absent from the snapshot.

Source-agnostic: callers (the orchestrator) supply already-fetched pairs.
Source-specific dataset logic stays in each source client.  The league
profile row itself is bootstrapped by :func:`src.core.lib.ddl.ensure_league_profile`.
"""

import logging
from typing import Any, Dict, Iterable, List, Set, Tuple

from src.core.definitions.leagues import LEAGUES
from src.core.lib.postgres import db_connection, quote_col
from src.core.definitions.tables import CORE_SCHEMA, THE_GLASS_ID_COLUMN
from src.core.lib.fk_resolver import load_fk_mapping

logger = logging.getLogger(__name__)







# ---------------------------------------------------------------------------
# Gender propagation
# ---------------------------------------------------------------------------

def _stamp_gender(conn: Any, league_glass_id: int) -> Tuple[int, int]:
    """Propagate the league's gender to all active team and player profiles.

    Looks up the gender from ``core.league_profiles`` and issues two bulk
    UPDATEs -- one for active teams in ``league_rosters``, one for active
    players whose team is active in ``league_rosters``.

    Returns ``(teams_stamped, players_stamped)``.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT gender FROM {CORE_SCHEMA}.league_profiles "
            f"WHERE {quote_col(THE_GLASS_ID_COLUMN)} = %s",
            (league_glass_id,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return 0, 0
        gender = row[0]

        cur.execute(
            f"""
            UPDATE {CORE_SCHEMA}.team_profiles
            SET gender = %s, updated_at = NOW()
            WHERE {quote_col(THE_GLASS_ID_COLUMN)} IN (
                SELECT team_id FROM {CORE_SCHEMA}.league_rosters
                WHERE league_id = %s
            )
            """,
            (gender, league_glass_id),
        )
        teams_stamped = cur.rowcount

        cur.execute(
            f"""
            UPDATE {CORE_SCHEMA}.player_profiles
            SET gender = %s, updated_at = NOW()
            WHERE {quote_col(THE_GLASS_ID_COLUMN)} IN (
                SELECT tr.player_id
                FROM {CORE_SCHEMA}.team_rosters tr
                JOIN {CORE_SCHEMA}.league_rosters lr ON lr.team_id = tr.team_id
                WHERE lr.league_id = %s
            )
            """,
            (gender, league_glass_id),
        )
        players_stamped = cur.rowcount

    return teams_stamped, players_stamped


# ---------------------------------------------------------------------------
# Roster upsert primitives
# ---------------------------------------------------------------------------

def _upsert_roster_pairs(
    conn: Any,
    table: str,
    pk_columns: Tuple[str, str],
    rows: Iterable[Tuple[int, int]],
) -> int:
    """Insert each (a, b) pair into current rosters; on conflict do nothing."""
    rows = list(rows)
    if not rows:
        return 0
    a_col, b_col = pk_columns
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO {table} ({quote_col(a_col)}, {quote_col(b_col)})
            VALUES (%s, %s)
            ON CONFLICT ({quote_col(a_col)}, {quote_col(b_col)}) DO NOTHING
            """,
            rows,
        )
    return len(rows)


def _upsert_active_team_rosters(
    conn: Any,
    table: str,
    rows: Iterable[Tuple[int, int, Any]],
) -> int:
    """Upsert active team-player memberships with optional jersey number."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO {table} (team_id, player_id, jersey_num)
            VALUES (%s, %s, %s)
            ON CONFLICT (team_id, player_id) DO UPDATE
            SET jersey_num = COALESCE(EXCLUDED.jersey_num, {table}.jersey_num),
                updated_at = NOW()
            """,
            [(team_id, player_id, jersey_num) for team_id, player_id, jersey_num in rows],
        )
    return len(rows)


def _normalize_roster_snapshot(
    roster_pairs: Iterable[Tuple[Any, ...]],
) -> List[Tuple[Any, Any, Any]]:
    """Normalize roster snapshots to ``(team_source_id, player_source_id, jersey_num)``.

    Accepts legacy 2-tuples and newer 3-tuples; invalid entries are skipped.
    """
    normalized: List[Tuple[Any, Any, Any]] = []
    for entry in roster_pairs:
        if not isinstance(entry, (tuple, list)):
            continue
        if len(entry) < 2:
            continue
        team_source_id, player_source_id = entry[0], entry[1]
        jersey_num = entry[2] if len(entry) >= 3 else None
        if team_source_id is None or player_source_id is None:
            continue
        normalized.append((team_source_id, player_source_id, jersey_num))
    return normalized


def _delete_missing(
    conn: Any,
    table: str,
    pk_columns: Tuple[str, str],
    scope_filter_col: str,
    scope_filter_value: int,
    keep_pairs: Set[Tuple[int, int]],
) -> int:
    """Delete every row in ``table`` whose pair is NOT in ``keep_pairs``.
    Scoped to ``scope_filter_col = scope_filter_value``.
    """
    a_col, b_col = pk_columns
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {quote_col(a_col)}, {quote_col(b_col)}
            FROM {table}
            WHERE {quote_col(scope_filter_col)} = %s
            """,
            (scope_filter_value,),
        )
        existing = {(int(r[0]), int(r[1])) for r in cur.fetchall()}
        to_delete = existing - keep_pairs
        if not to_delete:
            return 0
        cur.executemany(
            f"""
            DELETE FROM {table}
            WHERE {quote_col(a_col)} = %s AND {quote_col(b_col)} = %s
            """,
            to_delete,
        )
    return len(to_delete)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_rosters(
    league_key: str,
    source_key: str,
    roster_pairs: Iterable[Tuple[Any, ...]],
    season: str = None,
) -> Dict[str, int]:
    """Apply a roster snapshot to ``core.league_rosters`` and ``core.team_rosters``.

    Args:
        league_key:    LEAGUES key (e.g. ``'nba'``).
        source_key:    SOURCES key (e.g. ``'nba_api'``).
        roster_pairs:  Iterable of ``(team_source_id, player_source_id)`` or
                       ``(team_source_id, player_source_id, jersey_num)`` tuples
                       representing every active roster slot in the league.
        season:        Optional season label (ignored).

    Returns:
        Dict with the per-roster counters
        ``{teams_active, players_active, teams_deactivated, players_deactivated,
           teams_unresolved, players_unresolved}``.
    """
    pairs = _normalize_roster_snapshot(roster_pairs)
    league_abbr = LEAGUES[league_key]['abbr']

    league_rosters = f'{CORE_SCHEMA}.league_rosters'
    team_rosters = f'{CORE_SCHEMA}.team_rosters'

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {quote_col(THE_GLASS_ID_COLUMN)} "
                f"FROM {CORE_SCHEMA}.league_profiles WHERE abbr = %s",
                (league_abbr,),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"League {league_key!r} not found in core.league_profiles. "
                    "ensure_league_profile must be called before sync_rosters."
                )
            league_glass_id = int(row[0])

        team_source_ids = {t for t, _, _ in pairs}
        player_source_ids = {p for _, p, _ in pairs}

        team_map = load_fk_mapping(conn, 'team', source_key, team_source_ids)
        player_map = load_fk_mapping(conn, 'player', source_key, player_source_ids)

        teams_unresolved = {sid for sid in team_source_ids if str(sid) not in team_map}
        players_unresolved = {sid for sid in player_source_ids if str(sid) not in player_map}

        # Do NOT create profile stubs here. Instead, log unresolved ids and
        # skip them. Entity creation should be a separate staged operation.
        if teams_unresolved:
            logger.warning('Found %d unresolved team source_ids; skipping', len(teams_unresolved))
        if players_unresolved:
            logger.warning('Found %d unresolved player source_ids; skipping', len(players_unresolved))

        # ---- league_rosters: (league_glass_id, team_glass_id) -----------------
        league_team_pairs: Set[Tuple[int, int]] = {
            (league_glass_id, team_map[str(t)])
            for t in team_source_ids
            if str(t) in team_map
        }
        teams_active = _upsert_roster_pairs(
            conn, league_rosters, ('league_id', 'team_id'), league_team_pairs,
        )
        teams_deactivated = _delete_missing(
            conn, league_rosters, ('league_id', 'team_id'),
            scope_filter_col='league_id',
            scope_filter_value=league_glass_id,
            keep_pairs=league_team_pairs,
        )

        # ---- team_rosters: (team_glass_id, player_glass_id) -------------------
        team_player_pairs: Set[Tuple[int, int]] = set()
        team_player_jersey: Dict[Tuple[int, int], Any] = {}
        for team_src, player_src, jersey_num in pairs:
            t = team_map.get(str(team_src))
            p = player_map.get(str(player_src))
            if t is not None and p is not None:
                team_player_pairs.add((t, p))
                if jersey_num is not None:
                    team_player_jersey[(t, p)] = str(jersey_num)

        players_active = _upsert_active_team_rosters(
            conn,
            team_rosters,
            [
                (team_id, player_id, team_player_jersey.get((team_id, player_id)))
                for team_id, player_id in sorted(team_player_pairs)
            ],
        )

        # Per-team deactivation: each team's slate is independent.
        teams_in_snapshot: Set[int] = {t for t, _ in team_player_pairs}
        players_deactivated = 0
        for team_glass_id in teams_in_snapshot:
            keep = {pair for pair in team_player_pairs if pair[0] == team_glass_id}
            players_deactivated += _delete_missing(
                conn, team_rosters, ('team_id', 'player_id'),
                scope_filter_col='team_id',
                scope_filter_value=team_glass_id,
                keep_pairs=keep,
            )

        # Propagate league gender to all active teams and players.
        teams_stamped, players_stamped = _stamp_gender(conn, league_glass_id)
        if teams_stamped or players_stamped:
            logger.info(
                'Gender stamped: %d teams, %d players',
                teams_stamped, players_stamped,
            )

    counts = {
        'teams_active': teams_active,
        'teams_deactivated': teams_deactivated,
        'teams_created': len(teams_unresolved),
        'players_active': players_active,
        'players_deactivated': players_deactivated,
        'players_created': len(players_unresolved),
    }
    logger.info(
        'Roster sync %s/%s: teams active=%d deactivated=%d created=%d | '
        'players active=%d deactivated=%d created=%d',
        league_key, source_key,
        counts['teams_active'], counts['teams_deactivated'], counts['teams_created'],
        counts['players_active'], counts['players_deactivated'], counts['players_created'],
    )
    return counts
