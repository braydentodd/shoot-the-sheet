"""
Shoot the Sheet - ETL Orchestrator

Sequences the ordered ETL phases for a single league run.  Knows nothing
about HTTP, argparse, or the destination of stdout -- just which phase
runs when, and which library function each phase calls.

Layering:

    src.etl.cli          (argparse + dispatch)
        |
        v
    src.etl.orchestrator  (this module: phase ordering)
        |
        +--> src.core.lib.ddl              (schema bootstrap)
        +--> src.etl.lib.load               (staging + profile writes)
        +--> src.etl.lib.executor           (one API call group)
        +--> src.etl.lib.cleanup            (post-run hygiene)

Each phase is a thin wrapper around the lib function it drives; orchestration
logic that has no business in lib (e.g. resolving the active source, building
ExecutionContext) lives here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple, Union

from src.core.definitions.leagues import LEAGUES
from src.core.lib.leagues_resolver import (
    get_all_canonical_season_types,
    get_current_season,
    get_regular_season_types,
    get_retained_seasons,
)
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.core.lib.schema_builder import bootstrap_schema
from src.core.lib.season_resolver import parse_season_end_year
from src.core.lib.terminal import progress
from src.etl.definitions.pipeline import (
    PIPELINE_PHASES,
    VALID_ETL_PHASES,
)
from src.etl.definitions.sources import SOURCES
from src.etl.lib.call_groups import build_call_groups
from src.etl.lib.cleanup import (
    prune_entities,
    prune_stats_retention,
)
from src.etl.lib.coverage_tracker import (
    _resolve_league_id,
    prune_coverages,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.progress_tracker import (
    complete_run,
    fail_run,
    mark_group_completed,
    mark_group_failed,
    mark_group_started,
    resolve_work,
    update_run_completed_groups,
)
from src.etl.lib.season_detector import detect_active_season_types, is_league_in_season
from src.etl.lib.source_resolver import (
    build_source_id_columns,
    get_source_id_column,
)

logger = logging.getLogger(__name__)


VALID_PHASES = set(VALID_ETL_PHASES)


OPS_SCHEMA = "ops"


# ============================================================================
# DYNAMIC SOURCE LOADING
# ============================================================================


def _load_source(source_key: str):
    """Dynamically import a source's config and client modules."""
    if source_key not in SOURCES:
        raise ValueError(
            f"Unknown source {source_key!r}. Registered: {sorted(SOURCES)}"
        )
    return get_source_modules(source_key)


# ============================================================================
# CORE-AWARE LOOKUPS
# ============================================================================


def _get_active_team_source_ids(league_key: str, source_key: str) -> Dict[str, int]:
    """Return ``{team_abbr: team_source_id}`` for teams currently active in
    the league-team roster table for the given league.

    Used by per-team execution strategies that need to iterate over the team
    list (e.g. on/off court datasets).
    """
    src_col = get_source_id_column(source_key)
    sql = f"""
        SELECT t.abbr, t.{quote_col(src_col)}
          FROM profiles.teams t
          JOIN rosters.leagues_teams lr
            ON lr.team_id = t.{quote_col("sts_id")}
          JOIN profiles.leagues lp
            ON lp.{quote_col("sts_id")} = lr.league_id
         WHERE lp.code = %s
         ORDER BY t.abbr
    """
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (league_key,))
            return {
                row[0]: int(row[1])
                for row in cur.fetchall()
                if row[0] and row[1] is not None
            }


# ============================================================================
# SHARED EXECUTION ENGINE  (drives src.etl.lib.executor for one phase)
# ============================================================================


