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
from typing import Any, Callable, Dict, List, Union

from psycopg2.extras import RealDictCursor

from src.core.definitions.leagues import LEAGUES
from src.core.definitions.schema import SEQUENCES, TABLES
from src.core.lib.leagues_resolver import (
    _league_or_raise,
    get_all_canonical_season_types,
    get_current_season,
    get_regular_season_types,
    get_retained_seasons,
)
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.core.lib.schema_builder import bootstrap_schema
from src.core.lib.season_resolver import parse_season_end_year
from src.etl.definitions.datasets import DATASETS
from src.etl.definitions.pipeline import (
    PIPELINE_PHASES,
)
from src.etl.definitions.sources import SOURCES
from src.etl.lib.call_groups import build_call_groups
from src.etl.lib.cleanup import (
    normalize_null_zero,
    prune_entities,
    prune_stats_retention,
)
from src.etl.lib.coverage_tracker import (
    prune_coverages,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.load import _resolve_league_id
from src.etl.lib.season_detector import _check_recent_games
from src.etl.lib.source_resolver import get_source_season_type_code
from src.etl.sources.registry import get_source_modules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity -> stats staging table resolution.
# ---------------------------------------------------------------------------
_STATS_TABLE = {
    "player": "player_seasons",
    "team": "team_seasons",
}

_PROFILE_TABLE = {"player": "players", "team": "teams"}
_ROSTER_TABLE = {"player": "teams_players", "team": "leagues_teams"}


# ============================================================================
# DYNAMIC SOURCE LOADING
# ============================================================================


def _load_source(source_code: str):
    """Dynamically import a source's config and client modules."""
    if source_code not in SOURCES:
        raise ValueError(
            f"Unknown source {source_code!r}. Registered: {sorted(SOURCES)}"
        )
    return get_source_modules(source_code)


# ============================================================================
# SHARED EXECUTION ENGINE
# ============================================================================


def _run_groups(
    table_name: str,
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    *,
    league_code: str,
    source_code: str,
    dataset: str,
    api_field_names: dict,
    api_config: dict,
    make_fetcher: Callable,
    on_entity_finished: Union[
        Callable[[str, str, List[Dict[str, Any]], int, bool, Any], None], None
    ] = None,
    in_season: bool = True,
) -> int:
    """Execute call groups for *table_name* across entities and seasons.

    Only columns referencing *dataset* are included (filtered inside
    ``build_call_groups``).
    """
    total_rows = 0

    for season in seasons:
        for entity in entities:
            groups = build_call_groups(
                entity,
                season,
                source_code,
                dataset=dataset,
                table_name=table_name,
                league_code=league_code,
                in_season=in_season,
            )

            if not groups:
                # Still need to call the API when the dataset declares
                # discovery_tables — entity IDs must be extracted even
                # when no db_columns fields reference this dataset.
                ds_cfg = DATASETS.get(source_code, {}).get(dataset, {})
                if ds_cfg.get("discovery_tables"):
                    groups = [
                        {
                            "dataset": dataset,
                            "params": {},
                            "tier": ds_cfg.get("execution_tier", "per_league"),
                            "columns": {},
                        }
                    ]
                else:
                    logger.debug(
                        "No call groups for entity=%s table=%s season=%s",
                        entity,
                        table_name,
                        season,
                    )
                    continue

            logger.info(
                "%s %s %s -- %d call groups",
                table_name,
                entity,
                season,
                len(groups),
            )

            season_end_year = parse_season_end_year(
                season, LEAGUES[league_code]["season_format"]
            )
            ctx = ExecutionContext(
                entity=entity,
                table_name=table_name,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names["entity_id"][entity],
                db_schema=league_code,
                source_code=source_code,
                api_fetcher=make_fetcher(
                    league_code,
                    season_end_year,
                    season_type_name,
                    entity,
                    identity_code=source_code,
                ),
                team_ids=team_ids,
                max_consecutive_failures=api_config.get("max_consecutive_failures", 5),
                id_aliases=api_field_names.get("id_aliases", {}),
            )

            entity_rows = 0
            failed_before = len(failed)
            succeeded_groups: List[Dict[str, Any]] = []

            for group in groups:
                try:
                    rows = execute_group(group, ctx, failed)
                    entity_rows += rows
                    succeeded_groups.append(group)
                except Exception as exc:
                    logger.exception(
                        "Group %s failed: %s",
                        group["dataset"],
                        exc,
                    )
                    failed.append(
                        {
                            "dataset": group["dataset"],
                            "error": str(exc),
                        }
                    )

            total_rows += entity_rows
            if on_entity_finished is not None:
                with db_connection() as conn:
                    on_entity_finished(
                        entity,
                        season,
                        succeeded_groups,
                        entity_rows,
                        len(failed) > failed_before,
                        conn,
                    )

    return total_rows


# ============================================================================
# ROLE-BASED DATASET LOOKUP
# ============================================================================


def _get_datasets_by_stage(stage_name: str) -> Dict[str, List[str]]:
    """Return ``{identity_code: [dataset_name, ...]}`` for a pipeline stage."""
    result: Dict[str, List[str]] = {}
    for identity_code, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            if ds_def.get("stage") == stage_name:
                result.setdefault(identity_code, []).append(ds_name)
    return result


def _load_team_ids(league_code: str) -> Dict[str, int]:
    """Return ``{ext_id: int(ext_id)}`` for teams in staging."""
    table = "ext_staging.teams_staging"
    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_code)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ext_id FROM {table} WHERE league_code = %s",
                (league_val,),
            )
            return {r[0]: int(r[0]) for r in cur.fetchall() if r[0] is not None}


