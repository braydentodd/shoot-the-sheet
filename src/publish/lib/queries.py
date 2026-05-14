"""
The Glass - Shared Data Access Layer (DAL)

Read-only SQL helpers used by the publish pipeline.

ID model:
    Profile tables  -> core.{entity}_profiles  (PK: the_glass_id)
    Stats tables    -> {league}.{entity}_season_stats
                       PK includes the_glass_id (and team_id for players)
    Membership      -> core.league_rosters (league/team), core.team_rosters (team/player)

The "team for a player" is derived from each stats row's ``team_id``
column, NOT from a column on the profile -- a player can play for several
teams in a season and we want each row to reflect which team accumulated
the stats.

Opponent stats live as ``opp_<col>`` columns on the same team-stats row.
The legacy ``is_opponent`` row flag has been removed.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from src.core.lib.postgres import get_db_connection
from src.core.definitions.tables import CORE_SCHEMA, THE_GLASS_ID_COLUMN
from src.core.definitions.stats import SEASON_TYPE_GROUPS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESERVED_COLUMNS = {'limit', 'offset', 'all', 'user', 'year', 'season', 'age', 'rank'}


def _quote_col(col: str) -> str:
    """Quote ``col`` if it could collide with a SQL reserved word."""
    if col.lower() in _RESERVED_COLUMNS:
        return f'"{col}"'
    return col


def _season_types_for_section(section: str) -> tuple:
    """Return the season_type codes a section covers."""
    if section == 'historical_stats':
        return SEASON_TYPE_GROUPS['regular_season']
    return SEASON_TYPE_GROUPS['postseason']


def _build_entity_fields(
    entity_fields: List[str],
    table_alias: str = 'p',
) -> Tuple[List[str], List[str]]:
    """Render SELECT fragments for entity fields and matching GROUP BY refs."""
    select_f: List[str] = []
    group_f: List[str] = []
    for f in sorted(entity_fields):
        select_f.append(f'{table_alias}.{_quote_col(f)}')
        group_f.append(f'{table_alias}.{_quote_col(f)}')
    return select_f, group_f


def _build_season_filter(
    historical_config: Optional[dict],
    current_season_year: int,
    season_col: str,
    season_format_fn,
) -> Tuple[str, tuple]:
    """Build a ``AND s.<season_col> IN %s`` filter and matching params tuple."""
    if not historical_config:
        seasons = tuple(season_format_fn(current_season_year - i) for i in range(1, 4))
        return f"AND s.{season_col} IN %s", (seasons,)

    value = historical_config.get('value', 3)
    if isinstance(value, int):
        seasons = tuple(season_format_fn(current_season_year - i) for i in range(1, 1 + value))
        return f"AND s.{season_col} IN %s", (seasons,)
    if isinstance(value, list):
        return f"AND s.{season_col} IN %s", (tuple(value),)
    return "", ()


def _split_team_opponent(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Separate a team-stats row into (team, opponent) dicts based on the
    ``opp_`` column-name prefix.  Profile and bare stat columns go to ``team``;
    every ``opp_<col>`` becomes ``<col>`` on the opponent dict.
    """
    team_part: Dict[str, Any] = {}
    opp_part: Dict[str, Any] = {}
    for col, val in row.items():
        if col.startswith('opp_'):
            opp_part[col[4:]] = val
        else:
            team_part[col] = val
    return team_part, opp_part


# ---------------------------------------------------------------------------
# Team listing
# ---------------------------------------------------------------------------

