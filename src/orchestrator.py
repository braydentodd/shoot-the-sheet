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

    src.cli          (argparse + dispatch)
        |
        v
    src.orchestrator  (this module: phase ordering)
        |
        +--> src.lib.schema_builder         (schema bootstrap)
        +--> src.lib.load                   (staging + profile writes)
        +--> src.lib.executor               (one API call group)
        +--> src.lib.cleanup                (post-run hygiene)

Each phase is a thin wrapper around the lib function it drives; orchestration
logic that has no business in lib (e.g. resolving the active source, building
ExecutionContext) lives here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple, Union

from psycopg2 import sql
from psycopg2.extras import RealDictCursor, execute_values

from src.definitions.datasets import DATASETS
from src.definitions.db_columns import DB_COLUMNS
from src.definitions.execution import GAME_LOOKBACK_DAYS
from src.definitions.leagues import LEAGUES
from src.definitions.pipeline import PIPELINE
from src.definitions.sources import SOURCES
from src.definitions.validation import VALID_ENTITY_TYPES
from src.lib.call_grouper import build_call_groups
from src.lib.cleanup import (
    normalize_nulls_zeroes,
    prune_entities,
    prune_stats_retention,
)
from src.lib.console_logger import phase_marker
from src.lib.coverage_tracker import (
    is_coverage_current,
    prune_coverage,
    seed_coverage,
)
from src.lib.executor import ExecutionContext, execute_group
from src.lib.leagues_resolver import (
    _league_or_raise,
    get_current_season,
    get_regular_season_types,
    get_retained_seasons,
)
from src.lib.load import _resolve_league_id
from src.lib.postgres import db_connection, quote_col
from src.lib.schema_builder import bootstrap_schema
from src.lib.season_detector import _check_recent_games
from src.lib.season_formatter import parse_season_end_year
from src.lib.source_resolver import get_source_season_type_code
from src.sources.registry import get_source_modules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Every target writes to its namesake table (e.g. "players" → players).
# ---------------------------------------------------------------------------