# ============================================================================
# season_detector
# ============================================================================


def _run_season_detector(league_code: str, season: str) -> List[str]:
    """Query season_detector datasets and return active canonical season types."""
    active: List[str] = []
    for identity_code, datasets in DATASETS.items():
        for dataset_name in _get_datasets_by_stage("season_detector").get(
            identity_code, []
        ):
            result = _check_recent_games(
                identity_code, dataset_name, league_code, season
            )
            if result is None:
                continue
            if result:
                return result
            # [] — no activity from this dataset, try next
    return active


# ============================================================================
# _discover_entities  (leagues_teams_maintainer / teams_players_maintainer)
# ============================================================================


def _discover_entities(
    league_code: str,
    season: str,
    stage_name: str,
    identity_code: str,
    source_code: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    team_ids: Dict[str, int] = None,  # type: ignore[assignment]
) -> int:
    """Execute a maintainer stage: call each dataset, extract columns, prune stale records."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_datasets_by_stage(stage_name).get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_code)
    entities = ["player"] if stage_name == "teams_players_maintainer" else ["team"]

    from datetime import datetime, timezone

    for dataset_name in dataset_names:
        logger.info(
            phase_marker(
                stage_name,
                f"dataset={identity_code}.{dataset_name} source={source_code}",
            )
        )

        ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
        prune_tables = ds_cfg.get("prune_tables")
        prune_start = datetime.now(timezone.utc) if prune_tables else None

        # Profile columns → players / teams staging
        for entity in entities:
            total_rows += _run_groups(
                table_name=_PROFILE_TABLE[entity],
                entities=[entity],
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids if entity == "player" else {},
                failed=failed,
                league_code=league_code,
                source_code=identity_code,
                dataset=dataset_name,
                api_field_names=config_mod.API_FIELD_NAMES
                if hasattr(config_mod, "API_FIELD_NAMES")
                else {},
                api_config=config_mod.API_CONFIG
                if hasattr(config_mod, "API_CONFIG")
                else {},
                make_fetcher=client_mod.make_fetcher,
                in_season=True,
            )

        # Roster links → teams_players / leagues_teams staging (teams_players_maintainer only)
        if stage_name == "teams_players_maintainer":
            for entity in entities:
                total_rows += _run_groups(
                    table_name=_ROSTER_TABLE[entity],
                    entities=[entity],
                    seasons=[season],
                    season_type=season_type,
                    season_type_name=season_type_name,
                    team_ids=team_ids,
                    failed=failed,
                    league_code=league_code,
                    source_code=identity_code,
                    dataset=dataset_name,
                    api_field_names=config_mod.API_FIELD_NAMES
                    if hasattr(config_mod, "API_FIELD_NAMES")
                    else {},
                    api_config=config_mod.API_CONFIG
                    if hasattr(config_mod, "API_CONFIG")
                    else {},
                    make_fetcher=client_mod.make_fetcher,
                    in_season=True,
                )

        # Prune stale records from roster tables — any row not touched
        # by this execution (updated_at < start time) is no longer present
        # in the dataset's API response.
        if prune_tables and prune_start:
            with db_connection() as conn:
                league_val = _resolve_league_id(conn, league_code)
                for tbl in prune_tables:
                    qualified = f"ext_staging.{tbl}"
                    with conn.cursor() as cur:
                        cur.execute(
                            f"DELETE FROM {qualified} "
                            f"WHERE league_code = %s AND identity = %s "
                            f"AND updated_at < %s",
                            (league_val, identity_code, prune_start),
                        )
                        deleted = cur.rowcount
                        if deleted:
                            logger.info(
                                "Pruned %d stale rows from %s", deleted, qualified
                            )
                    conn.commit()

    return total_rows


# ============================================================================
# stats_coverage_maintainer  (backfill)
# ============================================================================


def _maintain_stats_coverage(
    league_code: str,
    season_range: List[str],
    identity_code: str,
    source_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Ensure every retained season x every season type is covered.

    Always runs.  Coverage tracking gates re-fetching.
    """
    from src.core.lib.leagues_resolver import (
        get_all_canonical_season_types,
        is_season_type_valid_for,
    )
    from src.etl.lib.coverage_tracker import is_group_coverage_current

    total_rows = 0
    dataset_names = _get_datasets_by_stage("stats_maintainer").get(identity_code, [])
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_code)
    all_season_types = get_all_canonical_season_types(league_code)

    stats_entities = ["player", "team"]

    for dataset_name in dataset_names:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue

                season_type_name = get_source_season_type_code(
                    source_code, league_code, st_key
                )

                for entity in stats_entities:
                    table_name = _STATS_TABLE[entity]
                    groups = build_call_groups(
                        entity,
                        season_label,
                        identity_code,
                        dataset=dataset_name,
                        table_name=table_name,
                        league_code=league_code,
                        in_season=True,
                    )
                    if not groups:
                        continue

                    with db_connection() as conn:
                        filtered_groups = [
                            g
                            for g in groups
                            if not is_group_coverage_current(
                                conn,
                                league_code,
                                entity,
                                season_label,
                                st_key,
                                identity_code,
                                g,
                            )
                        ]

                    if not filtered_groups:
                        continue

                    total_rows += _execute_stats_groups(
                        league_code=league_code,
                        entity=entity,
                        season_label=season_label,
                        st_key=st_key,
                        season_type_name=season_type_name,
                        identity_code=identity_code,
                        source_code=source_code,
                        dataset=dataset_name,
                        filtered_groups=filtered_groups,
                        team_ids=team_ids,
                        failed=failed,
                        use_coverage=True,
                    )

    return total_rows


