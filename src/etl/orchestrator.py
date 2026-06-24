"""
Shoot the Sheet - ETL Orchestrator

Sequences the ordered ETL phases for a single league run.  Knows nothing
about HTTP, argparse, or the destination of stdout -- just which phase
runs when, and which library function each phase calls.

Clusters:
    - ``execution_start``  — runs once before all leagues (schema bootstrap only).
    - ``per_league``       — runs once per league (season detection).
    - ``per_identity``     — runs once per league (maintain / match / upsert).
    - ``execution_end``    — runs once after all leagues (prune phases).

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

from psycopg2.extras import RealDictCursor

from src.core.definitions.db_columns import DB_COLUMNS
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
from src.etl.definitions.pipeline import PIPELINE, VALID_PHASES
from src.etl.definitions.sources import SOURCES
from src.etl.lib.call_groups import build_call_groups
from src.etl.lib.cleanup import (
    normalize_nulls_zeroes,
    prune_entities,
    prune_stats_retention,
)
from src.etl.lib.coverage_tracker import (
    prune_game_coverages,
    prune_season_coverages,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.load import _resolve_league_id
from src.etl.lib.season_detector import _check_recent_games
from src.etl.lib.source_resolver import get_source_season_type_code
from src.etl.sources.registry import get_source_modules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Every target writes to its namesake table (e.g. "players" → players).
# ---------------------------------------------------------------------------

_active_types_cache: Dict[str, List[str]] = {}


def _is_player_target(target: str) -> bool:
    """True when *target* is a player-level variant (player, player_seasons, player_games)."""
    return target.startswith("player")


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
    targets: List[str],
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
    on_target_finished: Union[
        Callable[[str, str, List[Dict[str, Any]], int, bool, Any], None], None
    ] = None,
    in_season: bool = True,
) -> int:
    """Execute call groups for *table_name* across targets and seasons.

    Only columns referencing *dataset* are included (filtered inside
    ``build_call_groups``).
    """
    total_rows = 0

    for season in seasons:
        for target in targets:
            groups = build_call_groups(
                target,
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
                        "No call groups for target=%s table=%s season=%s",
                        target,
                        table_name,
                        season,
                    )
                    continue

            logger.info(
                "%s %s %s -- %d call groups",
                table_name,
                target,
                season,
                len(groups),
            )

            season_end_year = parse_season_end_year(
                season, LEAGUES[league_code]["season_format"]
            )
            ctx = ExecutionContext(
                target=target,
                table_name=table_name,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names["target_id"][target],
                db_schema=league_code,
                source_code=source_code,
                api_fetcher=make_fetcher(
                    league_code,
                    season_end_year,
                    season_type_name,
                    target,
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
            if on_target_finished is not None:
                with db_connection() as conn:
                    on_target_finished(
                        target,
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


def _get_datasets_by_phase(phase_name: str) -> Dict[str, List[str]]:
    """Return ``{identity_code: [dataset_name, ...]}`` for a pipeline stage."""
    result: Dict[str, List[str]] = {}
    for identity_code, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            if ds_def.get("phase") == phase_name:
                result.setdefault(identity_code, []).append(ds_name)
    return result


def _load_team_ids(league_code: str) -> Dict[str, int]:
    """Return ``{ext_id: int(ext_id)}`` for teams in staging."""
    table = "staging.teams_staging"
    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_code)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ext_id FROM {table} WHERE league_code = %s",
                (league_val,),
            )
            return {r[0]: int(r[0]) for r in cur.fetchall() if r[0] is not None}


# ============================================================================
# detect_season_activity
# ============================================================================


def _detect_season_activity(league_code: str, season: str) -> List[str]:
    """Query detect_season_activity datasets and return active canonical season types."""
    active: List[str] = []
    for identity_code, datasets in DATASETS.items():
        for dataset_name in _get_datasets_by_phase("detect_season_activity").get(
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
# _discover_entities  (maintain_leagues_teams / maintain_teams_players)
# ============================================================================


def _discover_entities(
    league_code: str,
    season: str,
    phase_name: str,
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
    dataset_names = _get_datasets_by_phase(phase_name).get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_code)
    targets = ["players"] if phase_name == "maintain_teams_players" else ["teams"]
    roster_targets = (
        ["teams_players"]
        if phase_name == "maintain_teams_players"
        else ["leagues_teams"]
    )

    from datetime import datetime, timezone

    for dataset_name in dataset_names:
        logger.info(
            phase_marker(
                phase_name,
                f"dataset={identity_code}.{dataset_name} source={source_code}",
            )
        )

        ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
        prune_tables = ds_cfg.get("prune_tables")
        prune_start = datetime.now(timezone.utc) if prune_tables else None

        # Profile columns → players / teams staging
        for target in targets:
            total_rows += _run_groups(
                table_name=target,
                targets=[target],
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids if _is_player_target(target) else {},
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

        # Roster links → teams_players / leagues_teams staging
        for target in roster_targets:
            total_rows += _run_groups(
                table_name=target,
                targets=[target],
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
                    qualified = f"staging.{tbl}"
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
# maintain_season_coverages  (backfill)
# ============================================================================


def _maintain_season_coverages(
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
    dataset_names = _get_datasets_by_phase("maintain_current_seasons").get(
        identity_code, []
    )
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_code)
    all_season_types = get_all_canonical_season_types(league_code)

    stats_targets = ["player_seasons", "team_seasons"]

    for dataset_name in dataset_names:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue

                season_type_name = get_source_season_type_code(
                    source_code, league_code, st_key
                )

                for target in stats_targets:
                    table_name = target
                    groups = build_call_groups(
                        target,
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
                                target,
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
                        target=target,
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
# maintain_current_games  (current season game-level refresh)
# ============================================================================


def _maintain_current_games(
    league_code: str,
    season: str,
    identity_code: str,
    source_code: str,
    active_types: List[str],
    failed: List[Dict[str, Any]],
) -> int:
    """Refresh game-level stats for the CURRENT season and ACTIVE season types."""
    from src.core.lib.leagues_resolver import is_season_type_valid_for

    total_rows = 0
    dataset_names = _get_datasets_by_phase("maintain_current_games").get(
        identity_code, []
    )
    if not dataset_names:
        return 0

    game_targets = ["player_games", "team_games"]

    for st_key in active_types:
        if not is_season_type_valid_for(league_code, st_key, season):
            continue

        season_type_name = get_source_season_type_code(source_code, league_code, st_key)

        for dataset_name in dataset_names:
            for target in game_targets:
                table_name = target
                groups = build_call_groups(
                    target,
                    season,
                    identity_code,
                    dataset=dataset_name,
                    table_name=table_name,
                    league_code=league_code,
                    in_season=True,
                )
                if not groups:
                    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
                    if ds_cfg.get("discovery_tables"):
                        groups = [
                            {
                                "dataset": dataset_name,
                                "params": {},
                                "tier": ds_cfg.get("execution_tier", "per_league"),
                                "columns": {},
                            }
                        ]
                    else:
                        continue

                total_rows += _execute_stats_groups(
                    league_code=league_code,
                    target=target,
                    season_label=season,
                    st_key=st_key,
                    season_type_name=season_type_name,
                    identity_code=identity_code,
                    source_code=source_code,
                    dataset=dataset_name,
                    filtered_groups=groups,
                    team_ids={},
                    failed=failed,
                    use_coverage=True,
                )

    return total_rows


# ============================================================================
# maintain_game_coverages  (game-level coverage backfill)
# ============================================================================


def _maintain_game_coverages(
    league_code: str,
    season_range: List[str],
    identity_code: str,
    source_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Ensure every retained season x season type has game-level coverage.

    Same pattern as _maintain_season_coverages but operates at game granularity
    via the game_coverages table.
    """
    from src.core.lib.leagues_resolver import (
        get_all_canonical_season_types,
        is_season_type_valid_for,
    )
    from src.etl.lib.coverage_tracker import is_game_coverage_current

    total_rows = 0
    dataset_names = _get_datasets_by_phase("maintain_current_games").get(
        identity_code, []
    )
    if not dataset_names:
        return 0

    all_season_types = get_all_canonical_season_types(league_code)
    game_targets = ["player_games", "team_games"]

    for dataset_name in dataset_names:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue

                season_type_name = get_source_season_type_code(
                    source_code, league_code, st_key
                )

                for target in game_targets:
                    table_name = target
                    groups = build_call_groups(
                        target,
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
                            if not is_game_coverage_current(
                                conn,
                                league_code,
                                target,
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
                        target=target,
                        season_label=season_label,
                        st_key=st_key,
                        season_type_name=season_type_name,
                        identity_code=identity_code,
                        source_code=source_code,
                        dataset=dataset_name,
                        filtered_groups=filtered_groups,
                        team_ids={},
                        failed=failed,
                        use_coverage=True,
                    )

    return total_rows


# ============================================================================
# maintain_current_seasons  (current season refresh)
# ============================================================================


def _maintain_current_seasons(
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
    dataset_names = _get_datasets_by_phase("maintain_current_seasons").get(
        identity_code, []
    )
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_code)
    stats_targets = ["player_seasons", "team_seasons"]

    for st_key in active_types:
        if not is_season_type_valid_for(league_code, st_key, season):
            continue

        season_type_name = get_source_season_type_code(source_code, league_code, st_key)

        for dataset_name in dataset_names:
            for target in stats_targets:
                table_name = target
                groups = build_call_groups(
                    target,
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
                    target=target,
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
    target: str,
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
    """Execute stats call groups for a single dataset / target slice."""
    from src.etl.lib.coverage_tracker import (
        upsert_game_coverage,
        upsert_group_coverage,
    )

    if not filtered_groups:
        return 0

    ds_cfg = DATASETS.get(identity_code, {}).get(dataset, {})
    src_key = ds_cfg.get("source", source_code)

    logger.info(
        phase_marker(
            "stats",
            f"target={target} season={season_label} "
            f"season_type={st_key} "
            f"dataset={dataset} "
            f"groups={len(filtered_groups)}",
        )
    )

    table_name = target
    config_mod, client_mod = _load_source(src_key)
    is_game = target.endswith("_games")

    def _on_coverage(
        target,
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
        upsert_fn = upsert_game_coverage if is_game else upsert_group_coverage
        for g in succeeded_groups:
            if is_game:
                upsert_fn(
                    conn,
                    _league_key,
                    target,
                    season_label,
                    _season_type,
                    _source_key,
                    "",  # ext_game_id — filled per-game by the executor
                    g,
                )
            else:
                upsert_fn(
                    conn,
                    _league_key,
                    target,
                    season_label,
                    _season_type,
                    _source_key,
                    g,
                )

    return _run_groups(
        table_name=table_name,
        targets=[target],
        seasons=[season_label],
        season_type=st_key,
        season_type_name=season_type_name,
        team_ids=team_ids if _is_player_target(target) else {},
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
        on_target_finished=_on_coverage if use_coverage else None,
    )


# ============================================================================
# maintain_profiles
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
    dataset_names = _get_datasets_by_phase("maintain_profiles").get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_code)

    for dataset_name in dataset_names:
        for target in ["teams", "players"]:
            logger.info(
                phase_marker(
                    "maintain_profiles",
                    f"dataset={identity_code}.{dataset_name} target={target}",
                )
            )
            total_rows += _run_groups(
                table_name=target,
                targets=[target],
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
# ENTITY MATCHING, MERGE, UPSERT, CASCADE DELETE
# ============================================================================


def _shared_profile_columns(entity: str) -> List[str]:
    """Return columns declared on both the core and staging table for *entity*.

    Excludes staging-metadata columns (identity, ext_id, matched_sts_id,
    reviewed) and core-generated columns (sts_id).
    """
    core_table = entity  # "players" or "teams"
    staging_table = f"{entity}_staging"
    exclude = {
        "identity",
        "ext_id",
        "matched_sts_id",
        "reviewed",
        "sts_id",
        "league_code",
    }
    shared = []
    for col_name, col_meta in DB_COLUMNS.items():
        tables = col_meta.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        if core_table in tables and staging_table in tables and col_name not in exclude:
            shared.append(col_name)
    return shared


def _league_identity_order() -> List[Tuple[str, str]]:
    """Return all (league_code, identity_code) pairs in priority order.

    Priority: league order from LEAGUES, then identity order from DATASETS.
    """
    pairs = []
    for league_code in LEAGUES:
        for identity_code in DATASETS:
            pairs.append((league_code, identity_code))
    return pairs


def _match_entities(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Cross-league: match all staging identities against identity registries.

    Sets matched_sts_id and reviewed=True on every staging row whose
    (identity, ext_id) pair exists.  Overwrites previously-set values.
    """
    logger.info(phase_marker("match_entities"))
    total_matched = 0

    match_pairs = [
        ("staging.players_staging", "core.identities_players", "player_id"),
        ("staging.teams_staging", "core.identities_teams", "team_id"),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for staging_table, identity_table, id_col in match_pairs:
                sql = f"""
                    UPDATE {staging_table} s
                       SET matched_sts_id = i.{quote_col(id_col)},
                           reviewed = TRUE
                      FROM {identity_table} i
                     WHERE s.identity = i.identity
                       AND s.ext_id = i.ext_id
                """
                cur.execute(sql)
                matched = cur.rowcount
                total_matched += matched
                if matched:
                    entity = "player" if "players" in staging_table else "team"
                    logger.info(
                        "Matched %d staged %ss to existing sts_ids", matched, entity
                    )
        conn.commit()

    return total_matched


def _merge_staging(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Merge reviewed=True staging rows that share the same matched_sts_id.

    For each group of rows with the same non-null matched_sts_id:
      - First row (by league/identity priority order) is the base.
      - Subsequent rows fill NULLs in the base (first-write-wins).
      - Non-base rows are deleted.

    Returns the number of rows deleted.
    """
    logger.info(phase_marker("merge_staging"))
    total_deleted = 0

    priority_order = _league_identity_order()
    # Build (league_code, identity) → rank
    rank = {pair: i for i, pair in enumerate(priority_order)}

    for entity, staging_table in [
        ("player", "staging.players_staging"),
        ("team", "staging.teams_staging"),
    ]:
        shared_cols = _shared_profile_columns(entity)
        if not shared_cols:
            continue

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Fetch all reviewed rows with a matched_sts_id, grouped
                cur.execute(
                    f"""
                    SELECT matched_sts_id, league_code, identity, ext_id,
                           {", ".join(quote_col(c) for c in shared_cols)}
                      FROM {staging_table}
                     WHERE reviewed = TRUE
                       AND matched_sts_id IS NOT NULL
                  ORDER BY matched_sts_id
                    """
                )
                rows = cur.fetchall()

            if not rows:
                continue

            # Group by matched_sts_id
            col_names = [
                "matched_sts_id",
                "league_code",
                "identity",
                "ext_id",
            ] + shared_cols
            groups: Dict[int, List[Dict[str, Any]]] = {}
            for row in rows:
                d = dict(zip(col_names, row))
                msid = d["matched_sts_id"]
                groups.setdefault(msid, []).append(d)

            # Merge groups with duplicates
            delete_keys: List[Tuple[str, str]] = []
            for msid, group in groups.items():
                if len(group) < 2:
                    continue

                # Sort by league/identity priority
                group.sort(
                    key=lambda r: rank.get((r["league_code"], r["identity"]), 9999)
                )
                base = group[0]
                merged = dict(base)

                for other in group[1:]:
                    for col in shared_cols:
                        if merged.get(col) is None and other.get(col) is not None:
                            merged[col] = other[col]
                    delete_keys.append((other["identity"], other["ext_id"]))

                # Update base row with merged values
                set_clauses = [
                    f"{quote_col(c)} = %s"
                    for c in shared_cols
                    if merged.get(c) != base.get(c)
                ]
                if set_clauses:
                    values = [
                        merged[c] for c in shared_cols if merged.get(c) != base.get(c)
                    ]
                    cur.execute(
                        f"UPDATE {staging_table} SET {', '.join(set_clauses)} "
                        f"WHERE identity = %s AND ext_id = %s",
                        values + [base["identity"], base["ext_id"]],
                    )

            # Delete non-base rows
            if delete_keys:
                for identity, ext_id in delete_keys:
                    cur.execute(
                        f"DELETE FROM {staging_table} WHERE identity = %s AND ext_id = %s",
                        (identity, ext_id),
                    )
                    total_deleted += cur.rowcount

            conn.commit()

    return total_deleted


def _promote_profiles(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote reviewed=True staging rows to core profile tables.

    For each reviewed row:
      - If matched_sts_id is NULL: auto-create the core entity row
        (sts_id from sequence), then link via identities_*.
      - If matched_sts_id is set: upsert into core, updating profile
        columns (first-write-wins on core).

    Only shared profile columns (declared on both staging and core in
    db_columns) are promoted.  Staging metadata columns are excluded.
    """
    logger.info(phase_marker("upsert_entities"))
    total_upserted = 0

    for entity, staging_table, core_table, identity_table, id_col in [
        (
            "player",
            "staging.players_staging",
            "core.players",
            "core.identities_players",
            "player_id",
        ),
        (
            "team",
            "staging.teams_staging",
            "core.teams",
            "core.identities_teams",
            "team_id",
        ),
    ]:
        shared_cols = _shared_profile_columns(entity)
        if not shared_cols:
            continue

        core_short = core_table.split(".", 1)[-1]

        with db_connection() as conn:
            with conn.cursor() as cur:
                # 1) Pre-assign sts_ids for reviewed rows missing matched_sts_id.
                #    Consume the sequence first so the same value can be used
                #    for both core.{entity} and identities_{entity}.
                cur.execute(
                    f"""
                    UPDATE {staging_table}
                       SET matched_sts_id = nextval('core.sts_id_seq')
                     WHERE reviewed = TRUE
                       AND matched_sts_id IS NULL
                    """
                )
                assigned = cur.rowcount
                if assigned:
                    logger.info(
                        "Assigned %d new sts_ids to %s staging", assigned, entity
                    )

                # 2) Upsert profile rows: insert or update shared columns into core.
                select_cols = ["s.matched_sts_id AS sts_id"]
                select_cols += [f"s.{quote_col(c)}" for c in shared_cols]

                insert_cols = ["sts_id"] + shared_cols
                insert_sql = ", ".join(quote_col(c) for c in insert_cols)
                select_sql = ", ".join(select_cols)

                update_sql = ", ".join(
                    f"{quote_col(c)} = COALESCE({core_short}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
                    for c in shared_cols
                )

                cur.execute(
                    f"""
                    INSERT INTO {core_table} ({insert_sql})
                    SELECT {select_sql}
                      FROM {staging_table} s
                     WHERE s.reviewed = TRUE
                       AND s.matched_sts_id IS NOT NULL
                    ON CONFLICT (sts_id) DO UPDATE SET {update_sql}
                    """
                )
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info(
                        "Upserted %d %s rows from staging to core", upserted, entity
                    )

                # 3) Populate identities table — link external IDs to sts_ids.
                #    ON CONFLICT DO NOTHING because a previous ETL run may have
                #    already registered this identity.
                cur.execute(
                    f"""
                    INSERT INTO {identity_table} (identity, ext_id, {quote_col(id_col)})
                    SELECT s.identity, s.ext_id, s.matched_sts_id
                      FROM {staging_table} s
                     WHERE s.reviewed = TRUE
                       AND s.matched_sts_id IS NOT NULL
                    ON CONFLICT (identity, ext_id) DO NOTHING
                    """
                )
                linked = cur.rowcount
                if linked:
                    logger.info("Linked %d %s identities", linked, entity)

            conn.commit()

    return total_upserted


def _promote_rosters(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote reviewed staging roster rows to core roster tables.

    Resolves ``ext_player_id`` / ``ext_team_id`` to internal sts_ids
    via ``identities_players`` / ``identities_teams``.
    """
    logger.info(phase_marker("promote_rosters"))
    total_upserted = 0

    roster_mappings = [
        (
            "staging.teams_players_staging",
            "core.teams_players",
            ["league_code", "team_id", "player_id"],
            [
                "s.league_code",
                "team_ie.team_id",
                "player_ie.player_id",
            ],
            ["league_code", "team_id", "player_id"],
        ),
        (
            "staging.leagues_teams_staging",
            "core.leagues_teams",
            ["league_code", "team_id"],
            ["s.league_code", "team_ie.team_id"],
            ["league_code", "team_id"],
        ),
        (
            "staging.countries_players_staging",
            "core.countries_players",
            ["country_code", "player_id"],
            ["s.country_code", "player_ie.player_id"],
            ["country_code", "player_id"],
        ),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for (
                staging_table,
                core_table,
                insert_cols,
                select_cols,
                conflict_cols,
            ) in roster_mappings:
                needs_player = (
                    "player" in staging_table or "countries_players" in core_table
                )
                needs_team = "team" in staging_table or "leagues_teams" in core_table

                from_clause = f"{staging_table} s"
                if needs_player:
                    from_clause += (
                        "\n        JOIN core.identities_players player_ie"
                        "\n          ON s.identity = player_ie.identity"
                        "\n         AND s.ext_player_id = player_ie.ext_id"
                    )
                if needs_team:
                    from_clause += (
                        "\n        JOIN core.identities_teams team_ie"
                        "\n          ON s.identity = team_ie.identity"
                        "\n         AND s.ext_team_id = team_ie.ext_id"
                    )

                insert_sql = ", ".join(quote_col(c) for c in insert_cols)
                select_sql = ", ".join(select_cols)
                conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)

                cur.execute(
                    f"""
                    INSERT INTO {core_table} ({insert_sql})
                    SELECT {select_sql}
                      FROM {from_clause}
                     WHERE s.league_code IS NOT NULL
                       AND EXISTS (
                           SELECT 1 FROM staging.teams_staging ts
                            WHERE ts.identity = s.identity
                              AND ts.ext_id = COALESCE(s.ext_team_id, s.ext_player_id)
                              AND ts.reviewed = TRUE
                       )
                    ON CONFLICT ({conflict_sql}) DO NOTHING
                    """
                )
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info("Promoted %d rows to %s", upserted, core_table)
        conn.commit()

    return total_upserted


def _promote_stats(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote reviewed staging stats rows to core stats tables.

    Resolves ``ext_player_id`` / ``ext_team_id`` to internal sts_ids
    via ``identities_players`` / ``identities_teams``.  Shared stat
    columns are promoted by direct name match from db_columns.
    """
    logger.info(phase_marker("promote_stats"))
    total_upserted = 0

    for entity in ("player", "team"):
        staging_table = f"staging.{entity}_seasons_staging"
        core_table = f"core.{entity}_seasons"

        # Stats columns shared between staging and core
        from src.core.definitions.db_columns import DB_COLUMNS

        shared_cols = []
        for col_name, col_meta in DB_COLUMNS.items():
            tables = col_meta.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            if f"{entity}_seasons" in tables and f"{entity}_seasons_staging" in tables:
                shared_cols.append(col_name)

        if not shared_cols:
            continue

        # Build select/insert column lists
        select_cols = ["s.league_code"]
        if entity == "player":
            select_cols += [
                "player_ie.player_id",
                "team_ie.team_id",
                "s.season",
                "s.season_type",
            ]
            insert_cols = [
                "league_code",
                "player_id",
                "team_id",
                "season",
                "season_type",
            ]
        else:
            select_cols += [
                "team_ie.team_id",
                "s.season",
                "s.season_type",
            ]
            insert_cols = ["league_code", "team_id", "season", "season_type"]

        conflict_cols = list(insert_cols)

        for c in shared_cols:
            select_cols.append(f"s.{quote_col(c)}")
            insert_cols.append(c)

        insert_sql = ", ".join(quote_col(c) for c in insert_cols)
        select_sql = ", ".join(select_cols)
        conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)

        from_clause = f"{staging_table} s"
        if entity == "player":
            from_clause += (
                "\n        JOIN core.identities_players player_ie"
                "\n          ON s.identity = player_ie.identity"
                "\n         AND s.ext_player_id = player_ie.ext_id"
                "\n        JOIN core.identities_teams team_ie"
                "\n          ON s.identity = team_ie.identity"
                "\n         AND s.ext_team_id = team_ie.ext_id"
            )
        else:
            from_clause += (
                "\n        JOIN core.identities_teams team_ie"
                "\n          ON s.identity = team_ie.identity"
                "\n         AND s.ext_team_id = team_ie.ext_id"
            )

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {core_table} ({insert_sql})
                    SELECT {select_sql}
                      FROM {from_clause}
                     WHERE EXISTS (
                           SELECT 1 FROM staging.{entity}s_staging ps
                            WHERE ps.identity = s.identity
                              AND ps.ext_id = s.ext_{entity}_id
                              AND ps.reviewed = TRUE
                       )
                    ON CONFLICT ({conflict_sql}) DO NOTHING
                    """
                )
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info("Promoted %d rows to %s", upserted, core_table)
        conn.commit()

    return total_upserted


def _cascade_delete_reviewed(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Delete reviewed=True profile staging rows.

    All dependent staging tables (rosters, stats) have ON DELETE CASCADE
    foreign keys to players_staging and teams_staging, so the database
    handles cascading automatically.
    """
    logger.info(phase_marker("cascade_delete_reviewed"))
    total_deleted = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            for table in ("staging.players_staging", "staging.teams_staging"):
                cur.execute(f"DELETE FROM {table} WHERE reviewed = TRUE")
                deleted = cur.rowcount
                if deleted:
                    logger.info(
                        "Deleted %d reviewed rows from %s (+ cascaded)", deleted, table
                    )
                total_deleted += deleted
        conn.commit()

    return total_deleted


# ============================================================================
# TOP-LEVEL RUNNER
# ============================================================================


def run_etl(
    league_code: Union[str, None] = None,
    stage: Union[str, None] = None,
) -> None:
    """Run all ETL phase clusters for a league or all leagues.

    *stage* restricts execution to a subset of clusters:
        ``"ingest"``  — execution_start + per_league + per_identity
        ``"promote"`` — execution_end
        ``None``      — full pipeline (default)
    """
    if league_code:
        if league_code not in LEAGUES:
            raise ValueError(
                f"Unknown league {league_code!r}. Registered: {sorted(LEAGUES)}"
            )
        leagues_to_run = [league_code]
    else:
        leagues_to_run = list(LEAGUES)

    run_start = stage in (None, "ingest")
    run_end = stage in (None, "promote")

    if run_start:
        _run_cluster("execution_start", leagues_to_run[0])
        for lcode in leagues_to_run:
            _run_cluster("per_league", lcode)
            _run_cluster("per_identity", lcode)

    if run_end:
        _run_cluster("execution_end", leagues_to_run[0])


def _run_cluster(cluster: str, league_code: str) -> None:
    handlers = PIPELINE.get(cluster, [])
    if not handlers:
        return

    logger.info("=" * 80)
    logger.info("Cluster: %s", cluster)
    logger.info("=" * 80)

    try:
        _run_phases(league_code, phases, cluster, season_range=None)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        raise
    except Exception:
        logger.exception(
            "ETL run failed for league %s in cluster %s.", league_code, cluster
        )


def _run_phases(
    league_code: str,
    phases: List[str],
    cluster: str,
    season_range: Union[List[str], None] = None,
) -> int:
    """Run phases for a single league for a single league. Returns total rows written."""
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

    ctx = {
        "league_code": league_code,
        "season": season,
        "season_range": season_range,
        "failed": failed,
        "total_rows": total_rows,
    }

    for phase in phases:
        fn = _resolve_phase(phase_name)
        total_rows += fn(ctx)

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)

    return total_rows


# ═══════════════════════════════════════════════════════════════════════════
# Phase dispatch
# ═══════════════════════════════════════════════════════════════════════════


def _phase_build_schema(ctx: dict) -> int:
    logger.info(phase_marker("build_schema"))
    with db_connection() as conn:
        bootstrap_schema(ctx["league_code"], conn=conn)
    return 0


def _phase_detect_season_activity(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    logger.info(phase_marker("detect_season_activity"))
    active = _detect_season_activity(league_code, season)
    _active_types_cache[league_code] = active
    logger.info("Season detector result: active=%s in_season=%s", active, bool(active))
    return 0


def _phase_maintain_leagues_teams(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    failed = ctx["failed"]
    total_rows = 0
    handler = "maintain_leagues_teams"
    logger.info(phase_marker(handler))

    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase(handler).get(identity_code, [])
        if not phase_datasets:
            continue
        source_code = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[source_code].get("leagues", {}):
            continue
        logger.info(
            "  identity=%s source=%s datasets=%s",
            identity_code,
            source_code,
            phase_datasets,
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
            team_ids={},
        )
    return total_rows


def _phase_maintain_teams_players(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    failed = ctx["failed"]
    total_rows = 0
    handler = "maintain_teams_players"
    logger.info(phase_marker(handler))
    team_ids = _load_team_ids(league_code)

    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase(handler).get(identity_code, [])
        if not phase_datasets:
            continue
        source_code = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[source_code].get("leagues", {}):
            continue
        logger.info(
            "  identity=%s source=%s datasets=%s",
            identity_code,
            source_code,
            phase_datasets,
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
    return total_rows


def _phase_maintain_games(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season_range = ctx["season_range"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_games"))
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase("maintain_games").get(identity_code, [])
        if not phase_datasets:
            continue
        source_code = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[source_code].get("leagues", {}):
            continue
        total_rows += _maintain_games(
            league_code, season_range, identity_code, source_code, failed
        )
    return total_rows


def _phase_maintain_seasons(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season_range = ctx["season_range"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_seasons"))
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase("maintain_seasons").get(
            identity_code, []
        )
        if not phase_datasets:
            continue
        source_code = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[source_code].get("leagues", {}):
            continue
        total_rows += _maintain_seasons(
            league_code, season_range, identity_code, source_code, failed
        )
    return total_rows


def _phase_maintain_profiles(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_profiles"))
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase("maintain_profiles").get(
            identity_code, []
        )
        if not phase_datasets:
            continue
        source_code = DATASETS[identity_code][phase_datasets[0]]["source"]
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
    return total_rows


def _phase_match_entities(ctx: dict) -> int:
    return _match_entities(ctx["league_code"], ctx["failed"])


def _phase_merge_staging(ctx: dict) -> int:
    return _merge_staging(ctx["league_code"], ctx["failed"])


def _phase_promote_profiles(ctx: dict) -> int:
    return _promote_profiles(ctx["league_code"], ctx["failed"])


def _phase_promote_rosters(ctx: dict) -> int:
    return _promote_rosters(ctx["league_code"], ctx["failed"])


def _phase_promote_stats(ctx: dict) -> int:
    return _promote_stats(ctx["league_code"], ctx["failed"])


def _phase_cascade_delete_reviewed(ctx: dict) -> int:
    return _cascade_delete_reviewed(ctx["league_code"], ctx["failed"])


def _phase_normalize_nulls_zeroes(ctx: dict) -> int:
    logger.info(phase_marker("normalize_nulls_zeroes"))
    return normalize_nulls_zeroes()


def _phase_prune_stats_retention(ctx: dict) -> int:
    logger.info(phase_marker("prune_stats_retention"))
    return prune_stats_retention(current_season=ctx["season"])


def _phase_prune_entities(ctx: dict) -> int:
    logger.info(phase_marker("prune_entities"))
    result = prune_entities()
    return result.get("players", 0) + result.get("teams", 0)


def _phase_prune_season_coverages(ctx: dict) -> int:
    logger.info(phase_marker("prune_season_coverages"))
    return prune_season_coverages(ctx["league_code"])


def _phase_prune_game_coverages(ctx: dict) -> int:
    logger.info(phase_marker("prune_game_coverages"))
    return prune_game_coverages(ctx["league_code"])


def _resolve_phase(name: str) -> Callable:
    """Return the handler function for *name* via naming convention.

    Raises RuntimeError at import time if a handler listed in
    PIPELINE has no corresponding ``_phase_{name}`` function.
    """
    func = globals().get(f"_phase_{name}")
    if func is None:
        raise RuntimeError(
            f"Phase {name!r} listed in PIPELINE but no "
            f"implementation _phase_{name!r} found in orchestrator"
        )
    return func


# Validate every handler at import time so missing implementations fail fast.
for _name in VALID_PHASES:
    _resolve_phase(_name)