_active_types_cache: Dict[str, List[str]] = {}


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
    identity_code: str,
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
        # Build call groups once per season — all columns across all targets
        groups = build_call_groups(
            season,
            identity_code,
            dataset=dataset,
            table_name=table_name,
            league_code=league_code,
            in_season=in_season,
        )

        if not groups:
            ds_cfg = DATASETS.get(identity_code, {}).get(dataset, {})
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
                    "No call groups for table=%s season=%s",
                    table_name,
                    season,
                )
                continue

        logger.info(
            "%s %s -- %d call groups",
            table_name,
            season,
            len(groups),
        )

        season_end_year = parse_season_end_year(
            season, LEAGUES[league_code]["season_format"]
        )

        # One shared fetcher — all targets extract from the same API response
        shared_fetcher = make_fetcher(
            league_code,
            season_end_year,
            season_type_name,
            identity_code=identity_code,
        )

        for group in groups:
            # Fetch once per group
            dataset_name = group["dataset"]
            try:
                result = shared_fetcher(dataset_name, group.get("params"))
            except Exception as exc:
                logger.exception("Group %s fetch failed: %s", dataset_name, exc)
                failed.append({"dataset": dataset_name, "error": str(exc)})
                continue

            if result is None:
                continue

            group_succeeded = False
            for target in targets:
                ctx = ExecutionContext(
                    target=target,
                    table_name=table_name,
                    season=season,
                    season_type=season_type,
                    season_type_name=season_type_name,
                    entity_id_field=api_field_names["target_id"][target],
                    db_schema=league_code,
                    identity_code=identity_code,
                    api_fetcher=shared_fetcher,
                    team_ids=team_ids,
                    max_consecutive_failures=api_config.get(
                        "max_consecutive_failures", 5
                    ),
                    id_aliases=api_field_names.get("id_aliases", {}),
                )

                try:
                    rows = execute_group(group, ctx, failed, result=result)
                    total_rows += rows
                    if rows:
                        group_succeeded = True
                except Exception as exc:
                    logger.exception(
                        "Group %s target %s failed: %s",
                        dataset_name,
                        target,
                        exc,
                    )
                    failed.append(
                        {
                            "dataset": dataset_name,
                            "target": target,
                            "error": str(exc),
                        }
                    )

            if group_succeeded and on_target_finished is not None:
                with db_connection() as conn:
                    for target in targets:
                        on_target_finished(
                            target,
                            season,
                            [group],
                            0,  # rows already counted
                            False,
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
    table = "staging.teams"
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
    identity_source: str,
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

    config_mod, client_mod = _load_source(identity_source)
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
                f"dataset={identity_code}.{dataset_name} source={identity_source}",
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
                team_ids=team_ids if ds_cfg.get("execution_tier") == "per_team" else {},
                failed=failed,
                league_code=league_code,
                identity_code=identity_code,
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
                identity_code=identity_code,
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
# maintain_seasons  (active-type current + coverage backfill)
# ============================================================================


def _maintain_seasons(
    league_code: str,
    season: str,
    season_range: List[str],
    identity_code: str,
    identity_source: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Fetch season-level stats in two passes.

    Part A — Active types x current season: always fetch if the season
    detector identified active types (no coverage check — current season
    data may have changed).

    Part B — Coverage backfill: iterate every season in *season_range*
    for every declared season type.  Coverage tracking gates re-fetching.
    """
    from src.lib.leagues_resolver import (
        get_all_canonical_season_types,
        is_season_type_valid_for,
    )

    total_rows = 0
    dataset_names = _get_datasets_by_phase("maintain_seasons").get(identity_code, [])
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_code)
    all_season_types = get_all_canonical_season_types(league_code)
    stats_targets = ["player_seasons", "team_seasons"]
    active_types = _active_types_cache.get(league_code, [])

    # ── Part A: active types x current season (no coverage check) ──────────
    if active_types:
        logger.info(
            phase_marker(
                "maintain_seasons",
                f"active types={active_types} season={season}",
            )
        )
        for st_key in active_types:
            if not is_season_type_valid_for(league_code, st_key, season):
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, st_key
            )
            for dataset_name in dataset_names:
                for target in stats_targets:
                    groups = build_call_groups(
                        season,
                        identity_code,
                        dataset=dataset_name,
                        table_name=target,
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
                        identity_source=identity_source,
                        dataset=dataset_name,
                        filtered_groups=groups,
                        team_ids=team_ids,
                        failed=failed,
                        use_coverage=True,
                    )

    # ── Part B: coverage backfill (all seasons x all types) ────────────────
    for dataset_name in dataset_names:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, st_key
                )
                for target in stats_targets:
                    groups = build_call_groups(
                        season_label,
                        identity_code,
                        dataset=dataset_name,
                        table_name=target,
                        league_code=league_code,
                        in_season=True,
                    )
                    if not groups:
                        continue
                    with db_connection() as conn:
                        filtered_groups = [
                            g
                            for g in groups
                            if not is_coverage_current(
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
                        identity_source=identity_source,
                        dataset=dataset_name,
                        filtered_groups=filtered_groups,
                        team_ids=team_ids,
                        failed=failed,
                        use_coverage=True,
                    )

    return total_rows


# ============================================================================
# maintain_games  (active-type current + coverage backfill)
# ============================================================================


def _maintain_games(
    league_code: str,
    season: str,
    season_range: List[str],
    identity_code: str,
    identity_source: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Fetch game-level stats in two passes.

    Part A — Active types x current season: always fetch if the season
    detector identified active types.

    Part B — Coverage backfill: iterate every season in *season_range*
    for every declared season type.  Coverage tracking gates re-fetching.
    """
    from src.lib.leagues_resolver import (
        get_all_canonical_season_types,
        is_season_type_valid_for,
    )

    total_rows = 0
    dataset_names = _get_datasets_by_phase("maintain_games").get(identity_code, [])
    if not dataset_names:
        return 0

    all_season_types = get_all_canonical_season_types(league_code)
    game_targets = ["player_games", "team_games"]
    active_types = _active_types_cache.get(league_code, [])

    # ── Part A: active types x current season (no coverage check) ──────────
    if active_types:
        logger.info(
            phase_marker(
                "maintain_games",
                f"active types={active_types} season={season}",
            )
        )
        for st_key in active_types:
            if not is_season_type_valid_for(league_code, st_key, season):
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, st_key
            )
            for dataset_name in dataset_names:
                for target in game_targets:
                    groups = build_call_groups(
                        season,
                        identity_code,
                        dataset=dataset_name,
                        table_name=target,
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
                        identity_source=identity_source,
                        dataset=dataset_name,
                        filtered_groups=groups,
                        team_ids={},
                        failed=failed,
                        use_coverage=True,
                    )

    # ── Part B: coverage backfill (all seasons x all types) ────────────────
    for dataset_name in dataset_names:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, st_key
                )
                for target in game_targets:
                    groups = build_call_groups(
                        season_label,
                        identity_code,
                        dataset=dataset_name,
                        table_name=target,
                        league_code=league_code,
                        in_season=True,
                    )
                    if not groups:
                        continue
                    with db_connection() as conn:
                        filtered_groups = [
                            g
                            for g in groups
                            if not is_coverage_current(
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
                        identity_source=identity_source,
                        dataset=dataset_name,
                        filtered_groups=filtered_groups,
                        team_ids={},
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
    identity_source: str,
    dataset: str,
    filtered_groups: List[Dict[str, Any]],
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    use_coverage: bool,
) -> int:
    """Execute stats call groups for a single dataset / target slice."""
    from src.lib.coverage_tracker import upsert_coverage

    if not filtered_groups:
        return 0

    ds_cfg = DATASETS.get(identity_code, {}).get(dataset, {})
    src_key = ds_cfg.get("source", identity_source)

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
        for g in succeeded_groups:
            upsert_coverage(
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
        team_ids=team_ids if ds_cfg.get("execution_tier") == "per_team" else {},
        failed=failed,
        league_code=league_code,
        identity_code=identity_code,
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
    identity_source: str,
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

    config_mod, client_mod = _load_source(identity_source)

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
                identity_code=identity_code,
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
    staging_table = entity  # same bare name as core - staging prefix handled by schema
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

    # Table-driven entity matching config:
    # (staging_table_schema, staging_table_name, identity_table_schema, identity_table_name, id_col, entity_type)
    match_pairs = [
        (
            "staging",
            "players",
            "core",
            "identities_players",
            "player_id",
            "player",
        ),
        ("staging", "teams", "core", "identities_teams", "team_id", "team"),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for (
                staging_schema,
                staging_table,
                id_schema,
                id_table,
                id_col,
                entity,
            ) in match_pairs:
                # Use psycopg2.sql for table/column identifiers to prevent SQL injection
                query = sql.SQL(
                    """
                    UPDATE {staging_table} s
                       SET matched_sts_id = i.{id_col},
                           reviewed = TRUE
                      FROM {id_table} i
                     WHERE s.identity = i.identity
                       AND s.ext_id = i.ext_id
                    """
                ).format(
                    staging_table=sql.Identifier(staging_schema, staging_table),
                    id_table=sql.Identifier(id_schema, id_table),
                    id_col=sql.Identifier(id_col),
                )
                cur.execute(query)
                matched = cur.rowcount
                total_matched += matched
                if matched:
                    logger.info(
                        "Matched %d staged %ss to existing sts_ids", matched, entity
                    )
        conn.commit()

    return total_matched


def _match_games(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Resolve staged games to core game_ids via the composite unique key."""
    logger.info(phase_marker("match_games"))
    total = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            # 1) Upsert games from staging using composite unique key
            cur.execute(
                """
                INSERT INTO core.games AS target (
                    date, home_team_id, away_team_id,
                    season, season_type, ot, neutral_site
                )
                SELECT gs.date,
                       home_t.sts_id,
                       away_t.sts_id,
                       gs.season,
                       gs.season_type,
                       gs.ot,
                       gs.neutral_site
                  FROM staging.games gs
                  JOIN core.identities_teams home_t
                    ON home_t.identity = gs.identity
                   AND home_t.ext_id = gs.ext_home_team_id
                  JOIN core.identities_teams away_t
                    ON away_t.identity = gs.identity
                   AND away_t.ext_id = gs.ext_away_team_id
                 WHERE gs.league_code = %s
                   AND gs.reviewed = TRUE
                ON CONFLICT (date, home_team_id, away_team_id)
                DO UPDATE SET season = COALESCE(target.season, EXCLUDED.season),
                              season_type = COALESCE(target.season_type, EXCLUDED.season_type),
                              ot = COALESCE(target.ot, EXCLUDED.ot),
                              neutral_site = COALESCE(target.neutral_site, EXCLUDED.neutral_site)
                """,
                (league_code,),
            )
            upserted = cur.rowcount
            total += upserted
            if upserted:
                logger.info("Upserted %d games", upserted)

            # 2) Populate identities_games — link ext_game_id to game_id
            cur.execute(
                """
                INSERT INTO core.identities_games (identity, ext_id, game_id)
                SELECT gs.identity, gs.ext_game_id, g.game_id
                  FROM staging.games gs
                  JOIN core.games g
                    ON g.date = gs.date
                   AND g.home_team_id = home_t.sts_id
                   AND g.away_team_id = away_t.sts_id
                  JOIN core.identities_teams home_t
                    ON home_t.identity = gs.identity
                   AND home_t.ext_id = gs.ext_home_team_id
                  JOIN core.identities_teams away_t
                    ON away_t.identity = gs.identity
                   AND away_t.ext_id = gs.ext_away_team_id
                 WHERE gs.league_code = %s
                   AND gs.reviewed = TRUE
                ON CONFLICT (identity, ext_id) DO NOTHING
                """,
                (league_code,),
            )
            linked = cur.rowcount
            total += linked
            if linked:
                logger.info("Linked %d game identities", linked)

        conn.commit()

    return total


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
        ("player", "staging.players"),
        ("team", "staging.teams"),
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


def _merge_to_intermediate(
    league_code: str,
    identity: str,
) -> int:
    """Merge staging tables into intermediate tables for a single identity.

    For each of the 9 intermediate tables:
      - SELECT * FROM staging.{table}
      - INSERT INTO intermediate.{table} ... ON CONFLICT UPDATE
      - COALESCE preserves existing values (first-write-wins)

    Called at the end of each per_identity run.
    Returns the number of rows upserted.
    """
    logger.info(phase_marker("merge_to_intermediate", f"identity={identity}"))
    total_upserted = 0

    from src.definitions.db_columns import DB_COLUMNS

    # Only these 9 tables flow through the intermediate layer
    intermediate_tables = [
        "teams",
        "players",
        "leagues_teams",
        "teams_players",
        "team_seasons",
        "player_seasons",
        "games",
        "team_games",
        "player_games",
    ]

    for bare_name in intermediate_tables:
        staging_table = f"staging.{bare_name}"
        intermediate_table = f"intermediate.{bare_name}"

        # Build set of valid column names for this table (both qualified and bare matches)
        cols = []
        for col_name, col_def in DB_COLUMNS.items():
            tables = col_def.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            if "all" in tables:
                cols.append(col_name)
                continue
            for entry in tables:
                if "." in entry:
                    # Qualified: match exact schema.table
                    if entry == staging_table or entry == intermediate_table:
                        cols.append(col_name)
                        break
                else:
                    # Bare: match table name regardless of schema
                    if entry == bare_name:
                        cols.append(col_name)
                        break

        if not cols:
            continue

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Check if staging has rows
                cur.execute(f"SELECT COUNT(*) FROM {staging_table}")
                result = cur.fetchone()
                if result is None or result[0] == 0:
                    continue

                col_list = ", ".join(quote_col(c) for c in cols)
                update_cols = [
                    c
                    for c in cols
                    if c
                    not in ("identity", "ext_id", "sts_id", "game_id", "league_code")
                ]

                # Read primary key from staging table definition
                from src.definitions.schema import get_table

                staging_meta = get_table(staging_table)
                conflict_cols = list(staging_meta.get("primary_key") or [])

                if conflict_cols and update_cols:
                    conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)
                    update_sql = ", ".join(
                        f"{quote_col(c)} = COALESCE({bare_name}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
                        for c in update_cols
                    )
                    cur.execute(
                        f"""
                        INSERT INTO {intermediate_table} AS {bare_name} ({col_list})
                        SELECT {col_list}
                          FROM {staging_table}
                         WHERE identity = %s
                        ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
                        """,
                        (identity,),
                    )
                elif conflict_cols:
                    conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)
                    cur.execute(
                        f"""
                        INSERT INTO {intermediate_table} ({col_list})
                        SELECT {col_list}
                          FROM {staging_table}
                         WHERE identity = %s
                        ON CONFLICT ({conflict_sql}) DO NOTHING
                        """,
                        (identity,),
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {intermediate_table} ({col_list})
                        SELECT {col_list}
                          FROM {staging_table}
                         WHERE identity = %s
                        """,
                        (identity,),
                    )

                upserted = cur.rowcount
                total_upserted += upserted

                if upserted:
                    logger.info(
                        "Merged %d rows from %s to %s",
                        upserted,
                        staging_table,
                        intermediate_table,
                    )

            conn.commit()

    return total_upserted


def _promote_to_core(
    league_code: str,
) -> int:
    """Promote intermediate tables to core tables after all identities complete.

    For each of the 9 intermediate tables:
      - SELECT * FROM intermediate.{table}
      - INSERT INTO core.{table} ... ON CONFLICT UPDATE
      - COALESCE preserves existing core values (first-write-wins)

    Called once in execution_end cluster.
    Returns the number of rows upserted to core.
    """
    logger.info(phase_marker("promote_to_core"))
    total_upserted = 0

    from src.definitions.db_columns import DB_COLUMNS

    # Only the 9 tables that flow through intermediate
    promote_tables = [
        "teams",
        "players",
        "leagues_teams",
        "teams_players",
        "team_seasons",
        "player_seasons",
        "games",
        "team_games",
        "player_games",
    ]

    for bare_name in promote_tables:
        intermediate_table = f"intermediate.{bare_name}"
        core_table = f"core.{bare_name}"

        # Build set of valid column names for this table in both schemas
        cols = []
        for col_name, col_def in DB_COLUMNS.items():
            tables = col_def.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            if "all" in tables:
                cols.append(col_name)
                continue
            for entry in tables:
                if "." in entry:
                    if entry == intermediate_table or entry == core_table:
                        cols.append(col_name)
                        break
                else:
                    if entry == bare_name:
                        cols.append(col_name)
                        break

        if not cols:
            continue

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Check if intermediate has rows
                cur.execute(f"SELECT COUNT(*) FROM {intermediate_table}")
                result = cur.fetchone()
                if result is None or result[0] == 0:
                    continue

                col_list = ", ".join(quote_col(c) for c in cols)
                update_cols = [c for c in cols if c not in ("sts_id", "game_id")]

                # Get PK from core table definition
                from src.definitions.schema import get_table

                core_meta = get_table(core_table)
                conflict_cols = list(core_meta.get("primary_key") or [])

                if conflict_cols and update_cols:
                    conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)
                    update_sql = ", ".join(
                        f"{quote_col(c)} = COALESCE({bare_name}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
                        for c in update_cols
                    )
                    cur.execute(
                        f"""
                        INSERT INTO {core_table} AS {bare_name} ({col_list})
                        SELECT {col_list}
                          FROM {intermediate_table}
                        ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
                        """
                    )
                elif conflict_cols:
                    conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)
                    cur.execute(
                        f"""
                        INSERT INTO {core_table} ({col_list})
                        SELECT {col_list}
                          FROM {intermediate_table}
                        ON CONFLICT ({conflict_sql}) DO NOTHING
                        """
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {core_table} ({col_list})
                        SELECT {col_list}
                          FROM {intermediate_table}
                        """
                    )

                upserted = cur.rowcount
                total_upserted += upserted

                if upserted:
                    logger.info(
                        "Promoted %d rows from %s to %s",
                        upserted,
                        intermediate_table,
                        core_table,
                    )

            conn.commit()

    return total_upserted


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
            "staging.players",
            "core.players",
            "core.identities_players",
            "player_id",
        ),
        (
            "team",
            "staging.teams",
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

    # Table-driven roster promotion config:
    # (staging_table, core_table, insert_cols, select_cols, conflict_cols, review_checks)
    # review_checks: list of (entity_type, staging_table, ext_id_field)
    roster_mappings = [
        (
            "staging.teams_players",
            "core.teams_players",
            ["league_code", "team_id", "player_id"],
            [
                "s.league_code",
                "team_ie.team_id",
                "player_ie.player_id",
            ],
            ["league_code", "team_id", "player_id"],
            [
                ("team", "teams", "ext_team_id"),
                ("player", "players", "ext_player_id"),
            ],
        ),
        (
            "staging.leagues_teams",
            "core.leagues_teams",
            ["league_code", "team_id"],
            ["s.league_code", "team_ie.team_id"],
            ["league_code", "team_id"],
            [("team", "teams", "ext_team_id")],
        ),
        (
            "staging.countries_players",
            "core.countries_players",
            ["country_code", "player_id"],
            ["s.country_code", "player_ie.player_id"],
            ["country_code", "player_id"],
            [("player", "players", "ext_player_id")],
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
                review_checks,
            ) in roster_mappings:
                needs_player = any(entity == "player" for entity, _, _ in review_checks)
                needs_team = any(entity == "team" for entity, _, _ in review_checks)

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

                # Build review check clauses
                review_clauses = []
                for entity_type, review_table, ext_id_field in review_checks:
                    review_clauses.append(
                        f"""
                        EXISTS (
                            SELECT 1 FROM staging.{review_table} rt
                             WHERE rt.identity = s.identity
                               AND rt.ext_id = s.{ext_id_field}
                               AND rt.reviewed = TRUE
                        )
                        """
                    )
                review_sql = " AND ".join(review_clauses)

                insert_sql = ", ".join(quote_col(c) for c in insert_cols)
                select_sql = ", ".join(select_cols)
                conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)

                cur.execute(
                    f"""
                    INSERT INTO {core_table} ({insert_sql})
                    SELECT {select_sql}
                      FROM {from_clause}
                     WHERE s.league_code IS NOT NULL
                       AND {review_sql}
                    ON CONFLICT ({conflict_sql}) DO NOTHING
                    """
                )
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info("Promoted %d rows to %s", upserted, core_table)
        conn.commit()

    return total_upserted


def _promote_seasons(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote reviewed staging stats rows to core stats tables.

    Resolves ``ext_player_id`` / ``ext_team_id`` to internal sts_ids
    via ``identities_players`` / ``identities_teams``.  Shared stat
    columns are promoted by direct name match from db_columns.
    """
    logger.info(phase_marker("promote_seasons"))
    total_upserted = 0

    for entity in VALID_ENTITY_TYPES:
        staging_table = f"staging.{entity}_seasons"
        core_table = f"core.{entity}_seasons"

        # Stats columns shared between staging and core
        from src.definitions.db_columns import DB_COLUMNS

        shared_cols = []
        for col_name, col_meta in DB_COLUMNS.items():
            tables = col_meta.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            if f"{entity}_seasons" in tables:
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
                           SELECT 1 FROM staging.{entity}s ps
                            WHERE ps.identity = s.identity
                              AND ps.ext_id = s.ext_{entity}_id
                              AND ps.reviewed = TRUE
                       )
                    ON CONFLICT ({conflict_sql}) DO UPDATE SET
                        {", ".join(f"{quote_col(c)} = COALESCE(target.{quote_col(c)}, EXCLUDED.{quote_col(c)})" for c in shared_cols)}
                    """
                )
                upserted = cur.rowcount
                total_upserted += upserted
                if upserted:
                    logger.info("Promoted %d rows to %s", upserted, core_table)
        conn.commit()

    return total_upserted


def _promote_games(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote game staging rows to core game tables.

    Pre-assigns game_ids from the game sequence, resolves team FKs via
    identities_teams, and upserts into core.games, core.player_games,
    and core.team_games.
    """
    logger.info(phase_marker("promote_games"))
    total_upserted = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            # 1) Promote to core.games — resolve team FKs via identities,
            #    natural key prevents duplicates.
            cur.execute(
                """
                INSERT INTO core.games (game_id, league_code, date,
                       home_team_id, away_team_id, ot)
                SELECT nextval('core.game_id_seq'), gs.league_code, gs.date,
                       home_ie.team_id, away_ie.team_id, gs.ot
                  FROM staging.games gs
                  JOIN core.identities_teams home_ie
                    ON gs.identity = home_ie.identity
                   AND gs.ext_home_team_id = home_ie.ext_id
                  JOIN core.identities_teams away_ie
                    ON gs.identity = away_ie.identity
                   AND gs.ext_away_team_id = away_ie.ext_id
                ON CONFLICT (date, home_team_id, away_team_id)
                DO NOTHING
                """
            )
            upserted = cur.rowcount
            total_upserted += upserted
            if upserted:
                logger.info("Promoted %d rows to core.games", upserted)

            # 2) Promote player_games — join through games_staging → core.games
            cur.execute(
                """
                INSERT INTO core.player_games (league_code, game_id,
                       player_id, team_id, date)
                SELECT pgs.league_code, g.game_id,
                       player_ie.player_id, team_ie.team_id,
                       pgs.date
                  FROM staging.player_games pgs
                  JOIN staging.games gs
                    ON pgs.identity = gs.identity
                   AND pgs.ext_game_id = gs.ext_game_id
                  JOIN core.games g
                    ON g.date = gs.date
                   AND g.home_team_id = home_ie.team_id
                   AND g.away_team_id = away_ie.team_id
                  JOIN core.identities_players player_ie
                    ON pgs.identity = player_ie.identity
                   AND pgs.ext_player_id = player_ie.ext_id
                  JOIN core.identities_teams team_ie
                    ON pgs.identity = team_ie.identity
                   AND pgs.ext_team_id = team_ie.ext_id
                ON CONFLICT (league_code, game_id, player_id, team_id)
                DO NOTHING
                """
            )
            upserted = cur.rowcount
            total_upserted += upserted
            if upserted:
                logger.info("Promoted %d rows to core.player_games", upserted)

            # 3) Promote team_games
            cur.execute(
                """
                INSERT INTO core.team_games (league_code, game_id,
                       team_id, date)
                SELECT tgs.league_code, g.game_id,
                       team_ie.team_id, tgs.date
                  FROM staging.team_games tgs
                  JOIN staging.games gs
                    ON tgs.identity = gs.identity
                   AND tgs.ext_game_id = gs.ext_game_id
                  JOIN core.games g
                    ON g.date = gs.date
                   AND g.home_team_id = home_ie.team_id
                   AND g.away_team_id = away_ie.team_id
                  JOIN core.identities_teams team_ie
                    ON tgs.identity = team_ie.identity
                   AND tgs.ext_team_id = team_ie.ext_id
                ON CONFLICT (league_code, game_id, team_id)
                DO NOTHING
                """
            )
            upserted = cur.rowcount
            total_upserted += upserted
            if upserted:
                logger.info("Promoted %d rows to core.team_games", upserted)

        conn.commit()

    return total_upserted


def _cascade_delete_reviewed(
    league_code: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Delete reviewed=True profile staging rows.

    All dependent staging tables (rosters, stats) have ON DELETE CASCADE
    foreign keys to staging.players and staging.teams, so the database
    handles cascading automatically.
    """
    logger.info(phase_marker("cascade_delete_reviewed"))
    total_deleted = 0

    # Table-driven deletion config: (schema, table_name)
    staging_tables = [
        ("staging", "players"),
        ("staging", "teams"),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for schema, table_name in staging_tables:
                # Use psycopg2.sql for safe table identifier handling
                query = sql.SQL("DELETE FROM {table} WHERE reviewed = TRUE").format(
                    table=sql.Identifier(schema, table_name)
                )
                cur.execute(query)
                deleted = cur.rowcount
                if deleted:
                    logger.info(
                        "Deleted %d reviewed rows from %s.%s (+ cascaded)",
                        deleted,
                        schema,
                        table_name,
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
        _run_phases(league_code, handlers, cluster, season_range=None)
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
        fn = _resolve_phase(phase)
        total_rows += fn(ctx)

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)

    return total_rows


# ═══════════════════════════════════════════════════════════════════════════
# Phase dispatch  --  explicit mapping from phase name to handler function
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

    if active:
        from datetime import datetime, timedelta

        lookback_date = (
            datetime.now().date() - timedelta(days=GAME_LOOKBACK_DAYS)
        ).isoformat()

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Reset coverage for active types in current season
                cur.execute(
                    """UPDATE coverage SET covered = false
                        WHERE league_code = %s AND season = %s
                          AND season_type = ANY(%s)""",
                    (league_code, season, active),
                )
                season_reset = cur.rowcount

                # Reset game-level coverage for games within the lookback window
                cur.execute(
                    """UPDATE coverage SET covered = false
                        WHERE league_code = %s
                          AND coverage_level = 'game'
                          AND game_id IN (
                              SELECT game_id FROM games
                               WHERE league_code = %s
                                 AND season = %s
                                 AND season_type = ANY(%s)
                                 AND date >= %s
                          )""",
                    (league_code, league_code, season, active, lookback_date),
                )
                game_reset = cur.rowcount
            conn.commit()

        if season_reset or game_reset:
            logger.info(
                "Coverage reset: %d season rows, %d game rows",
                season_reset,
                game_reset,
            )

    return 0


def _phase_seed_season_coverage(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season_range = ctx["season_range"]
    total = 0
    logger.info(phase_marker("seed_season_coverage"))
    for identity_code in DATASETS:
        total += seed_coverage(
            league_code, season_range, identity_code, coverage_level="season"
        )
    logger.info("Seeded %d season coverage rows", total)
    return total


def _phase_seed_game_coverage(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season_range = ctx["season_range"]
    total = 0
    logger.info(phase_marker("seed_game_coverage"))
    for identity_code in DATASETS:
        total += seed_coverage(
            league_code, season_range, identity_code, coverage_level="game"
        )
    logger.info("Seeded %d game coverage rows", total)
    return total


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
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        logger.info(
            "  identity=%s source=%s datasets=%s",
            identity_code,
            identity_source,
            phase_datasets,
        )
        reg_st = get_regular_season_types(league_code)[0]
        reg_code = get_source_season_type_code(identity_source, league_code, reg_st)
        total_rows += _discover_entities(
            league_code,
            season,
            handler,
            identity_code,
            identity_source,
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
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        logger.info(
            "  identity=%s source=%s datasets=%s",
            identity_code,
            identity_source,
            phase_datasets,
        )
        reg_st = get_regular_season_types(league_code)[0]
        reg_code = get_source_season_type_code(identity_source, league_code, reg_st)
        total_rows += _discover_entities(
            league_code,
            season,
            handler,
            identity_code,
            identity_source,
            reg_st,
            reg_code,
            failed,
            team_ids=team_ids,
        )
    return total_rows


def _phase_maintain_games(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    season_range = ctx["season_range"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_games"))
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase("maintain_games").get(identity_code, [])
        if not phase_datasets:
            continue
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        total_rows += _maintain_games(
            league_code, season, season_range, identity_code, identity_source, failed
        )
    return total_rows


def _write_pbp_stats(
    cur,
    table_name: str,
    stats: List[Dict[str, Any]],
    identity_code: str,
    ext_game_id: str,
    pk_columns: List[str],
) -> int:
    """Write accumulated PBP stats to a staging table with COALESCE fill.

    Args:
        cur: Database cursor.
        table_name: Qualified staging table name (e.g. ``"staging.player_games"``).
        stats: List of stat dicts from the accumulator (each dict has canonical field names
               plus the entity ID columns like ``ext_team_id``, ``ext_player_id``).
        identity_code: Identity to stamp on each row.
        ext_game_id: External game ID to stamp on each row.
        pk_columns: PK column names for ON CONFLICT clause (e.g. ``["identity", "ext_player_id", "ext_team_id", "ext_game_id"]``).

    Returns the number of rows written.
    """
    if not stats:
        return 0

    for record in stats:
        record["identity"] = identity_code
        record["ext_game_id"] = ext_game_id

    cols = sorted(stats[0].keys())
    col_list = ", ".join(quote_col(c) for c in cols)
    placeholders = ", ".join("%s" for _ in cols)

    data = [tuple(record.get(col) for col in cols) for record in stats]

    update_cols = [c for c in cols if c not in pk_columns]
    update_set = ", ".join(
        f"{quote_col(c)} = COALESCE({table_name}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
        for c in update_cols
    )

    pk_list = ", ".join(quote_col(c) for c in pk_columns)

    execute_values(
        cur,
        f"""
        INSERT INTO {table_name} ({col_list})
        VALUES %s
        ON CONFLICT ({pk_list})
        DO UPDATE SET {update_set}
        """,
        data,
        template=f"({placeholders})",
    )

    return len(stats)


def _phase_maintain_pbp(ctx: dict) -> int:
    """Fetch PBP events, normalize, accumulate into stats, write to staging.

    This phase:
    1. Fetches raw PBP data from sources
    2. Normalizes events to standard event types
    3. Accumulates events into stats per result_set
    4. Writes accumulated stats to appropriate staging tables
    """
    from nba_api.stats.endpoints.playbyplayv3 import PlayByPlayV3

    from src.lib.pbp_accumulator import accumulate_pbp_events
    from src.sources.nba_api.pbp_normalizer import normalize_nba_pbp_events

    league_code = ctx["league_code"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_pbp"))

    # Iterate through identities with maintain_pbp datasets
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase("maintain_pbp").get(identity_code, [])
        if not phase_datasets:
            continue

        dataset_name = phase_datasets[0]
        identity_source = DATASETS[identity_code][dataset_name]["source"]

        # Verify league is supported by this source
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue

        logger.info(
            phase_marker(
                "maintain_pbp",
                f"identity={identity_code} source={identity_source}",
            )
        )

        # Find games needing PBP data
        with db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ext_game_id, ext_home_team_id, ext_away_team_id
                    FROM staging.games
                    WHERE identity = %s
                      AND league_code = %s
                    ORDER BY ext_game_id
                    """,
                    (identity_code, league_code),
                )
                games_needing_pbp = cur.fetchall()

        if not games_needing_pbp:
            logger.info(
                "No games require PBP data for %s/%s", identity_code, league_code
            )
            continue

        logger.info(
            "Processing PBP for %d games (%s/%s)",
            len(games_needing_pbp),
            identity_code,
            league_code,
        )

        # Process each game
        for game_row in games_needing_pbp:
            ext_game_id = game_row["ext_game_id"]
            ext_home_team_id = game_row["ext_home_team_id"]
            ext_away_team_id = game_row["ext_away_team_id"]

            try:
                # Fetch raw PBP from NBA API
                logger.debug("Fetching PBP for game %s", ext_game_id)
                pbp_response = PlayByPlayV3(game_id=ext_game_id)
                raw_actions = pbp_response.get_dict().get("game", {}).get("actions", [])

                if not raw_actions:
                    logger.warning("No PBP actions returned for game %s", ext_game_id)
                    continue

                # Normalize to standard events
                normalized_events = normalize_nba_pbp_events(
                    raw_actions=raw_actions,
                    ext_game_id=ext_game_id,
                    home_team_id=ext_home_team_id,
                    away_team_id=ext_away_team_id,
                    identity=identity_code,
                )

                if not normalized_events:
                    logger.warning(
                        "No normalized events produced for game %s", ext_game_id
                    )
                    continue

                # Events are in-memory only; pass directly to accumulator
                # Accumulate events into stats
                result_sets = accumulate_pbp_events(
                    events=normalized_events,
                    ext_game_id=ext_game_id,
                    ext_home_team_id=ext_home_team_id,
                    ext_away_team_id=ext_away_team_id,
                )

                # Separate result sets into player-level and team-level stats
                player_stats = (
                    result_sets.get("player", [])
                    + result_sets.get("opp_player", [])
                    + result_sets.get("on_player", [])
                )
                team_stats = result_sets.get("team", []) + result_sets.get(
                    "opp_team", []
                )

                # Write accumulated stats to staging tables via shared helper
                with db_connection() as conn:
                    with conn.cursor() as cur:
                        player_rows = _write_pbp_stats(
                            cur,
                            table_name="staging.player_games",
                            stats=player_stats,
                            identity_code=identity_code,
                            ext_game_id=ext_game_id,
                            pk_columns=[
                                "identity",
                                "ext_player_id",
                                "ext_team_id",
                                "ext_game_id",
                            ],
                        )
                        team_rows = _write_pbp_stats(
                            cur,
                            table_name="staging.team_games",
                            stats=team_stats,
                            identity_code=identity_code,
                            ext_game_id=ext_game_id,
                            pk_columns=[
                                "identity",
                                "ext_team_id",
                                "ext_game_id",
                            ],
                        )
                    conn.commit()

                total_rows += player_rows + team_rows

                logger.info(
                    "Processed PBP for game %s (%d events, %d player rows, %d team rows)",
                    ext_game_id,
                    len(normalized_events),
                    player_rows,
                    team_rows,
                )

            except Exception as e:
                logger.error(
                    "Failed to process PBP for game %s: %s",
                    ext_game_id,
                    str(e),
                    exc_info=True,
                )
                failed.append(
                    {
                        "phase": "maintain_pbp",
                        "identity": identity_code,
                        "ext_game_id": ext_game_id,
                        "error": str(e),
                    }
                )
                continue

    logger.info("PBP maintenance complete - %d total rows written", total_rows)
    return total_rows


def _phase_maintain_seasons(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
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
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        total_rows += _maintain_seasons(
            league_code, season, season_range, identity_code, identity_source, failed
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
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        team_ids = _load_team_ids(league_code)
        reg_st = get_regular_season_types(league_code)[0]
        reg_code = get_source_season_type_code(identity_source, league_code, reg_st)
        total_rows += _maintain_profiles(
            league_code,
            season,
            identity_code,
            identity_source,
            reg_st,
            reg_code,
            failed,
            team_ids=team_ids,
        )
    return total_rows


def _phase_match_entities(ctx: dict) -> int:
    return _match_entities(ctx["league_code"], ctx["failed"])


def _phase_match_games(ctx: dict) -> int:
    return _match_games(ctx["league_code"], ctx["failed"])


def _phase_merge_to_intermediate(ctx: dict) -> int:
    total = 0
    for identity_code in DATASETS:
        total += _merge_to_intermediate(ctx["league_code"], identity_code)
    return total


def _phase_merge_staging(ctx: dict) -> int:
    return _merge_staging(ctx["league_code"], ctx["failed"])


def _phase_promote_to_core(ctx: dict) -> int:
    return _promote_to_core(ctx["league_code"])


def _phase_promote_profiles(ctx: dict) -> int:
    return _promote_profiles(ctx["league_code"], ctx["failed"])


def _phase_promote_rosters(ctx: dict) -> int:
    return _promote_rosters(ctx["league_code"], ctx["failed"])


def _phase_promote_seasons(ctx: dict) -> int:
    return _promote_seasons(ctx["league_code"], ctx["failed"])


def _phase_promote_games(ctx: dict) -> int:
    return _promote_games(ctx["league_code"], ctx["failed"])


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


def _phase_prune_coverage(ctx: dict) -> int:
    logger.info(phase_marker("prune_coverage"))
    return prune_coverage(ctx["league_code"])


PHASE_HANDLERS: Dict[str, Callable] = {
    "build_schema": _phase_build_schema,
    "detect_season_activity": _phase_detect_season_activity,
    "seed_season_coverage": _phase_seed_season_coverage,
    "seed_game_coverage": _phase_seed_game_coverage,
    "maintain_leagues_teams": _phase_maintain_leagues_teams,
    "maintain_teams_players": _phase_maintain_teams_players,
    "maintain_games": _phase_maintain_games,
    "match_games": _phase_match_games,
    "maintain_pbp": _phase_maintain_pbp,
    "maintain_seasons": _phase_maintain_seasons,
    "maintain_profiles": _phase_maintain_profiles,
    "match_entities": _phase_match_entities,
    "merge_to_intermediate": _phase_merge_to_intermediate,
    "merge_staging": _phase_merge_staging,
    "promote_to_core": _phase_promote_to_core,
    "promote_profiles": _phase_promote_profiles,
    "promote_rosters": _phase_promote_rosters,
    "promote_seasons": _phase_promote_seasons,
    "promote_games": _phase_promote_games,
    "cascade_delete_reviewed": _phase_cascade_delete_reviewed,
    "normalize_nulls_zeroes": _phase_normalize_nulls_zeroes,
    "prune_stats_retention": _phase_prune_stats_retention,
    "prune_entities": _phase_prune_entities,
    "prune_coverage": _phase_prune_coverage,
}


def _resolve_phase(name: str) -> Callable:
    """Return the handler function for *name* from ``PHASE_HANDLERS``.

    Raises RuntimeError at import time if a handler listed in
    PIPELINE has no corresponding entry in PHASE_HANDLERS.
    """
    func = PHASE_HANDLERS.get(name)
    if func is None:
        raise RuntimeError(
            f"Phase {name!r} listed in PIPELINE but no "
            f"handler registered in PHASE_HANDLERS"
        )
    return func