# ============================================================================
# current_stats_maintainer  (current season refresh)
# ============================================================================


def _maintain_current_stats(
    league_code: str,
    season: str,
    identity_code: str,
    source_code: str,
    active_types: List[str],
    failed: List[Dict[str, Any]],
) -> int:
    """Refresh stats for the CURRENT season and ACTIVE season types only."""
    from src.core.lib.leagues_resolver import is_season_type_valid_for

    total_rows = 0
    dataset_names = _get_datasets_by_stage("stats_maintainer").get(identity_code, [])
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_code)
    stats_entities = ["player", "team"]

    for st_key in active_types:
        if not is_season_type_valid_for(league_code, st_key, season):
            continue

        season_type_name = get_source_season_type_code(source_code, league_code, st_key)

        for dataset_name in dataset_names:
            for entity in stats_entities:
                table_name = _STATS_TABLE[entity]
                groups = build_call_groups(
                    entity,
                    season,
                    identity_code,
                    dataset=dataset_name,
                    table_name=table_name,
                    league_code=league_code,
                    in_season=True,
                )
                if not groups:
                    continue

                total_rows += _execute_stats_groups(
                    league_code=league_code,
                    entity=entity,
                    season_label=season,
                    st_key=st_key,
                    season_type_name=season_type_name,
                    identity_code=identity_code,
                    source_code=source_code,
                    dataset=dataset_name,
                    filtered_groups=groups,
                    team_ids=team_ids,
                    failed=failed,
                    use_coverage=True,
                )

    return total_rows


