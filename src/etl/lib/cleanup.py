"""
Shoot the Sheet - ETL Cleanup

Two-phase data hygiene:

  Phase A: Per-league stats retention
      normalize_stats_domains - in-place coherency rules within a season's
                        stats rows (NULL/zero stats based on minutes).
        prune_stats_retention - DELETE stats rows older than the league's
                                retention window.

  Phase B: Cross-league profile pruning
        prune_entities - DELETE rows from ``profiles.{entity}s``
                                that have no stats rows in any league schema
                                AND no roster history.

Both phases are idempotent.  Phase B should be run only after every league
has finished its Phase A run for the day; running it during in-flight ETL
risks deleting an entity that's about to be referenced.
"""

import logging
from typing import Dict, List, Union

from src.core.definitions.db_columns import DB_COLUMNS
from src.core.definitions.leagues import LEAGUES
from src.core.definitions.schema import TABLE_ENTITY, TABLES
from src.core.lib.leagues_resolver import get_oldest_retained_season
from src.core.lib.postgres import db_connection, get_db_connection, quote_col

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PHASE A.1 -- in-season stat coherency
# ---------------------------------------------------------------------------


def _stats_table_for_entity(entity: str) -> Union[str, None]:
    """Return the bare stats table name for *entity* (e.g. 'player' -> 'player_seasons')."""
    for table_name, meta in TABLES.items():
        if meta.get("schema") == "stats" and TABLE_ENTITY.get(table_name) == entity:
            return table_name
    return None


def _collect_domain_columns(entity: str) -> Dict[str, List[str]]:
    """Return ``{domain_name: [counter columns]}`` for every non-base
    domain whose stats apply to ``entity``.

    Domain configuration comes from each dataset's ``source_mapping.domain``.
    The base domain (``mins_x10``) is always present and is not included here.
    """
    from src.etl.definitions.datasets import DATASETS

    target_table = _stats_table_for_entity(entity)
    if not target_table:
        return {}

    # Build domain -> minutes_col lookup from datasets
    domain_configs: Dict[str, dict] = {}
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            domain = (ds_def.get("source_mapping") or {}).get("domain")
            if not domain:
                continue
            name = domain.get("name")
            if not name or name == "base":
                continue
            domain_configs[name] = domain

    out: Dict[str, List[str]] = {}
    for col_name, col_meta in DB_COLUMNS.items():
        tables = col_meta.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        if target_table not in tables:
            continue
        col_domain = col_meta.get("domain")
        if not col_domain or col_domain == "base":
            continue
        if col_domain not in domain_configs:
            continue
        mins_col = f"{col_domain}_mins_x10"
        if col_name == mins_col:
            continue
        out.setdefault(col_domain, []).append(col_name)
    return out


def normalize_stats_domains(
    league_key: str,
    entity: str,
    season: Union[str, List[str]],
    season_type: str,
) -> int:
    """Apply per-domain coherency rules to a stats-table slice.

    For each non-primary domain:
      - If the domain's minutes column is > 0, NULL stat columns are coalesced to 0.
      - If the domain's minutes column is NULL or 0, every stat column is set to NULL.

    Returns the total number of UPDATE rows touched (counts both passes).
    """
    seasons = [season] if isinstance(season, str) else list(season)
    if not seasons:
        return 0

    stats_bare = _stats_table_for_entity(entity)
    if not stats_bare:
        return 0
    table = f"stats.{stats_bare}"
    domain_cols = _collect_domain_columns(entity)
    if not domain_cols:
        return 0

    affected = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for domain, cols in domain_cols.items():
                minutes_col = quote_col(f"{domain}_mins_x10")

                set_to_zero = ", ".join(
                    f"{quote_col(c)} = COALESCE({quote_col(c)}, 0)" for c in cols
                )
                cur.execute(
                    f"UPDATE {table} SET {set_to_zero} "
                    f"WHERE season = ANY(%s) AND season_type = %s AND {minutes_col} > 0",
                    (seasons, season_type),
                )
                affected += cur.rowcount

                set_to_null = ", ".join(f"{quote_col(c)} = NULL" for c in cols)
                cur.execute(
                    f"UPDATE {table} SET {set_to_null} "
                    f"WHERE season = ANY(%s) AND season_type = %s "
                    f"  AND ({minutes_col} IS NULL OR {minutes_col} = 0)",
                    (seasons, season_type),
                )
                affected += cur.rowcount

    if affected:
        seasons_str = (
            ",".join(seasons) if len(seasons) <= 3 else f"{len(seasons)} seasons"
        )
        logger.info(
            "Domain cleanup %s/%s [%s] %s: %d rows updated",
            league_key,
            entity,
            seasons_str,
            season_type,
            affected,
        )
    return affected


# ---------------------------------------------------------------------------
# PHASE A.2 -- per-league stats retention pruning
# ---------------------------------------------------------------------------


def prune_stats_retention(league_key: str, current_season: str) -> int:
    """Delete stats rows older than the league's retention window.

    ``current_season`` defines the most recent season (e.g. ``'2025-26'``);
    the retention window is governed by the global ``RETENTION_SEASONS`` constant.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    oldest = get_oldest_retained_season(league_key, current_season)
    pruned = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for table_name, meta in TABLES.items():
                if meta.get("schema") != "stats":
                    continue
                if table_name.endswith("_staging"):
                    continue
                entity = TABLE_ENTITY.get(table_name)
                if not entity:
                    continue
                cur.execute(
                    f"DELETE FROM stats.{table_name} WHERE league_code = %s AND season < %s",
                    (league_key, oldest),
                )
                if cur.rowcount:
                    logger.info(
                        "Pruned %d rows from stats.%s (season < %s)",
                        cur.rowcount,
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
        if meta.get("schema") != "stats":
            continue
        if table_name.endswith("_staging"):
            continue
        if TABLE_ENTITY.get(table_name) != entity:
            continue
        sub_selects.append(
            f"SELECT 1 FROM stats.{table_name} s "
            f"WHERE s.{quote_col(entity_id_col)} = p.{quote_col('sts_id')}"
        )
    if not sub_selects:
        return "FALSE"
    return " UNION ALL ".join(sub_selects)


def _delete_pruned_players(cur) -> int:
    """Delete player profiles with no stats anywhere and no roster history."""
    stats_pred = _profile_has_stats_predicate("player")
    cur.execute(
        f"""
        DELETE FROM profiles.players p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM rosters.teams_players tr
              WHERE tr.player_id = p.{quote_col("sts_id")}
          )
        """
    )
    return cur.rowcount


def _delete_pruned_teams(cur) -> int:
    """Delete team profiles with no stats anywhere and no league/team-roster history."""
    stats_pred = _profile_has_stats_predicate("team")
    cur.execute(
        f"""
        DELETE FROM profiles.teams p
        WHERE NOT EXISTS ({stats_pred})
          AND NOT EXISTS (
              SELECT 1 FROM rosters.leagues_teams lr
              WHERE lr.team_id = p.{quote_col("sts_id")}
          )
          AND NOT EXISTS (
              SELECT 1 FROM rosters.teams_players tr
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