def get_teams_from_db(league_key: str) -> Dict[int, Tuple[str, str]]:
    """Return ``{the_glass_id: (abbr, name)}`` for teams currently active in
    ``core.league_rosters`` for ``league_key``.
    """
    sql = f"""
        SELECT t.{_quote_col(THE_GLASS_ID_COLUMN)}, t.abbr, t.name
          FROM {CORE_SCHEMA}.team_profiles t
          JOIN {CORE_SCHEMA}.league_rosters lr
            ON lr.team_id = t.{_quote_col(THE_GLASS_ID_COLUMN)}
          JOIN {CORE_SCHEMA}.league_profiles lp
            ON lp.{_quote_col(THE_GLASS_ID_COLUMN)} = lr.league_id
         WHERE lp.league_key = %s AND lr.is_active = TRUE
         ORDER BY t.abbr
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (league_key,))
            return {int(row[0]): (row[1], row[2]) for row in cur.fetchall()}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Player queries
# ---------------------------------------------------------------------------

def fetch_players_for_team(
    conn,
    team_abbr: str,
    section: str,
    historical_config: Optional[dict],
    ctx,
    current_season: str,
    current_season_year: int,
    season_type_val,
    season_col_name: str = 'season',
) -> List[dict]:
    """Players + per-team stats for a single team.

    ``current_stats``: lists every player on the team's *active* roster and
        joins their stats row for ``current_season`` / ``season_type_val``.
        Players without a stats row appear with NULL stat columns.

    ``historical_stats`` / ``postseason``: lists every player who has stats
        rows for this team in the season window, aggregated.
    """
    players_tbl = ctx.player_entity_table
    teams_tbl = ctx.team_entity_table
    stats_tbl = ctx.player_stats_table
    abbr_col = _quote_col(ctx.team_abbr_col)
    glass_id = _quote_col(THE_GLASS_ID_COLUMN)

    p_select, p_group = _build_entity_fields(ctx.player_entity_fields, 'p')
    team_abbr_select = f"t.{abbr_col} AS team_abbr"

    if section == 'current_stats':
        s_fields = [f's.{_quote_col(f)}' for f in sorted(ctx.stat_fields)]
        all_fields = p_select + [team_abbr_select] + s_fields

        query = f"""
            SELECT {', '.join(all_fields)}
              FROM {players_tbl} p
              JOIN {CORE_SCHEMA}.team_rosters tr
                ON tr.player_id = p.{glass_id} AND tr.is_active = TRUE
              JOIN {teams_tbl} t
                ON t.{glass_id} = tr.team_id
              LEFT JOIN {stats_tbl} s
                ON s.{glass_id} = p.{glass_id}
               AND s.team_id = t.{glass_id}
               AND s.{season_col_name} = %s
               AND s.season_type = %s
             WHERE t.{abbr_col} = %s
             ORDER BY COALESCE(s.{ctx.primary_minutes_col}, 0) DESC, p.name
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (current_season, season_type_val, team_abbr))
            return [dict(r) for r in cur.fetchall()]

    season_types = _season_types_for_section(section)
    season_filter, params = _build_season_filter(
        historical_config, current_season_year, season_col_name, ctx.season_format_fn,
    )

    s_sums = [f'SUM(s.{_quote_col(f)}) AS {_quote_col(f)}' for f in sorted(ctx.stat_fields)]
    s_sums.append(f'COUNT(DISTINCT s.{season_col_name}) AS {season_col_name}')
    all_aggregates = p_select + [team_abbr_select] + s_sums
    group_fields = p_group + [f't.{abbr_col}']

    query = f"""
        SELECT {', '.join(all_aggregates)}
          FROM {players_tbl} p
          JOIN {stats_tbl} s
            ON s.{glass_id} = p.{glass_id}
          JOIN {teams_tbl} t
            ON t.{glass_id} = s.team_id
         WHERE t.{abbr_col} = %s
           AND s.season_type IN %s
           {season_filter}
         GROUP BY {', '.join(group_fields)}
         ORDER BY SUM(COALESCE(s.{ctx.primary_minutes_col}, 0)) DESC, p.name
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (team_abbr, season_types, *params))
        return [dict(r) for r in cur.fetchall()]


def fetch_all_players(
    conn,
    section: str,
    historical_config: Optional[dict],
    ctx,
    current_season: str,
    current_season_year: int,
    season_type_val,
    season_col_name: str = 'season',
) -> List[dict]:
    """Every player's stats for percentile baselines (entire league)."""
    players_tbl = ctx.player_entity_table
    teams_tbl = ctx.team_entity_table
    stats_tbl = ctx.player_stats_table
    abbr_col = _quote_col(ctx.team_abbr_col)
    glass_id = _quote_col(THE_GLASS_ID_COLUMN)

    ent_select, ent_group = _build_entity_fields(ctx.player_entity_fields, 'p')
    team_abbr_select = f"t.{abbr_col} AS team_abbr"

    if section == 'current_stats':
        stat_f = [f's.{_quote_col(f)}' for f in sorted(ctx.stat_fields)]
        all_f = stat_f + ent_select + [team_abbr_select]

        query = f"""
            SELECT {', '.join(all_f)}
              FROM {stats_tbl} s
              JOIN {players_tbl} p ON p.{glass_id} = s.{glass_id}
              JOIN {teams_tbl}   t ON t.{glass_id} = s.team_id
             WHERE s.{season_col_name} = %s AND s.season_type = %s
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (current_season, season_type_val))
            return [dict(r) for r in cur.fetchall()]

    season_types = _season_types_for_section(section)
    season_filter, params = _build_season_filter(
        historical_config, current_season_year, season_col_name, ctx.season_format_fn,
    )

    s_sums = [f'SUM(s.{_quote_col(f)}) AS {_quote_col(f)}' for f in sorted(ctx.stat_fields)]
    s_sums.append(f'COUNT(DISTINCT s.{season_col_name}) AS {season_col_name}')
    all_aggregates = s_sums + ent_select + [team_abbr_select]
    group_f = ent_group + [f't.{abbr_col}']

    query = f"""
        SELECT {', '.join(all_aggregates)}
          FROM {stats_tbl} s
          JOIN {players_tbl} p ON p.{glass_id} = s.{glass_id}
          JOIN {teams_tbl}   t ON t.{glass_id} = s.team_id
         WHERE s.season_type IN %s {season_filter}
         GROUP BY {', '.join(group_f)}
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (season_types, *params))
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Team queries
# ---------------------------------------------------------------------------

