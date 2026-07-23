"""
Shoot the Sheet - ETL Cleanup

Multi-phase data hygiene:

  Phase A: Per-league stats retention
      prune_stats_retention - DELETE stats rows older than the league's
                              retention window.

  Phase B: Cross-league profile pruning
      prune_entities - DELETE rows from core entity tables that have no
                      stats rows in any league schema AND no roster history.

  Phase C: Coverage pruning
      prune_season_coverages - DELETE season_coverages rows for seasons outside
                        the league's retention window.

All phases are idempotent.  Phase B should be run only after every league
has finished its Phase A run for the day; running it during in-flight ETL
risks deleting an entity that's about to be referenced.
"""

import logging
from typing import Dict, List, Union

from src.definitions.leagues import LEAGUES
from src.definitions.schema import iter_tables
from src.lib.leagues_resolver import get_oldest_retained_season
from src.lib.postgres import db_connection, get_db_connection, quote_col

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PHASE A -- per-league stats retention pruning
# ---------------------------------------------------------------------------


def prune_stats_retention(
    league_code: Union[str, None] = None, current_season: str = ""
) -> int:
    """Delete stats rows older than each league's retention window.

    If *league_code* is None, prunes across all registered leagues.
    """
    league_codes = [league_code] if league_code else list(LEAGUES)
    pruned = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for lc in league_codes:
                oldest = get_oldest_retained_season(lc, current_season)
                for qualified_name, schema_name, table_name, meta in iter_tables():
                    if schema_name != "core":
                        continue
                    if (
                        not table_name.endswith("_seasons")
                        and table_name != "season_coverages"
                        and table_name != "game_coverages"
                    ):
                        continue
                    cur.execute(
                        f"DELETE FROM {schema_name}.{table_name} WHERE league_code = %s AND season < %s",
                        (lc, oldest),
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
    # Core stats tables are named {entity}_seasons (e.g. player_seasons, team_seasons)
    for qualified_name, schema_name, table_name, meta in iter_tables():
        if schema_name != "core" or not table_name.endswith("_seasons"):
            continue
        # Only include the table that matches this entity's naming convention
        expected_table = f"{entity}_seasons"
        if table_name != expected_table:
            continue
        sub_selects.append(
            f"SELECT 1 FROM {schema_name}.{table_name} s "
            f"WHERE s.{quote_col(entity_id_col)} = p.{quote_col('sts_id')}"
        )
    if not sub_selects:
        return "FALSE"
    return " UNION ALL ".join(sub_selects)


def _delete_pruned(entity: str, cur) -> int:
    """Delete profile rows with no stats anywhere and no roster history.

    Args:
        entity: "player" or "team" -- drives table/column resolution.

    Returns the number of deleted rows.
    """
    stats_pred = _profile_has_stats_predicate(entity)

    # Tables that prove an entity is still referenced.
    reference_checks = []

    if entity == "player":
        reference_checks = [("core.teams_players", "player_id")]
    elif entity == "team":
        reference_checks = [
            ("core.leagues_teams", "team_id"),
            ("core.teams_players", "team_id"),
        ]

    not_exists_clauses = "".join(
        f"""
          AND NOT EXISTS (
              SELECT 1 FROM {table} ref
              WHERE ref.{fk_col} = p.{quote_col("sts_id")}
          )"""
        for table, fk_col in reference_checks
    )

    table = f"core.{entity}s"
    cur.execute(
        f"""
        DELETE FROM {table} p
        WHERE NOT EXISTS ({stats_pred})
        {not_exists_clauses}
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
            out["players"] = _delete_pruned("player", cur)
            out["teams"] = _delete_pruned("team", cur)
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
