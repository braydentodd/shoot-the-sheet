"""
Shoot the Sheet - ETL Cleanup

Multi-phase data hygiene:

  Phase 0: Stats normalization (null/zero)
      normalize_nulls_zeroes - Normalize zero-values and NULLs in stats
                             tables based on minutes played.

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
from typing import Dict, List

from src.core.definitions.leagues import LEAGUES
from src.core.definitions.schema import TABLES
from src.core.lib.leagues_resolver import get_oldest_retained_season
from src.core.lib.postgres import db_connection, get_db_connection, quote_col

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PHASE 0 -- per-league stats null/zero normalization
# ---------------------------------------------------------------------------

# Columns excluded from zero→null conversion (these are meaningful zeros).
_ZERO_PRESERVE_COLS = frozenset({"mins", "games", "poss", "opp_poss"})

# Columns that are never stats (system / identity / FK / audit).
_SYSTEM_COLS = frozenset(
    {
        "sts_id",
        "player_id",
        "team_id",
        "league_code",
        "season",
        "season_type",
        "updated_at",
        "created_at",
        "entity",
    }
)

# Only these data types are considered stats columns.
_NUMERIC_TYPES = frozenset(
    {
        "smallint",
        "integer",
        "bigint",
        "real",
        "double precision",
        "numeric",
    }
)


def _discover_stats_columns(cur, table_name: str) -> List[str]:
    """Return ordered list of numeric stats columns for a core table."""
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'core'
           AND table_name   = %s
           AND data_type    = ANY(%s)
           AND column_name != ALL(%s)
         ORDER BY ordinal_position
        """,
        (table_name, list(_NUMERIC_TYPES), list(_SYSTEM_COLS)),
    )
    return [row[0] for row in cur.fetchall()]


def normalize_nulls_zeroes(league_code: Union[str, None] = None) -> int:
    """Normalize null/zero values in stats tables based on minutes played.

    If *league_code* is None, normalizes across all registered leagues.
    """
    league_codes = [league_code] if league_code else list(LEAGUES)
    updated = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for lc in league_codes:
                for table_name in ("player_seasons", "team_seasons"):
                    stats_cols = _discover_stats_columns(cur, table_name)
                    if not stats_cols:
                        continue

                    zero_to_null = [
                        c for c in stats_cols if c not in _ZERO_PRESERVE_COLS
                    ]
                    if zero_to_null:
                        assignments = ", ".join(
                            f"{quote_col(c)} = NULLIF({quote_col(c)}, 0)"
                            for c in zero_to_null
                        )
                        cur.execute(
                            f"UPDATE core.{table_name} SET {assignments}"
                            f" WHERE league_code = %s AND mins = 0",
                            (lc,),
                        )
                        updated += cur.rowcount

                    null_to_zero = ", ".join(
                        f"{quote_col(c)} = COALESCE({quote_col(c)}, 0)"
                        for c in stats_cols
                    )
                    cur.execute(
                        f"UPDATE core.{table_name} SET {null_to_zero}"
                        f" WHERE league_code = %s AND mins > 0",
                        (lc,),
                    )
                    updated += cur.rowcount

        conn.commit()

    if updated:
        logger.info("Normalized null/zero: %d rows updated", updated)
    return updated


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
                for table_name, meta in TABLES.items():
                    if meta.get("schema") != "core":
                        continue
                    if table_name.endswith("_staging"):
                        continue
                    if (
                        not table_name.endswith("_seasons")
                        and table_name != "season_coverages"
                    ):
                        continue
                    schema_name = meta["schema"]
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
    for table_name, meta in TABLES.items():
        if (
            meta.get("schema") != "core"
            or not table_name.endswith("_seasons")
            or table_name.endswith("_staging")
        ):
            continue
        # Only include the table that matches this entity's naming convention
        expected_table = f"{entity}_seasons"
        if table_name != expected_table:
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