def _run_groups(
    scope: str,
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    *,
    league_key: str,
    source_key: str,
    api_field_names: dict,
    api_config: dict,
    make_fetcher: Callable,
    groups_override: Union[Dict[Tuple[str, str], List[Dict[str, Any]]], None] = None,
    on_entity_finished: Union[
        Callable[[str, str, List[Dict[str, Any]], int, bool, Any], None], None
    ] = None,
    in_season: bool = True,
) -> int:
    """Execute call groups for a given scope across entities and seasons."""
    total_rows = 0

    for season in seasons:
        for entity in entities:
            if groups_override is not None:
                groups = groups_override.get((entity, season), [])
            else:
                groups = build_call_groups(
                    entity,
                    season,
                    source_key,
                    scope=scope,
                    league_key=league_key,
                    in_season=in_season,
                )
            if not groups:
                continue

            logger.info(
                "%s: %s %s -- %d call groups",
                scope,
                entity,
                season,
                len(groups),
            )

            season_end_year = parse_season_end_year(
                season, LEAGUES[league_key]["season_format"]
            )
            ctx = ExecutionContext(
                entity=entity,
                scope=scope,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names["entity_id"][entity],
                db_schema=league_key,
                source_key=source_key,
                api_fetcher=make_fetcher(
                    league_key, season_end_year, season_type_name, entity
                ),
                team_ids=team_ids,
                max_consecutive_failures=api_config.get("max_consecutive_failures", 5),
                id_aliases=api_field_names.get("id_aliases", {}),
            )

            with db_connection() as conn:
                league_id = _resolve_league_id(conn, league_key)
                run_process_id, work_items = resolve_work(
                    conn,
                    OPS_SCHEMA,
                    entity,
                    season,
                    season_type,
                    groups,
                    True,
                    league_id=league_id,
                )

                entity_rows = 0
                failed_before = len(failed)
                succeeded_groups: List[Dict[str, Any]] = []
                bar_desc = f"{scope}/{entity}/{season}"
                try:
                    with progress(
                        total=len(work_items),
                        desc=bar_desc,
                        unit="group",
                        leave=False,
                    ) as bar:
                        for group, progress_id in work_items:
                            bar.set_postfix_str(group["dataset"], refresh=False)
                            mark_group_started(conn, OPS_SCHEMA, progress_id)
                            try:
                                rows = execute_group(group, ctx, failed, conn=conn)
                                entity_rows += rows
                                mark_group_completed(
                                    conn,
                                    OPS_SCHEMA,
                                    progress_id,
                                    rows,
                                    dataset=group.get("dataset"),
                                    tier=group.get("tier"),
                                )
                                succeeded_groups.append(group)
                            except Exception as exc:
                                logger.exception(
                                    "Group %s failed: %s",
                                    group["dataset"],
                                    exc,
                                )
                                mark_group_failed(
                                    conn, OPS_SCHEMA, progress_id, str(exc)
                                )
                                failed.append(
                                    {
                                        "dataset": group["dataset"],
                                        "error": str(exc),
                                    }
                                )
                            bar.update(1)

                    total_rows += entity_rows
                    update_run_completed_groups(conn, OPS_SCHEMA, run_process_id)
                    complete_run(conn, OPS_SCHEMA, run_process_id)
                    if on_entity_finished is not None:
                        on_entity_finished(
                            entity,
                            season,
                            succeeded_groups,
                            entity_rows,
                            len(failed) > failed_before,
                            conn,
                        )
                except Exception as exc:
                    fail_run(conn, OPS_SCHEMA, run_process_id, str(exc))
                    raise

    return total_rows


# ============================================================================
# ETL PHASE HANDLERS
# ============================================================================


def _get_internal_sources() -> List[str]:
    """Return source keys whose datasets live under the ``sts_id`` identity."""
    from src.etl.definitions.datasets import DATASETS

    internal = set()
    for ds_name, ds_def in DATASETS.get("sts_id", {}).items():
        internal.add(ds_def.get("source"))
    return sorted(internal)


def _get_external_sources(league_key: str) -> List[str]:
    """Return source keys with datasets under non-``sts_id`` identities."""
    from src.etl.definitions.datasets import DATASETS

    external = set()
    for identity_key, datasets in DATASETS.items():
        if identity_key == "sts_id":
            continue
        for ds_name, ds_def in datasets.items():
            source = ds_def.get("source")
            if source and source != "shoot_the_sheet":
                external.add(source)
    return sorted(external)