# ============================================================================
# stats execution helper
# ============================================================================


def _execute_stats_groups(
    *,
    league_code: str,
    entity: str,
    season_label: str,
    st_key: str,
    season_type_name: str,
    identity_code: str,
    source_code: str,
    dataset: str,
    filtered_groups: List[Dict[str, Any]],
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    use_coverage: bool,
) -> int:
    """Execute stats call groups for a single dataset / entity slice."""
    from src.etl.lib.coverage_tracker import upsert_group_coverage

    if not filtered_groups:
        return 0

    ds_cfg = DATASETS.get(identity_code, {}).get(dataset, {})
    src_key = ds_cfg.get("source", source_code)

    logger.info(
        phase_marker(
            "stats",
            f"entity={entity} season={season_label} "
            f"season_type={st_key} "
            f"dataset={dataset} "
            f"groups={len(filtered_groups)}",
        )
    )

    table_name = _STATS_TABLE[entity]
    config_mod, client_mod = _load_source(src_key)

    def _on_coverage(
        entity,
        season_label,
        succeeded_groups,
        _rows,
        _had_failures,
        conn,
        _league_key=league_code,
        _season_type=st_key,
        _source_key=identity_code,
    ):
        if not use_coverage:
            return
        for g in succeeded_groups:
            upsert_group_coverage(
                conn,
                _league_key,
                entity,
                season_label,
                _season_type,
                _source_key,
                g,
            )

    return _run_groups(
        table_name=table_name,
        entities=[entity],
        seasons=[season_label],
        season_type=st_key,
        season_type_name=season_type_name,
        team_ids=team_ids if entity == "player" else {},
        failed=failed,
        league_code=league_code,
        source_code=identity_code,
        dataset=dataset,
        api_field_names=config_mod.API_FIELD_NAMES
        if hasattr(config_mod, "API_FIELD_NAMES")
        else {},
        api_config=config_mod.API_CONFIG if hasattr(config_mod, "API_CONFIG") else {},
        make_fetcher=client_mod.make_fetcher,
        in_season=True,
        on_entity_finished=_on_coverage if use_coverage else None,
    )


# ============================================================================
# profile_maintainer
# ============================================================================


