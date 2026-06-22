"""
Shoot the Sheet - ETL Cleanup

Two-phase data hygiene:

  Phase A: Per-league stats retention
      prune_stats_retention - DELETE stats rows older than the league's
                              retention window.

  Phase B: Cross-league profile pruning
      prune_entities - DELETE rows from core entity tables that have no
                      stats rows in any league schema AND no roster history.

Both phases are idempotent.  Phase B should be run only after every league
has finished its Phase A run for the day; running it during in-flight ETL
risks deleting an entity that's about to be referenced.
"""

import logging
from typing import Dict, List

from src.core.definitions.leagues import LEAGUES
from src.core.definitions.schema import TABLE_ENTITY, TABLES
from src.core.lib.leagues_resolver import get_oldest_retained_season
from src.core.lib.postgres import db_connection, get_db_connection, quote_col

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PHASE A -- per-league stats retention pruning
# ---------------------------------------------------------------------------


def prune_stats_retention(league_key: str, current_season: str) -> int:
    """Delete stats rows older than the league's retention window.

    ``current_season`` defines the most recent season (e.g. ``'2025-26'``);
    the retention window is governed by the league's ``season_retention_start``.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    oldest = get_oldest_retained_season(league_key, current_season)
    pruned = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for table_name, meta in TABLES.items():
                if meta.get("schema") != "core":
                    continue
                if table_name.endswith("_staging"):
                    continue
                entity = TABLE_ENTITY.get(table_name)
                if not entity:
                    continue
                schema_name = meta["schema"]
                cur.execute(
                    f"DELETE FROM {schema_name}.{table_name} WHERE league = %s AND season < %s",
                    (league_key, oldest),
                )
                if cur.rowcount:
                    logger.info(
                        "Pruned %d rows from %s.%s (season < %s)",
                        cur.rowcount,
                        schema_name,
                        table_name,
                        oldest,
                    )
                    pruned += cur.rowcount
        conn.commit()
    return pruned


# ---------------------------------------------------------------------------
# PHASE B -- cross-league entity pruning
# ---------------------------------------------------------------------------


def _profile_has_stats_predicate(entity: str) -> str:
    """Build a SQL EXISTS predicate that's TRUE if a profile has stats in any league.

    The predicate references ``p.{sts_id}`` and assumes the outer query
    aliases the profile table as ``p``.
    """
    sub_selects: List[str] = []
    entity_id_col = f"{entity}_id"
    for table_name, meta in TABLES.items():
        if (
            meta.get("schema") != "core"
            or not table_name.endswith("_seasons")
            or table_name.endswith("_staging")
        ):
            continue
        if TABLE_ENTITY.get(table_name) != entity:
            continue
        schema_name = meta["schema"]
        sub_selects.append(
            f"SELECT 1 FROM {schema_name}.{table_name} s "
            f"WHERE s.{quote_col(entity_id_col)} = p.{quote_col('sts_id')}"
        )
    if not sub_selects:
        return "FALSE"
    return " UNION ALL ".join(sub_selects)


def _delete_pruned_players(cur) -> int:
    """Delete player profiles with no stats anywhere and no roster history."""
    players_meta = TABLES["players"]
    teams_players_meta = TABLES["teams_players"]
    stats_pred = _profile_has_stats_predicate("player")
    cur.execute(
        f"""
        DELETE FROM {players_meta["schema"]}.players p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM {teams_players_meta["schema"]}.teams_players tr
              WHERE tr.player_id = p.{quote_col("sts_id")}
          )
        """
    )
    return cur.rowcount


def _delete_pruned_teams(cur) -> int:
    """Delete team profiles with no stats anywhere and no league/team-roster history."""
    teams_meta = TABLES["teams"]
    leagues_teams_meta = TABLES["leagues_teams"]
    teams_players_meta = TABLES["teams_players"]
    stats_pred = _profile_has_stats_predicate("team")
    cur.execute(
        f"""
        DELETE FROM {teams_meta["schema"]}.teams p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM {leagues_teams_meta["schema"]}.leagues_teams lr
              WHERE lr.team_id = p.{quote_col("sts_id")}
          )
          AND NOT EXISTS (
              SELECT 1 FROM {teams_players_meta["schema"]}.teams_players tr
              WHERE tr.team_id = p.{quote_col("sts_id")}
          )
        """
    )
    return cur.rowcount


def prune_entities() -> Dict[str, int]:
    """Cross-league sweep: delete profile rows that have no stats and no roster
    history.  Requires every league's Phase A run to have completed.

    Returns ``{'players': n, 'teams': n}``.
    """
    logger.info("Phase B: prune_entities")
    conn = get_db_connection()
    out = {"players": 0, "teams": 0}
    try:
        with conn.cursor() as cur:
            out["players"] = _delete_pruned_players(cur)
            out["teams"] = _delete_pruned_teams(cur)
        conn.commit()
        if out["players"]:
            logger.info("Deleted %d unreferenced player profiles", out["players"])
        if out["teams"]:
            logger.info("Deleted %d unreferenced team profiles", out["teams"])
        return out
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