def _update_internal(
    league_key: str,
    season: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Update production profiles from internal sources (direct write, no staging)."""
    total_rows = 0
    for source_key in _get_internal_sources():
        logger.info(phase_marker("update_internal", f"source={source_key}"))
        # TODO: iterate datasets in DATASETS order, write directly to profiles tables
    return total_rows


def _backfill_external(
    league_key: str,
    season_range: List[str],
    season: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    in_season: bool = True,
) -> int:
    """Backfill historical stats to staging tables for uncovered combinations."""
    total_rows = 0
    previous_seasons = [s for s in season_range if s != season]
    if not previous_seasons:
        return 0

    for source_key in _get_external_sources(league_key):
        logger.info(
            phase_marker(
                "backfill_external",
                f"source={source_key} seasons={len(previous_seasons)}",
            )
        )
        # TODO: iterate datasets in DATASETS order, write to *_staging tables
    return total_rows


def _maintain_external(
    league_key: str,
    season: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    in_season: bool = True,
) -> int:
    """Fetch current profiles, stats, and rosters to staging tables."""
    total_rows = 0
    for source_key in _get_external_sources(league_key):
        logger.info(phase_marker("maintain_external", f"source={source_key}"))
        # TODO: fetch profiles -> teams_staging, players_staging
        # TODO: fetch rosters -> leagues_teams_staging, teams_players_staging
        # TODO: fetch stats -> player_seasons_staging, team_seasons_staging
    return total_rows


def _match_entities(
    league_key: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Match staged entities (countries, teams, players) to sts_id."""
    total_rows = 0
    for source_key in _get_external_sources(league_key):
        logger.info(phase_marker("match_entities", f"source={source_key}"))
        # TODO: resolve staged rows to sts_id
    return total_rows


def _upsert_entities(
    league_key: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Upsert matched staged data into production tables."""
    total_rows = 0
    for source_key in _get_external_sources(league_key):
        logger.info(phase_marker("upsert_entities", f"source={source_key}"))
        # TODO: upsert from staging to production
    return total_rows


def _resolve_source_season_type_names(
    source_key: str,
    regular_canonical: str,
    requested_canonical: str,
) -> Tuple[str, str]:
    """Resolve canonical season type keys to source-specific wire names."""
    from src.etl.lib.source_resolver import get_season_type_wire_name

    regular_name = get_season_type_wire_name(source_key, regular_canonical)
    requested_name = get_season_type_wire_name(source_key, requested_canonical)
    return regular_name, requested_name


# ============================================================================
# PUBLIC ENTRY
# ============================================================================


def run_etl(
    league_key: Union[str, None] = None,
    phase: str = "full",
) -> None:
    """Run one or more ETL phases for a league or all leagues.

    Args:
        league_key:      Registered league key (e.g. ``'nba'``). If None,
                         runs all leagues in sorted order.
        phase:           Execution phase (see VALID_PHASES).

    Caller (the CLI) is expected to have already configured logging and run
    config validation; this function never touches stdout directly.
    """
    if phase not in VALID_PHASES:
        raise ValueError(
            f"Invalid phase {phase!r}. Must be one of {sorted(VALID_PHASES)}"
        )

    # Multi-league execution
    if not league_key:
        leagues_to_run = sorted(LEAGUES)
        success_count = 0
        fail_count = 0
        failures = []

        for lkey in leagues_to_run:
            logger.info("=" * 80)
            logger.info("Executing ETL for league: %s", lkey)
            logger.info("=" * 80)
            try:
                run_etl(league_key=lkey, phase=phase)
                success_count += 1
            except KeyboardInterrupt:
                logger.warning("Interrupted by user.")
                raise
            except Exception as exc:
                logger.exception("ETL run failed for league %s.", lkey)
                fail_count += 1
                failures.append((lkey, str(exc)))

        if len(leagues_to_run) > 1:
            logger.info("=" * 80)
            logger.info("Multi-League Run Summary:")
            logger.info("  Total leagues: %d", len(leagues_to_run))
            logger.info("  Successes:     %d", success_count)
            logger.info("  Failures:      %d", fail_count)
            if failures:
                for league_key_failed, err in failures:
                    logger.error("    - %s: %s", league_key_failed, err)
            logger.info("=" * 80)
            if fail_count > 0:
                raise RuntimeError(f"{fail_count} league(s) failed")
        return
    if league_key not in LEAGUES:
        raise ValueError(
            f"Unknown league {league_key!r}. Registered: {sorted(LEAGUES)}"
        )

    league_cfg = LEAGUES[league_key]
    season = get_current_season(league_key)
    season_types = get_all_canonical_season_types(league_key)
    regular_st = get_regular_season_types(league_key)[0]
    regular_st_name = regular_st
    season_range = get_retained_seasons(league_key, season)

    # Detect which season types have had recent game activity.
    # When none are active, the pipeline skips stats columns and only
    # refreshes profiles / rosters.
    active_types = detect_active_season_types(league_key, season)
    in_season = bool(active_types)

    logger.info(
        "ETL starting: league=%s phase=%s season=%s types=%s active_types=%s in_season=%s",
        league_key,
        phase,
        season,
        ",".join(season_types),
        ",".join(active_types),
        in_season,
    )

    failed: List[Dict[str, Any]] = []
    total_rows = 0

    configured_handlers = PIPELINE_PHASES.get(phase, [])

    for handler in configured_handlers:
        if handler == "build_schema":
            logger.info(phase_marker("build_schema"))
            with db_connection() as conn:
                bootstrap_schema(
                    league_key, conn=conn, source_id_columns=build_source_id_columns()
                )

        elif handler == "update_internal":
            total_rows += _update_internal(league_key, season, regular_st_name, failed)

        elif handler == "backfill_external":
            total_rows += _backfill_external(
                league_key,
                season_range,
                season,
                regular_st,
                regular_st_name,
                failed,
                in_season=in_season,
            )

        elif handler == "maintain_external":
            total_rows += _maintain_external(
                league_key,
                season,
                regular_st,
                regular_st_name,
                failed,
                in_season=in_season,
            )

        elif handler == "match_entities":
            total_rows += _match_entities(league_key, failed)

        elif handler == "upsert_entities":
            total_rows += _upsert_entities(league_key, failed)

        elif handler == "prune_stats_retention":
            logger.info(phase_marker(handler))
            total_rows += prune_stats_retention(league_key, season)

        elif handler == "prune_entities":
            logger.info(phase_marker(handler))
            total_rows += prune_entities()

        elif handler == "prune_coverages":
            logger.info(phase_marker(handler))
            total_rows += prune_coverages(league_key)

        else:
            raise ValueError(
                f"Unknown ETL stage handler {handler!r} for league {league_key!r}"
            )

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)
