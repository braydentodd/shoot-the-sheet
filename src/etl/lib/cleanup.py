"""
The Glass - ETL Cleanup

Two-phase data hygiene:

  Phase A: Per-league stats retention
        cleanup_stat_domains  - in-place coherency rules within a season's
                                stats rows (NULL/zero stats based on minutes).
        prune_stats_retention - DELETE stats rows older than the league's
                                retention window.

  Phase B: Cross-league profile pruning
        prune_orphan_profiles - DELETE rows from ``core.{entity}_profiles``
                                that have no stats rows in any league schema
                                AND no roster history.

Both phases are idempotent.  Phase B should be run only after every league
has finished its Phase A run for the day; running it during in-flight ETL
risks deleting an entity that's about to be referenced.
"""

import logging
from typing import Dict, List

from src.core.lib.postgres import db_connection, get_db_connection, quote_col
from src.core.definitions.leagues import LEAGUES
from src.core.definitions.tables import (
    CORE_SCHEMA,
    STATS_TABLES,
    THE_GLASS_ID_COLUMN,
)
from src.core.definitions.stats import STAT_DOMAINS
from src.core.lib.leagues_resolver import get_oldest_retained_season
from src.core.lib.tables_resolver import get_table_name
from src.core.definitions.columns import DB_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PHASE A.1 -- in-season stat coherency
# ---------------------------------------------------------------------------

def _collect_domain_columns(entity: str) -> Dict[str, List[str]]:
    """Return ``{domain_name: [counter columns]}`` for every non-primary
    domain whose stats apply to ``entity``.

    Counter columns are everything in the domain *except* its ``minutes_col``
    denominator.  Minutes is the single coherency signal: if it is 0 / NULL
    every other column in the domain (including ``games_col``) is nulled to
    keep the row internally consistent.
    """
    out: Dict[str, List[str]] = {}
    for col_name, col_meta in DB_COLUMNS.items():
        entity_types = col_meta.get('entity_types') or []
        if entity not in entity_types:
            continue
        domain = col_meta.get('domain')
        if not domain or domain not in STAT_DOMAINS:
            continue
        domain_cfg = STAT_DOMAINS[domain]
        if domain_cfg.get('primary', True):
            continue
        if col_name == domain_cfg['minutes_col']:
            continue
        out.setdefault(domain, []).append(col_name)
    return out


def cleanup_stat_domains(
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
) -> int:
    """Apply per-domain coherency rules to a stats-table slice.

    For each non-primary domain:
      - If the domain's minutes column is > 0, NULL stat columns are coalesced to 0.
      - If the domain's minutes column is NULL or 0, every stat column is set to NULL.

    Returns the total number of UPDATE rows touched (counts both passes).
    """
    table = get_table_name(entity, 'stats', league_key)
    domain_cols = _collect_domain_columns(entity)
    if not domain_cols:
        return 0

    affected = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for domain, cols in domain_cols.items():
                minutes_col = quote_col(STAT_DOMAINS[domain]['minutes_col'])

                set_to_zero = ', '.join(
                    f'{quote_col(c)} = COALESCE({quote_col(c)}, 0)' for c in cols
                )
                cur.execute(
                    f"UPDATE {table} SET {set_to_zero} "
                    f"WHERE season = %s AND season_type = %s AND {minutes_col} > 0",
                    (season, season_type),
                )
                affected += cur.rowcount

                set_to_null = ', '.join(f'{quote_col(c)} = NULL' for c in cols)
                cur.execute(
                    f"UPDATE {table} SET {set_to_null} "
                    f"WHERE season = %s AND season_type = %s "
                    f"  AND ({minutes_col} IS NULL OR {minutes_col} = 0)",
                    (season, season_type),
                )
                affected += cur.rowcount

    if affected:
        logger.info(
            'Domain cleanup %s/%s %s %s: %d rows updated',
            league_key, entity, season, season_type, affected,
        )
    return affected


# ---------------------------------------------------------------------------
# PHASE A.2 -- per-league stats retention pruning
# ---------------------------------------------------------------------------

def prune_stats_retention(league_key: str, current_season: str) -> int:
    """Delete stats rows older than the league's retention window.

    ``current_season`` defines the most recent season (e.g. ``'2025-26'``);
    the retention window is ``LEAGUES[league_key]['retention_seasons']``.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    oldest = get_oldest_retained_season(league_key, current_season)
    pruned = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for table_name, meta in STATS_TABLES.items():
                qualified = f'{league_key}.{table_name}'
                cur.execute(
                    f"DELETE FROM {qualified} WHERE season < %s",
                    (oldest,),
                )
                if cur.rowcount:
                    logger.info(
                        'Pruned %d rows from %s (season < %s)',
                        cur.rowcount, qualified, oldest,
                    )
                    pruned += cur.rowcount
    return pruned


# ---------------------------------------------------------------------------
# PHASE B -- cross-league orphan profile pruning
# ---------------------------------------------------------------------------

def _profile_has_stats_predicate(entity: str) -> str:
    """Build a SQL EXISTS predicate that's TRUE if a profile has stats in any league.

    The predicate references ``p.{the_glass_id}`` and assumes the outer query
    aliases the profile table as ``p``.
    """
    sub_selects: List[str] = []
    for league_key in sorted(LEAGUES):
        for table_name, meta in STATS_TABLES.items():
            if meta['entity'] != entity:
                continue
            qualified = f'{league_key}.{table_name}'
            sub_selects.append(
                f"SELECT 1 FROM {qualified} s "
                f"WHERE s.{quote_col(THE_GLASS_ID_COLUMN)} = p.{quote_col(THE_GLASS_ID_COLUMN)}"
            )
    if not sub_selects:
        return 'FALSE'
    return ' UNION ALL '.join(sub_selects)


def _delete_orphan_players(cur) -> int:
    """Delete player profiles with no stats anywhere and no roster history."""
    stats_pred = _profile_has_stats_predicate('player')
    cur.execute(
        f"""
        DELETE FROM {CORE_SCHEMA}.player_profiles p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM {CORE_SCHEMA}.team_rosters tr
              WHERE tr.player_id = p.{quote_col(THE_GLASS_ID_COLUMN)}
          )
        """
    )
    return cur.rowcount


def _delete_orphan_teams(cur) -> int:
    """Delete team profiles with no stats anywhere and no league/team-roster history."""
    stats_pred = _profile_has_stats_predicate('team')
    cur.execute(
        f"""
        DELETE FROM {CORE_SCHEMA}.team_profiles p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM {CORE_SCHEMA}.league_rosters lr
              WHERE lr.team_id = p.{quote_col(THE_GLASS_ID_COLUMN)}
          )
          AND NOT EXISTS (
              SELECT 1 FROM {CORE_SCHEMA}.team_rosters tr
              WHERE tr.team_id = p.{quote_col(THE_GLASS_ID_COLUMN)}
          )
        """
    )
    return cur.rowcount


def prune_orphan_profiles() -> Dict[str, int]:
    """Cross-league sweep: delete profile rows that have no stats and no roster
    history.  Requires every league's Phase A run to have completed.

    Returns ``{'players': n, 'teams': n}``.
    """
    logger.info('Phase B: prune_orphan_profiles')
    conn = get_db_connection()
    out = {'players': 0, 'teams': 0}
    try:
        with conn.cursor() as cur:
            out['players'] = _delete_orphan_players(cur)
            out['teams'] = _delete_orphan_teams(cur)
        conn.commit()
        if out['players']:
            logger.info('Deleted %d orphan player profiles', out['players'])
        if out['teams']:
            logger.info('Deleted %d orphan team profiles', out['teams'])
        return out
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