def fetch_team_stats(
    conn,
    team_abbr: str,
    section: str,
    historical_config: Optional[dict],
    ctx,
    current_season: str,
    current_season_year: int,
    season_type_val,
    season_col_name: str = 'season',
) -> dict:
    """Aggregated stats for a single team.

    Returns ``{'team': team_dict, 'opponent': opp_dict}`` where opponent
    columns are unprefixed (``opp_pts`` -> ``pts`` on the opponent dict).
    """
    teams_tbl = ctx.team_entity_table
    stats_tbl = ctx.team_stats_table
    abbr_col = _quote_col(ctx.team_abbr_col)
    glass_id = _quote_col(THE_GLASS_ID_COLUMN)

    entity_fields = [f for f in sorted(ctx.team_entity_fields) if f != 'updated_at']
    t_select, t_group = _build_entity_fields(entity_fields, 't')

    if section == 'current_stats':
        s_fields = [f's.{_quote_col(f)}' for f in sorted(ctx.team_stat_fields)]
        all_fields = t_select + s_fields + [f"t.{abbr_col} AS team_abbr"]
        query = f"""
            SELECT {', '.join(all_fields)}
              FROM {teams_tbl} t
              LEFT JOIN {stats_tbl} s
                ON s.{glass_id} = t.{glass_id}
               AND s.{season_col_name} = %s
               AND s.season_type = %s
             WHERE t.{abbr_col} = %s
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (current_season, season_type_val, team_abbr))
            rows = [dict(r) for r in cur.fetchall()]
    else:
        season_types = _season_types_for_section(section)
        season_filter, params = _build_season_filter(
            historical_config, current_season_year, season_col_name, ctx.season_format_fn,
        )
        s_sums = [f'SUM(s.{_quote_col(f)}) AS {_quote_col(f)}' for f in sorted(ctx.team_stat_fields)]
        s_sums.append(f'COUNT(DISTINCT s.{season_col_name}) AS {season_col_name}')
        all_aggregates = t_select + s_sums + [f"t.{abbr_col} AS team_abbr"]
        group_fields = t_group + [f't.{abbr_col}']
        query = f"""
            SELECT {', '.join(all_aggregates)}
              FROM {teams_tbl} t
              LEFT JOIN {stats_tbl} s
                ON s.{glass_id} = t.{glass_id}
               AND s.season_type IN %s
               {season_filter}
             WHERE t.{abbr_col} = %s
             GROUP BY {', '.join(group_fields)}
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (season_types, *params, team_abbr))
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {'team': {}, 'opponent': {}}
    team_dict, opp_dict = _split_team_opponent(rows[0])
    return {'team': team_dict, 'opponent': opp_dict}


def fetch_all_teams(
    conn,
    section: str,
    historical_config: Optional[dict],
    ctx,
    current_season: str,
    current_season_year: int,
    season_type_val,
    season_col_name: str = 'season',
) -> dict:
    """Aggregated stats for every active team in the league.

    Returns ``{'teams': [team_dict, ...], 'opponents': [opp_dict, ...]}`` --
    the two lists are aligned by team_abbr.
    """
    teams_tbl = ctx.team_entity_table
    stats_tbl = ctx.team_stats_table
    abbr_col = _quote_col(ctx.team_abbr_col)
    glass_id = _quote_col(THE_GLASS_ID_COLUMN)

    entity_fields = [f for f in sorted(ctx.team_entity_fields) if f != 'updated_at']
    t_select, t_group = _build_entity_fields(entity_fields, 't')

    if section == 'current_stats':
        s_fields = [f's.{_quote_col(f)}' for f in sorted(ctx.team_stat_fields)]
        all_fields = t_select + s_fields + [f"t.{abbr_col} AS team_abbr"]
        query = f"""
            SELECT {', '.join(all_fields)}
              FROM {stats_tbl} s
              JOIN {teams_tbl} t ON t.{glass_id} = s.{glass_id}
             WHERE s.{season_col_name} = %s AND s.season_type = %s
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (current_season, season_type_val))
            rows = [dict(r) for r in cur.fetchall()]
    else:
        season_types = _season_types_for_section(section)
        season_filter, params = _build_season_filter(
            historical_config, current_season_year, season_col_name, ctx.season_format_fn,
        )
        s_sums = [f'SUM(s.{_quote_col(f)}) AS {_quote_col(f)}' for f in sorted(ctx.team_stat_fields)]
        s_sums.append(f'COUNT(DISTINCT s.{season_col_name}) AS {season_col_name}')
        all_aggregates = t_select + s_sums + [f"t.{abbr_col} AS team_abbr"]
        group_fields = t_group + [f't.{abbr_col}']
        query = f"""
            SELECT {', '.join(all_aggregates)}
              FROM {stats_tbl} s
              JOIN {teams_tbl} t ON t.{glass_id} = s.{glass_id}
             WHERE s.season_type IN %s {season_filter}
             GROUP BY {', '.join(group_fields)}
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (season_types, *params))
            rows = [dict(r) for r in cur.fetchall()]

    teams: List[dict] = []
    opponents: List[dict] = []
    for row in rows:
        team_dict, opp_dict = _split_team_opponent(row)
        teams.append(team_dict)
        opponents.append(opp_dict)
    return {'teams': teams, 'opponents': opponents}