def _maintain_profiles(
    league_code: str,
    season: str,
    identity_code: str,
    source_code: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    team_ids: Dict[str, int] = None,  # type: ignore[assignment]
) -> int:
    """Update profile fields for entities already in staging."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_datasets_by_stage("profile_maintainer").get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_code)

    for dataset_name in dataset_names:
        for entity in ["team", "player"]:
            logger.info(
                phase_marker(
                    "profile_maintainer",
                    f"dataset={identity_code}.{dataset_name} entity={entity}",
                )
            )
            total_rows += _run_groups(
                table_name=_PROFILE_TABLE[entity],
                entities=[entity],
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids,
                failed=failed,
                league_code=league_code,
                source_code=identity_code,
                api_field_names=config_mod.API_FIELD_NAMES
                if hasattr(config_mod, "API_FIELD_NAMES")
                else {},
                api_config=config_mod.API_CONFIG
                if hasattr(config_mod, "API_CONFIG")
                else {},
                make_fetcher=client_mod.make_fetcher,
                in_season=True,
                dataset=dataset_name,
            )

    return total_rows


# ============================================================================
# ENTITY MATCHING & UPSERT
# ============================================================================


def _match_entities(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Resolve staged identities to existing sts_ids."""
    logger.info(phase_marker("match_entities"))
    total_matched = 0

    ie_meta = TABLES["identities_entities"]
    identities_table = f"{ie_meta['schema']}.identities_entities"

    staging_entities = [
        ("player", "ext_staging.players_staging"),
        ("team", "ext_staging.teams_staging"),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for entity, staging_table in staging_entities:
                sql = f"""
                    UPDATE {staging_table} s
                       SET matched_sts_id = ie.entity_id
                      FROM {identities_table} ie
                     WHERE s.identity = ie.identity AND s.ext_id = ie.ext_id
                       AND ie.entity = %s
                       AND s.matched_sts_id IS NULL
                """
                cur.execute(sql, (entity,))
                matched = cur.rowcount
                total_matched += matched
                if matched:
                    logger.info(
                        "Matched %d staged %ss to existing sts_ids", matched, entity
                    )
        conn.commit()

    return total_matched


def _upsert_entities(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote staged rows to core tables."""
    logger.info(phase_marker("upsert_entities"))
    total_upserted = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            for entity, staging_table, core_table in [
                ("player", "ext_staging.players_staging", "core.players"),
                ("team", "ext_staging.teams_staging", "core.teams"),
            ]:
                # Count staged rows needing promotion
                cur.execute(
                    f"SELECT COUNT(*) FROM {staging_table} WHERE matched_sts_id IS NULL"
                )
                unmatched = cur.fetchone()[0]
                if unmatched:
                    logger.info(
                        "%d unmatched %s rows in staging — awaiting manual review",
                        unmatched,
                        entity,
                    )

                # Promote matched rows: insert into core + update staging
                sql = f"""
                    INSERT INTO {core_table} (league_code, nba_id_id, display_name, sts_id)
                    SELECT s.league_code, s.ext_id, s.display_name, ie.entity_id
                      FROM {staging_table} s
                      JOIN core.identities_entities ie
                        ON s.identity = ie.identity AND s.ext_id = ie.ext_id
                       AND ie.entity = %s
                     WHERE s.matched_sts_id IS NOT NULL
                       AND NOT EXISTS (
                           SELECT 1 FROM {core_table} c
                            WHERE c.sts_id = ie.entity_id
                       )
                """
                cur.execute(sql, (entity,))
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info(
                        "Promoted %d %s rows from staging to core", upserted, entity
                    )
        conn.commit()

    return total_upserted


# ============================================================================
# TOP-LEVEL RUNNER
# ============================================================================


def run_etl(
    league_code: Union[str, None] = None,
) -> None:
    """Run all ETL phase clusters for a league or all leagues.

    execution_start and execution_end run once total (schema bootstrap,
    pruning).  per_identity runs once per league.
    """
    if league_code:
        if league_code not in LEAGUES:
            raise ValueError(
                f"Unknown league {league_code!r}. Registered: {sorted(LEAGUES)}"
            )
        leagues_to_run = [league_code]
    else:
        leagues_to_run = list(LEAGUES)

    # execution_start — once (schema is global)
    _run_cluster("execution_start", leagues_to_run[0])

    # per_league — once per league (season detection)
    for lcode in leagues_to_run:
        _run_cluster("per_league", lcode)

    # per_identity — per league
    for lcode in leagues_to_run:
        _run_cluster("per_identity", lcode)

    # execution_end — once (pruning is global)
    _run_cluster("execution_end", leagues_to_run[0])


def _run_cluster(cluster: str, league_code: str) -> None:
    handlers = PIPELINE_PHASES.get(cluster, [])
    if not handlers:
        return

    logger.info("=" * 80)
    logger.info("Cluster: %s", cluster)
    logger.info("=" * 80)

    try:
        _run_league_phases(league_code, handlers, cluster, season_range=None)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        raise
    except Exception:
        logger.exception(
            "ETL run failed for league %s in cluster %s.", league_code, cluster
        )


def _run_league_phases(
    league_code: str,
    handlers: List[str],
    cluster: str,
    season_range: Union[List[str], None] = None,
) -> int:
    """Run per-league handlers for a single league. Returns total rows written."""
    _league_or_raise(league_code)
    season = get_current_season(league_code)
    if season_range is None:
        season_range = get_retained_seasons(league_code, season)

    logger.info(
        "ETL starting: league=%s cluster=%s season=%s",
        league_code,
        cluster,
        season,
    )

    failed: List[Dict[str, Any]] = []
    total_rows = 0

    for handler in handlers:
        if handler == "build_schema":
            logger.info(phase_marker("build_schema"))
            with db_connection() as conn:
                bootstrap_schema(league_code, conn=conn)

        elif handler == "season_detector":
            logger.info(phase_marker("season_detector"))
            active = _run_season_detector(league_code, season)
            logger.info(
                "Season detector result: active=%s in_season=%s",
                active,
                bool(active),
            )

        elif handler in ("leagues_teams_maintainer", "teams_players_maintainer"):
            logger.info(phase_marker(handler))
            team_ids = (
                _load_team_ids(league_code)
                if handler == "teams_players_maintainer"
                else {}
            )

            for identity_code in DATASETS:
                stage_datasets = _get_datasets_by_stage(handler).get(identity_code, [])
                if not stage_datasets:
                    continue
                source_code = DATASETS[identity_code][stage_datasets[0]]["source"]
                if league_code not in SOURCES[source_code].get("leagues", {}):
                    continue
                logger.info(
                    "  identity=%s source=%s datasets=%s",
                    identity_code,
                    source_code,
                    stage_datasets,
                )
                reg_st = get_regular_season_types(league_code)[0]
                reg_code = get_source_season_type_code(source_code, league_code, reg_st)
                total_rows += _discover_entities(
                    league_code,
                    season,
                    handler,
                    identity_code,
                    source_code,
                    reg_st,
                    reg_code,
                    failed,
                    team_ids=team_ids,
                )

        elif handler == "stats_coverage_maintainer":
            logger.info(phase_marker("stats_coverage_maintainer"))

            for identity_code in DATASETS:
                stage_datasets = _get_datasets_by_stage("stats_maintainer").get(
                    identity_code, []
                )
                if not stage_datasets:
                    continue
                source_code = DATASETS[identity_code][stage_datasets[0]]["source"]
                if league_code not in SOURCES[source_code].get("leagues", {}):
                    continue
                total_rows += _maintain_stats_coverage(
                    league_code,
                    season_range,
                    identity_code,
                    source_code,
                    failed,
                )

        elif handler == "current_stats_maintainer":
            active_types = _run_season_detector(league_code, season)
            if not active_types:
                logger.info(
                    phase_marker(
                        "current_stats_maintainer", "no active types — skipping"
                    )
                )
                continue

            logger.info(
                phase_marker("current_stats_maintainer", f"active_types={active_types}")
            )

            for identity_code in DATASETS:
                stage_datasets = _get_datasets_by_stage("stats_maintainer").get(
                    identity_code, []
                )
                if not stage_datasets:
                    continue
                source_code = DATASETS[identity_code][stage_datasets[0]]["source"]
                if league_code not in SOURCES[source_code].get("leagues", {}):
                    continue
                total_rows += _maintain_current_stats(
                    league_code,
                    season,
                    identity_code,
                    source_code,
                    active_types,
                    failed,
                )

        elif handler == "profile_maintainer":
            logger.info(phase_marker("profile_maintainer"))

            for identity_code in DATASETS:
                stage_datasets = _get_datasets_by_stage(handler).get(identity_code, [])
                if not stage_datasets:
                    continue
                source_code = DATASETS[identity_code][stage_datasets[0]]["source"]
                if league_code not in SOURCES[source_code].get("leagues", {}):
                    continue
                team_ids = _load_team_ids(league_code)
                reg_st = get_regular_season_types(league_code)[0]
                reg_code = get_source_season_type_code(source_code, league_code, reg_st)
                total_rows += _maintain_profiles(
                    league_code,
                    season,
                    identity_code,
                    source_code,
                    reg_st,
                    reg_code,
                    failed,
                    team_ids=team_ids,
                )

        elif handler == "match_entities":
            total_rows += _match_entities(league_code, failed)

        elif handler == "upsert_entities":
            total_rows += _upsert_entities(league_code, failed)

        elif handler == "normalize_null_zero":
            logger.info(phase_marker(handler))
            total_rows += normalize_null_zero(league_code)

        elif handler == "prune_stats_retention":
            logger.info(phase_marker(handler))
            total_rows += prune_stats_retention(league_code, season)

        elif handler == "prune_entities":
            logger.info(phase_marker(handler))
            result = prune_entities()
            total_rows += result.get("players", 0) + result.get("teams", 0)

        elif handler == "prune_coverages":
            logger.info(phase_marker(handler))
            total_rows += prune_coverages(league_code)

        else:
            raise ValueError(
                f"Unknown ETL stage handler {handler!r} for league {league_code!r}"
            )

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)

    return total_rows
