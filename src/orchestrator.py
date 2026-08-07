"""
Shoot the Sheet - ETL Orchestrator

Sequences the ordered ETL phases for a single league run.  Knows nothing
about HTTP, argparse, or the destination of stdout -- just which phase
runs when, and which library function each phase calls.

Clusters:
    - ``execution_start``  — runs once before all leagues (schema bootstrap only).
    - ``league_setup``     — runs once per league (season detection + coverage seeding).
    - ``league_ingest``    — runs once per league (all identity-scoped + league-wide ingest phases).
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
from collections.abc import Callable
from typing import Any

from psycopg2 import sql

from src.definitions.datasets import DATASETS, Dataset
from src.definitions.execution import GAME_LOOKBACK_DAYS
from src.definitions.leagues import LEAGUES
from src.definitions.pipeline import PIPELINE
from src.definitions.schema import SCHEMAS
from src.definitions.sources import SOURCES
from src.lib.call_grouper import build_call_groups
from src.lib.cleanup import (
    prune_entities,
    prune_stats_retention,
)
from src.lib.console_logger import phase_marker
from src.lib.coverage_tracker import (
    is_coverage_current,
    prune_coverage,
    seed_coverage,
)
from src.lib.error_recorder import log_error
from src.lib.executor import ExecutionContext, execute_group
from src.lib.extract import apply_row_filters
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

_active_types_cache: dict[str, list[str]] = {}


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
    targets: list[str],
    seasons: list[str],
    season_type: str,
    season_type_name: str,
    team_ids: dict[str, int],
    failed: list[dict[str, Any]],
    *,
    phase: str,
    league_code: str,
    identity_code: str,
    dataset: str,
    source_config: dict,
    api_config: dict,
    make_fetcher: Callable,
    on_target_finished: Callable[[str, str, list[dict[str, Any]], int, bool, Any], None] | None = None,
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
            if ds_cfg.get("target_tables"):
                groups = [
                    {
                        "dataset": dataset,
                        "params": {},
                        "tier": ds_cfg.get("iterates_by", "none"),
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
            except Exception as exc:  # noqa: BLE001
                logger.error("Group %s fetch failed: %s", dataset_name, str(exc))
                failed.append({"dataset": dataset_name, "error": str(exc)})
                log_error(
                    phase=phase,
                    message=(
                        f"Group fetch failed: identity={identity_code} "
                        f"league={league_code} target={table_name} "
                        f"dataset={dataset_name} -- {exc}"
                    ),
                    exc_info=exc,
                )
                continue

            if result is None:
                continue

            # Apply dataset-level row_filters (post-fetch, pre-extraction)
            ds_cfg_for_filter = DATASETS.get(identity_code, {}).get(dataset_name, {})
            row_filters = ds_cfg_for_filter.get("row_filters")
            if row_filters:
                result = apply_row_filters(
                    result, row_filters, season_end_year=season_end_year
                )

            group_succeeded = False
            for target in targets:
                ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
                entity_type, entity_id_field, entity_param = _resolve_entity_for_target(
                    source_config, ds_cfg, target
                )
                ctx = ExecutionContext(
                    target=target,
                    table_name=table_name,
                    season=season,
                    season_type=season_type,
                    season_type_name=season_type_name,
                    entity_id_field=entity_id_field,
                    entity_param=entity_param,
                    entity_type=entity_type,
                    db_schema=league_code,
                    identity_code=identity_code,
                    phase=phase,
                    api_fetcher=shared_fetcher,
                    team_ids=team_ids,
                    max_consecutive_failures=api_config.get(
                        "max_consecutive_failures", 5
                    ),
                    id_aliases=source_config.get("id_aliases", {}),
                )

                try:
                    rows = execute_group(group, ctx, failed, result=result)
                    total_rows += rows
                    if rows:
                        group_succeeded = True
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Group %s target %s failed: %s",
                        dataset_name,
                        target,
                        str(exc),
                    )
                    failed.append(
                        {
                            "dataset": dataset_name,
                            "target": target,
                            "error": str(exc),
                        }
                    )
                    log_error(
                        phase=phase,
                        message=(
                            f"Group target failed: identity={identity_code} "
                            f"league={league_code} target={target} "
                            f"dataset={dataset_name} -- {exc}"
                        ),
                        exc_info=exc,
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


def _get_datasets_by_phase(phase_name: str) -> dict[str, list[str]]:
    """Return ``{identity_code: [dataset_name, ...]}`` for a pipeline stage."""
    result: dict[str, list[str]] = {}
    for identity_code in DATASETS:
        datasets = DATASETS[identity_code]
        for ds_name, ds_def in datasets.items():
            if ds_def.get("phase") == phase_name:
                result.setdefault(identity_code, []).append(ds_name)
    return result


# Tables written by _discover_entities' "profile" pass (one row per entity)
# versus its "roster" pass (one row per relationship). Used to bucket a
# dataset's declared target_tables without hardcoding per-phase table names.
_PROFILE_TABLES = frozenset({"players", "teams"})
_ROSTER_TABLES = frozenset({"teams_players", "leagues_teams", "countries_players"})


def _resolve_entity_for_target(
    source_config: dict, dataset_config: dict | Dataset, target: str
) -> tuple:
    """Resolve entity_type, entity_id_field, and entity_param for a target table.

    Args:
        source_config: The source module's API_FIELD_NAMES dict.
        dataset_config: The dataset's config dict (from DATASETS).
        target: Bare staging table name (e.g. 'player_games').

    Returns:
        (entity_type, entity_id_field, entity_param) tuple.
    """
    target_tables = dataset_config.get("target_tables") or {}
    entity_type = target_tables.get(f"staging.{target}")
    if not entity_type:
        raise ValueError(
            f"No entity type for target '{target}' in dataset target_tables: {target_tables}"
        )
    entity_fields = source_config.get("entity_fields", {})
    entity_params = source_config.get("entity_params", {})
    entity_id_field = entity_fields.get(entity_type)
    entity_param = entity_params.get(entity_type)
    if not entity_id_field:
        raise ValueError(
            f"No entity_fields entry for entity_type '{entity_type}' "
            f"in source config. Available: {list(entity_fields.keys())}"
        )
    if not entity_param:
        raise ValueError(
            f"No entity_params entry for entity_type '{entity_type}' "
            f"in source config. Available: {list(entity_params.keys())}"
        )
    return entity_type, entity_id_field, entity_param


def _generic_targets_for_dataset(
    identity_code: str, dataset_name: str, identity_source: str
) -> list[str]:
    """Return the bare staging table names a dataset writes to via the
    generic per-row column-mapping / entity-extraction path.

    Always derived from ``DATASETS[identity_code][dataset_name]['target_tables']``
    -- the single source of truth for what a dataset writes to. Never
    hardcode per-phase target lists in the orchestrator; add or fix the
    dataset's ``target_tables`` entry instead.

    Tables declared in ``target_tables`` are filtered to those the source's
    ``entity_fields`` can resolve an entity key for. A table whose entity
    type has no ``entity_fields`` entry cannot be populated by the generic
    per-row extraction path yet -- it is skipped here with a warning rather
    than raising, so the rest of the dataset's tables keep working while
    the gap stays visible in logs.
    """
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
    target_tables = ds_cfg.get("target_tables") or {}
    config_mod, _ = _load_source(identity_source)
    entity_fields = getattr(config_mod, "API_FIELD_NAMES", {}).get("entity_fields", {})

    resolved: list[str] = []
    for qualified, entity_type in target_tables.items():
        table = qualified.split(".", 1)[1] if "." in qualified else qualified
        if entity_type in entity_fields:
            resolved.append(table)
        else:
            logger.warning(
                "%s.%s declares target_table '%s' with entity_type '%s' but %s has no "
                "entity_fields entry for it -- generic per-row write not implemented yet, skipping",
                identity_code,
                dataset_name,
                table,
                entity_type,
                identity_source,
            )
    return resolved


def _load_team_ids(league_code: str) -> dict[str, int]:
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


def _identity_supports_league(identity_code: str, league_code: str) -> bool:
    """Return True if *identity_code* has any dataset from a source supporting *league_code*."""
    for ds_def in DATASETS.get(identity_code, {}).values():
        source = ds_def.get("source", "")
        league_config = SOURCES.get(source, {}).get("leagues", {})
        if league_code in league_config:
            return True
    return False


def _iter_league_identities(league_code: str, phase_name: str):
    """Yield ``(identity_code, identity_source, phase_datasets)`` for
    identities that have datasets for *phase_name* and support *league_code*."""
    for identity_code in DATASETS:
        phase_datasets = _get_datasets_by_phase(phase_name).get(identity_code, [])
        if not phase_datasets:
            continue
        identity_source = DATASETS[identity_code][phase_datasets[0]]["source"]
        if league_code not in SOURCES[identity_source].get("leagues", {}):
            continue
        yield identity_code, identity_source, phase_datasets


# ============================================================================
# detect_season_activity
# ============================================================================


def _detect_season_activity(league_code: str, season: str) -> list[str]:
    """Query detect_season_activity datasets and return active canonical season types."""
    active: list[str] = []
    for identity_code in DATASETS:
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
    failed: list[dict[str, Any]],
    team_ids: dict[str, int] | None = None,
) -> int:
    """Execute a maintainer stage: call each dataset, extract columns, prune stale records."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_datasets_by_phase(phase_name).get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(identity_source)

    if not hasattr(client_mod, "make_fetcher"):
        raise RuntimeError(
            f"Source {identity_source!r} does not expose make_fetcher(). "
            f"Phase {phase_name!r} requires a make_fetcher callable on "
            f"the source's client module."
        )

    from datetime import UTC, datetime

    for dataset_name in dataset_names:
        logger.info(
            phase_marker(
                phase_name,
                f"dataset={identity_code}.{dataset_name} source={identity_source}",
            )
        )

        ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
        prune_tables = ds_cfg.get("prune_tables")
        prune_start = datetime.now(UTC) if prune_tables else None

        resolved_targets = _generic_targets_for_dataset(
            identity_code, dataset_name, identity_source
        )
        targets = [t for t in resolved_targets if t in _PROFILE_TABLES]
        roster_targets = [t for t in resolved_targets if t in _ROSTER_TABLES]

        # Profile columns → players / teams staging
        for target in targets:
            total_rows += _run_groups(
                table_name=target,
                targets=[target],
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids if ds_cfg.get("iterates_by") == "team" else {},
                failed=failed,
                phase=phase_name,
                league_code=league_code,
                identity_code=identity_code,
                dataset=dataset_name,
                source_config=getattr(config_mod, "API_FIELD_NAMES", {}),
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
                phase=phase_name,
                league_code=league_code,
                identity_code=identity_code,
                dataset=dataset_name,
                source_config=getattr(config_mod, "API_FIELD_NAMES", {}),
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
    season_range: list[str],
    identity_code: str,
    identity_source: str,
    failed: list[dict[str, Any]],
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
    dataset_targets = {
        ds: _generic_targets_for_dataset(identity_code, ds, identity_source)
        for ds in dataset_names
    }
    active_types = _active_types_cache.get(league_code, [])

    # ── Part A: active types x current season (no coverage check) ──────────
    if active_types:
        logger.info(
            phase_marker(
                "maintain_seasons",
                f"active types={active_types} season={season}",
            )
        )
        # Separate datasets by per_season_type
        sep_datasets = []
        non_sep_datasets = []
        for ds_name in dataset_names:
            ds_cfg = DATASETS.get(identity_code, {}).get(ds_name, {})
            if ds_cfg.get("per_season_type", True):
                sep_datasets.append(ds_name)
            else:
                non_sep_datasets.append(ds_name)

        # per_season_type=True: call once per active season type
        for st_key in active_types:
            if not is_season_type_valid_for(league_code, st_key, season):
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, st_key
            )
            for dataset_name in sep_datasets:
                for target in dataset_targets[dataset_name]:
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
                        phase="maintain_seasons",
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

        # per_season_type=False: call once (returns all types)
        if non_sep_datasets:
            first_valid_type = next(
                (
                    st
                    for st in active_types
                    if is_season_type_valid_for(league_code, st, season)
                ),
                None,
            )
            if first_valid_type is not None:
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, first_valid_type
                )
                for dataset_name in non_sep_datasets:
                    for target in dataset_targets[dataset_name]:
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
                            phase="maintain_seasons",
                            league_code=league_code,
                            target=target,
                            season_label=season,
                            st_key=first_valid_type,
                            season_type_name=season_type_name,
                            identity_code=identity_code,
                            identity_source=identity_source,
                            dataset=dataset_name,
                            filtered_groups=groups,
                            team_ids=team_ids,
                            failed=failed,
                            use_coverage=True,
                        )

    # ── Part B: coverage backfill (all seasons x all types) ────────────────────────
    # Separate datasets by per_season_type
    sep_backfill = []
    non_sep_backfill = []
    for ds_name in dataset_names:
        ds_cfg = DATASETS.get(identity_code, {}).get(ds_name, {})
        if ds_cfg.get("per_season_type", True):
            sep_backfill.append(ds_name)
        else:
            non_sep_backfill.append(ds_name)

    # per_season_type=True: iterate all seasons x all types
    for dataset_name in sep_backfill:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, st_key
                )
                for target in dataset_targets[dataset_name]:
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
                        phase="maintain_seasons",
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

    # per_season_type=False: call once per season (returns all types)
    # Coverage is checked against first_valid_type only — the API returns
    # all types in one call, so one coverage check suffices.
    for dataset_name in non_sep_backfill:
        for season_label in season_range:
            first_valid = next(
                (
                    st
                    for st in all_season_types
                    if is_season_type_valid_for(league_code, st, season_label)
                ),
                None,
            )
            if first_valid is None:
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, first_valid
            )
            for target in dataset_targets[dataset_name]:
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
                            first_valid,
                            identity_code,
                            g,
                        )
                    ]
                if not filtered_groups:
                    continue
                total_rows += _execute_stats_groups(
                    phase="maintain_seasons",
                    league_code=league_code,
                    target=target,
                    season_label=season_label,
                    st_key=first_valid,
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
    season_range: list[str],
    identity_code: str,
    identity_source: str,
    failed: list[dict[str, Any]],
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
    dataset_targets = {
        ds: _generic_targets_for_dataset(identity_code, ds, identity_source)
        for ds in dataset_names
    }
    active_types = _active_types_cache.get(league_code, [])

    # ── Part A: active types x current season (no coverage check) ──────────
    if active_types:
        logger.info(
            phase_marker(
                "maintain_games",
                f"active types={active_types} season={season}",
            )
        )
        # Separate datasets by per_season_type
        sep_datasets = []
        non_sep_datasets = []
        for ds_name in dataset_names:
            ds_cfg = DATASETS.get(identity_code, {}).get(ds_name, {})
            if ds_cfg.get("per_season_type", True):
                sep_datasets.append(ds_name)
            else:
                non_sep_datasets.append(ds_name)

        # per_season_type=True: call once per active season type
        for st_key in active_types:
            if not is_season_type_valid_for(league_code, st_key, season):
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, st_key
            )
            for dataset_name in sep_datasets:
                for target in dataset_targets[dataset_name]:
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
                        if ds_cfg.get("target_tables"):
                            groups = [
                                {
                                    "dataset": dataset_name,
                                    "params": {},
                                    "tier": ds_cfg.get("iterates_by", "none"),
                                    "columns": {},
                                }
                            ]
                        else:
                            continue
                    total_rows += _execute_stats_groups(
                        phase="maintain_games",
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

        # per_season_type=False: call once (returns all types)
        if non_sep_datasets:
            first_valid_type = next(
                (
                    st
                    for st in active_types
                    if is_season_type_valid_for(league_code, st, season)
                ),
                None,
            )
            if first_valid_type is not None:
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, first_valid_type
                )
                for dataset_name in non_sep_datasets:
                    for target in dataset_targets[dataset_name]:
                        groups = build_call_groups(
                            season,
                            identity_code,
                            dataset=dataset_name,
                            table_name=target,
                            league_code=league_code,
                            in_season=True,
                        )
                        if not groups:
                            ds_cfg = DATASETS.get(identity_code, {}).get(
                                dataset_name, {}
                            )
                            if ds_cfg.get("target_tables"):
                                groups = [
                                    {
                                        "dataset": dataset_name,
                                        "params": {},
                                        "tier": ds_cfg.get("iterates_by", "none"),
                                        "columns": {},
                                    }
                                ]
                            else:
                                continue
                        total_rows += _execute_stats_groups(
                            phase="maintain_games",
                            league_code=league_code,
                            target=target,
                            season_label=season,
                            st_key=first_valid_type,
                            season_type_name=season_type_name,
                            identity_code=identity_code,
                            identity_source=identity_source,
                            dataset=dataset_name,
                            filtered_groups=groups,
                            team_ids={},
                            failed=failed,
                            use_coverage=True,
                        )

    # ── Part B: coverage backfill (all seasons x all types) ────────────
    # Separate datasets by per_season_type
    sep_backfill = []
    non_sep_backfill = []
    for ds_name in dataset_names:
        ds_cfg = DATASETS.get(identity_code, {}).get(ds_name, {})
        if ds_cfg.get("per_season_type", True):
            sep_backfill.append(ds_name)
        else:
            non_sep_backfill.append(ds_name)

    # per_season_type=True: iterate all seasons x all types
    for dataset_name in sep_backfill:
        for season_label in season_range:
            for st_key in all_season_types:
                if not is_season_type_valid_for(league_code, st_key, season_label):
                    continue
                season_type_name = get_source_season_type_code(
                    identity_source, league_code, st_key
                )
                for target in dataset_targets[dataset_name]:
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
                        phase="maintain_games",
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

    # per_season_type=False: call once per season (returns all types)
    # Coverage is checked against first_valid_type only — the API returns
    # all types in one call, so one coverage check suffices.
    for dataset_name in non_sep_backfill:
        for season_label in season_range:
            first_valid = next(
                (
                    st
                    for st in all_season_types
                    if is_season_type_valid_for(league_code, st, season_label)
                ),
                None,
            )
            if first_valid is None:
                continue
            season_type_name = get_source_season_type_code(
                identity_source, league_code, first_valid
            )
            for target in dataset_targets[dataset_name]:
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
                            first_valid,
                            identity_code,
                            g,
                        )
                    ]
                if not filtered_groups:
                    continue
                total_rows += _execute_stats_groups(
                    phase="maintain_games",
                    league_code=league_code,
                    target=target,
                    season_label=season_label,
                    st_key=first_valid,
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
# _populate_games_from_gamestats  (derives staging.games from LeagueGameLog)
# ============================================================================


# ============================================================================
# stats execution helper
# ============================================================================


def _execute_stats_groups(
    *,
    phase: str,
    league_code: str,
    target: str,
    season_label: str,
    st_key: str,
    season_type_name: str,
    identity_code: str,
    identity_source: str,
    dataset: str,
    filtered_groups: list[dict[str, Any]],
    team_ids: dict[str, int],
    failed: list[dict[str, Any]],
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

    if not hasattr(client_mod, "make_fetcher"):
        raise RuntimeError(
            f"Source {src_key!r} does not expose make_fetcher(). "
            f"Dataset {dataset!r} has phase={phase!r} which requires "
            f"a make_fetcher callable on the source's client module."
        )

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
        team_ids=team_ids if ds_cfg.get("iterates_by") == "team" else {},
        failed=failed,
        phase=phase,
        league_code=league_code,
        identity_code=identity_code,
        dataset=dataset,
        source_config=getattr(config_mod, "API_FIELD_NAMES", {}),
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
    failed: list[dict[str, Any]],
    team_ids: dict[str, int] | None = None,
) -> int:
    """Update profile fields for entities already in staging."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_datasets_by_phase("maintain_profiles").get(identity_code, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(identity_source)

    if not hasattr(client_mod, "make_fetcher"):
        raise RuntimeError(
            f"Source {identity_source!r} does not expose make_fetcher(). "
            f"Phase 'maintain_profiles' requires a make_fetcher callable on "
            f"the source's client module."
        )

    for dataset_name in dataset_names:
        resolved_targets = _generic_targets_for_dataset(
            identity_code, dataset_name, identity_source
        )
        for target in resolved_targets:
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
                phase="maintain_profiles",
                league_code=league_code,
                identity_code=identity_code,
                source_config=getattr(config_mod, "API_FIELD_NAMES", {}),
                api_config=config_mod.API_CONFIG
                if hasattr(config_mod, "API_CONFIG")
                else {},
                make_fetcher=client_mod.make_fetcher,
                in_season=True,
                dataset=dataset_name,
            )

    return total_rows


# ============================================================================
# ENTITY MATCHING, MERGE, PROMOTE, CLEANUP
# ============================================================================


def _match_entities(
    league_code: str,
    failed: list[dict[str, Any]],
) -> int:
    """Cross-league: match all staging identities against identity registries.

    Sets matched_sts_id and status='ready' on every staging row whose
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
                           status = 'ready'
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
    failed: list[dict[str, Any]],
) -> int:
    """Resolve staged games to core game_ids.

    Populates core.identities_games so that merge_staging can
    resolve ext_game_id -> game_id for all staging games (not just
    ready ones).  Also upserts into core.games using the
    (date, home_team_id, away_team_id) unique constraint as dedup key
    across identities.
    """
    logger.info(phase_marker("match_games"))
    total = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            # 1) Upsert games from staging using (date, home, away) dedup key
            #    No status = 'ready' filter — we need game_ids for all staged games
            #    so merge_staging can copy them to intermediate.
            cur.execute(
                """
                INSERT INTO core.games AS target (
                    date, home_team_id, away_team_id,
                    season, season_type, ot, neutral_site, completed
                )
                SELECT gs.date,
                       home_t."team_id",
                       away_t."team_id",
                       gs.season,
                       gs.season_type,
                       gs.ot,
                       gs.neutral_site,
                       gs.completed
                  FROM staging.games gs
                  JOIN core.identities_teams home_t
                    ON home_t.identity = gs.identity
                   AND home_t.ext_id = gs.ext_home_team_id
                  JOIN core.identities_teams away_t
                    ON away_t.identity = gs.identity
                   AND away_t.ext_id = gs.ext_away_team_id
                 WHERE gs.league_code = %s
                ON CONFLICT (date, home_team_id, away_team_id)
                DO UPDATE SET season = COALESCE(target.season, EXCLUDED.season),
                              season_type = COALESCE(target.season_type, EXCLUDED.season_type),
                              ot = COALESCE(target.ot, EXCLUDED.ot),
                              neutral_site = COALESCE(target.neutral_site, EXCLUDED.neutral_site),
                              completed = EXCLUDED.completed
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
                   AND g.home_team_id = home_t."team_id"
                   AND g.away_team_id = away_t."team_id"
                  JOIN core.identities_teams home_t
                    ON home_t.identity = gs.identity
                   AND home_t.ext_id = gs.ext_home_team_id
                  JOIN core.identities_teams away_t
                    ON away_t.identity = gs.identity
                   AND away_t.ext_id = gs.ext_away_team_id
                 WHERE gs.league_code = %s
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


# _merge_staging (old) removed -- merge_staging now takes its place
# merge_staging handles cross-identity merge via MERGE_TABLE_CONFIG + ON CONFLICT COALESCE


# ── Per-table merge config ────────────────────────────────────────────────
# Each entry defines how to copy one staging table into its intermediate
# counterpart.  Config fields:
#   staging_table / intermediate_table: qualified names.
#   conflict_cols: PK columns of the intermediate table (for ON CONFLICT).
#   staging_metadata: staging-only columns to exclude from the INSERT.
#   column_aliases: staging_col -> intermediate_col for trivial renames.
#   identity_joins: list of (staging_col, alias, identity_table) for JOIN
#                   resolution to core.identities_*.
#   value_resolution: special SELECT expressions for columns that need
#                     COALESCE / nextval / etc. instead of bare staging refs.
MERGE_TABLE_CONFIG = {
    "players": {
        "intermediate_table": "intermediate.players",
        "conflict_cols": ["sts_id"],
        "staging_metadata": ["identity", "ext_id", "status"],
        "column_aliases": {"matched_sts_id": "sts_id"},
        "identity_joins": [],
        "value_resolution": {
            "sts_id": "COALESCE(s.matched_sts_id, nextval('core.sts_id_seq'))",
        },
    },
    "teams": {
        "intermediate_table": "intermediate.teams",
        "conflict_cols": ["sts_id"],
        "staging_metadata": ["identity", "ext_id", "status"],
        "column_aliases": {"matched_sts_id": "sts_id"},
        "identity_joins": [],
        "value_resolution": {
            "sts_id": "COALESCE(s.matched_sts_id, nextval('core.sts_id_seq'))",
        },
    },
    "leagues_teams": {
        "intermediate_table": "intermediate.leagues_teams",
        "conflict_cols": ["league_code", "team_id"],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_team_id", "team_id", "core.identities_teams"),
        ],
        "value_resolution": {},
    },
    "teams_players": {
        "intermediate_table": "intermediate.teams_players",
        "conflict_cols": ["league_code", "team_id", "player_id"],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_team_id", "team_id", "core.identities_teams"),
            ("ext_player_id", "player_id", "core.identities_players"),
        ],
        "value_resolution": {},
    },
    "team_seasons": {
        "intermediate_table": "intermediate.team_seasons",
        "conflict_cols": ["league_code", "team_id", "season", "season_type"],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_team_id", "team_id", "core.identities_teams"),
        ],
        "value_resolution": {},
        "where_clause": "s.games > 0",
    },
    "player_seasons": {
        "intermediate_table": "intermediate.player_seasons",
        "conflict_cols": [
            "league_code",
            "player_id",
            "team_id",
            "season",
            "season_type",
        ],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_player_id", "player_id", "core.identities_players"),
            ("ext_team_id", "team_id", "core.identities_teams"),
        ],
        "value_resolution": {},
        "where_clause": "s.games > 0",
    },
    "games": {
        "intermediate_table": "intermediate.games",
        "conflict_cols": ["game_id"],
        "staging_metadata": ["identity", "ext_id", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_home_team_id", "home_team_id", "core.identities_teams"),
            ("ext_away_team_id", "away_team_id", "core.identities_teams"),
        ],
        "value_resolution": {
            "game_id": "COALESCE(ig.game_id, nextval('core.game_id_seq'))",
        },
        "extra_joins": [
            ("LEFT JOIN core.identities_games ig"
             "  ON s.identity = ig.identity AND s.ext_game_id = ig.ext_id"),
        ],
    },
    "team_games": {
        "intermediate_table": "intermediate.team_games",
        "conflict_cols": ["league_code", "game_id", "team_id"],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_team_id", "team_id", "core.identities_teams"),
        ],
        "value_resolution": {
            "game_id": "ig.game_id",
        },
        "extra_joins": [
            ("JOIN staging.games sg"
             "  ON s.identity = sg.identity AND s.ext_game_id = sg.ext_game_id"),
            ("LEFT JOIN core.identities_games ig"
             "  ON sg.identity = ig.identity AND sg.ext_game_id = ig.ext_id"),
        ],
        "where_clause": "sg.status IS DISTINCT FROM 'error'",
    },
    "player_games": {
        "intermediate_table": "intermediate.player_games",
        "conflict_cols": ["league_code", "game_id", "player_id", "team_id"],
        "staging_metadata": ["identity", "status"],
        "column_aliases": {},
        "identity_joins": [
            ("ext_player_id", "player_id", "core.identities_players"),
            ("ext_team_id", "team_id", "core.identities_teams"),
        ],
        "value_resolution": {
            "game_id": "ig.game_id",
        },
        "extra_joins": [
            ("JOIN staging.games sg"
             "  ON s.identity = sg.identity AND s.ext_game_id = sg.ext_game_id"),
            ("LEFT JOIN core.identities_games ig"
             "  ON sg.identity = ig.identity AND sg.ext_game_id = ig.ext_id"),
        ],
        "where_clause": "sg.status IS DISTINCT FROM 'error'",
    },
}


def _get_cols_for_table(table_name: str, schema_qualifier: str = "") -> list[str]:
    """Return DB_COLUMNS column names that belong to *table_name*.

    If *schema_qualifier* is set (e.g. "staging"), only columns that
    explicitly match that schema or use a bare table name are included.
    """
    from src.definitions.db_columns import DB_COLUMNS

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
                schema_part = entry.split(".", 1)[0]
                table_part = entry.split(".", 1)[1]
                if table_part == table_name and (not schema_qualifier or schema_part == schema_qualifier):
                    cols.append(col_name)
                    break
            else:
                # Bare: match table name regardless of schema
                if entry == table_name:
                    cols.append(col_name)
                    break
    return cols


# ============================================================================
# merge_staging  (staging -> intermediate for ALL 9 tables)
# ============================================================================


def _merge_staging(
    league_code: str,
    identity: str,
) -> int:
    """Merge staging tables into intermediate for a single identity.

    Uses ``MERGE_TABLE_CONFIG`` per-table config to handle:
      - column name aliasing (matched_sts_id -> sts_id)
      - identity JOINs (ext_team_id -> team_id via identities_teams)
      - value resolution (COALESCE with nextval for sts_id / game_id)
      - exclusion of staging metadata columns

    Called at the end of each per_identity run, after all maintain phases
    and match_* phases have completed.
    """
    logger.info(phase_marker("merge_staging", f"identity={identity}"))
    total_upserted = 0

    for bare_name, cfg in MERGE_TABLE_CONFIG.items():
        staging_table = f"staging.{bare_name}"
        intermediate_table = cfg["intermediate_table"]
        conflict_cols = cfg["conflict_cols"]
        staging_metadata = cfg["staging_metadata"]
        column_aliases = cfg["column_aliases"]
        identity_joins = cfg["identity_joins"]
        value_resolution = cfg["value_resolution"]
        extra_joins = cfg.get("extra_joins", [])
        config_where = cfg.get("where_clause", "")
        extra_where = f" AND {config_where}" if config_where else ""

        # Discover valid columns from DB_COLUMNS for this table in staging
        staging_cols = _get_cols_for_table(bare_name, schema_qualifier="staging")
        if not staging_cols:
            continue

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Check if staging has rows for this identity
                cur.execute(
                    f"SELECT COUNT(*) FROM {staging_table} WHERE identity = %s",
                    (identity,),
                )
                result = cur.fetchone()
                if result is None or result[0] == 0:
                    continue

                # Build SELECT expressions:
                select_parts = []
                insert_cols = []

                # Process each column from staging that also has an intermediate target
                all_intermediate_cols = _get_cols_for_table(bare_name)
                for col in staging_cols:
                    # Skip staging metadata
                    if col in staging_metadata:
                        continue

                    # Check if this column has a value resolution expression
                    if col in value_resolution:
                        resolved_expr = value_resolution[col]
                        # Determine the intermediate-side column name
                        alias = column_aliases.get(col, col)
                        select_parts.append(f"{resolved_expr} AS {quote_col(alias)}")
                        if alias not in insert_cols:
                            insert_cols.append(alias)
                        continue

                    # Check if this column has an alias (staging name != intermediate name)
                    if col in column_aliases:
                        alias = column_aliases[col]
                        select_parts.append(f"s.{quote_col(col)} AS {quote_col(alias)}")
                        if alias not in insert_cols:
                            insert_cols.append(alias)
                        continue

                    # Check if this column is in the intermediate table at all
                    if col in all_intermediate_cols:
                        select_parts.append(f"s.{quote_col(col)}")
                        if col not in insert_cols:
                            insert_cols.append(col)

                # Add identity JOIN resolutions
                for staging_col, alias, identity_table in identity_joins:
                    resolved = f"{identity_table.split('.')[1]}.{quote_col(alias)}"
                    expr = f"{resolved} AS {quote_col(alias)}"
                    if expr not in select_parts:
                        select_parts.append(expr)
                    if alias not in insert_cols:
                        insert_cols.append(alias)

                if not select_parts or not insert_cols:
                    continue

                select_sql = ", ".join(select_parts)
                insert_sql = ", ".join(quote_col(c) for c in insert_cols)
                conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)

                # Build identity JOIN clauses
                join_clauses = []
                join_alias = 1
                for staging_col, alias, identity_table in identity_joins:
                    id_alias = f"id{join_alias}"
                    join_alias += 1
                    join_clauses.append(
                        f"JOIN {identity_table} {id_alias}"
                        f"  ON s.identity = {id_alias}.identity"
                        f"  AND s.{quote_col(staging_col)} = {id_alias}.ext_id"
                    )

                # Add extra joins (e.g. for game_id resolution via identities_games)
                from_clause = f"{staging_table} s"
                if join_clauses:
                    from_clause += "\n      " + "\n      ".join(join_clauses)
                for ej in extra_joins:
                    from_clause += f"\n      {ej}"

                # Build UPDATE SET for columns that can be updated
                update_cols = [
                    c
                    for c in insert_cols
                    if c not in (*conflict_cols, "created_at", "updated_at")
                ]

                if update_cols:
                    update_sql = ", ".join(
                        f"{quote_col(c)} = COALESCE({quote_col(bare_name)}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
                        for c in update_cols
                    )
                    sql_template = f"""
                    INSERT INTO {intermediate_table} AS {bare_name} ({insert_sql})
                    SELECT {select_sql}
                      FROM {from_clause}
                     WHERE s.identity = %s{extra_where}
                    ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
                    """
                else:
                    sql_template = f"""
                    INSERT INTO {intermediate_table} ({insert_sql})
                    SELECT {select_sql}
                      FROM {from_clause}
                     WHERE s.identity = %s{extra_where}
                    ON CONFLICT ({conflict_sql}) DO NOTHING
                    """

                cur.execute(sql_template, (identity,))
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


def _promote_intermediate(
    league_code: str,
) -> int:
    """Promote intermediate tables to core (overwrite semantics).

    For each of the 9 intermediate tables:
      - SELECT all columns FROM intermediate.{table}
      - INSERT INTO core.{table} ... ON CONFLICT (PK) DO UPDATE
      - Intermediate IS authoritative: EXCLUDED.col overwrites core
        (not COALESCE).
      - System columns (created_at, updated_at) are never overwritten.

    Called once in execution_end cluster.
    Returns the number of rows upserted to core.
    """
    logger.info(phase_marker("promote_intermediate"))
    total_upserted = 0

    # The 9 tables that flow through intermediate -- derived from the
    # schema registry so the list can never drift from the DDL.  The
    # registry's declaration order is FK-safe for promotion: profiles
    # (teams/players) and games precede the game tables, and the season
    # tables only reference profiles.
    promote_tables = list(SCHEMAS["intermediate"].keys())

    for bare_name in promote_tables:
        intermediate_table = f"intermediate.{bare_name}"
        core_table = f"core.{bare_name}"

        cols = _get_cols_for_table(bare_name)
        if not cols:
            continue

        from src.lib.schema_resolver import get_table

        core_meta = get_table(core_table)
        conflict_cols = list(core_meta.get("primary_key") or [])

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {intermediate_table}")
                result = cur.fetchone()
                if result is None or result[0] == 0:
                    continue

                col_list = ", ".join(quote_col(c) for c in cols)

                # Never overwrite the identity/PK columns or the system
                # timestamps.
                excluded_cols = set(conflict_cols) | {"created_at", "updated_at"}
                update_cols = [c for c in cols if c not in excluded_cols]

                if conflict_cols and update_cols:
                    conflict_sql = ", ".join(quote_col(c) for c in conflict_cols)
                    # EXCLUDED.col — intermediate always overwrites core
                    update_sql = ", ".join(
                        f"{quote_col(c)} = EXCLUDED.{quote_col(c)}" for c in update_cols
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


# ============================================================================
# CLEANUP PHASES
# ============================================================================


def _clean_staging(
    league_code: str,
    identity: str,
) -> int:
    """Delete consumed staging rows for a single identity.

    Order matters:
      1. Games where BOTH home AND away teams are ready.
      2. Players WHERE status = 'ready' (CASCADE handles children).
      3. Teams WHERE status = 'ready' (CASCADE handles children).

    Rows that are not ready (including ``error`` games awaiting review)
    remain in staging; they are not re-fetched because coverage marks
    them as covered.
    """
    logger.info(phase_marker("clean_staging", f"identity={identity}"))
    total_deleted = 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            # Step 1: Games where both teams are ready
            cur.execute(
                """
                DELETE FROM staging.games g
                 USING staging.teams ht, staging.teams at
                 WHERE g.identity = ht.identity
                   AND g.ext_home_team_id = ht.ext_id
                   AND g.identity = at.identity
                   AND g.ext_away_team_id = at.ext_id
                   AND ht.status = 'ready'
                   AND at.status = 'ready'
                   AND g.identity = %s
                   AND g.status IS DISTINCT FROM 'error'
                """,
                (identity,),
            )
            deleted = cur.rowcount
            if deleted:
                logger.info("Deleted %d games from staging", deleted)
            total_deleted += deleted

            # Step 2: Ready players (CASCADE -> teams_players,
            #          countries_players, player_seasons, player_games)
            cur.execute(
                "DELETE FROM staging.players WHERE status = 'ready' AND identity = %s",
                (identity,),
            )
            deleted = cur.rowcount
            if deleted:
                logger.info(
                    "Deleted %d ready players from staging (+ cascaded)", deleted
                )
            total_deleted += deleted

            # Step 3: Ready teams (CASCADE -> leagues_teams,
            #          teams_players, team_seasons, team_games)
            cur.execute(
                "DELETE FROM staging.teams WHERE status = 'ready' AND identity = %s",
                (identity,),
            )
            deleted = cur.rowcount
            if deleted:
                logger.info(
                    "Deleted %d ready teams from staging (+ cascaded)", deleted
                )
            total_deleted += deleted

        conn.commit()

    return total_deleted


def _clean_intermediate() -> int:
    """Delete ALL rows from all 9 intermediate tables.

    No inter-table FKs in intermediate, so no cascade needed.
    Runs after promote_intermediate has copied data to core.
    """
    logger.info(phase_marker("clean_intermediate"))
    total_deleted = 0

    # All tables that flow through intermediate -- derived from the schema
    # registry so the list can never drift from the DDL.
    intermediate_tables = list(SCHEMAS["intermediate"].keys())

    with db_connection() as conn:
        with conn.cursor() as cur:
            for bare_name in intermediate_tables:
                cur.execute(f"DELETE FROM intermediate.{bare_name}")
                deleted = cur.rowcount
                if deleted:
                    logger.info(
                        "Deleted %d rows from intermediate.%s", deleted, bare_name
                    )
                total_deleted += deleted
        conn.commit()

    return total_deleted


def _prune_countries() -> int:
    """Delete core.countries rows no longer in COUNTRIES dict.

    CASCADE handles countries_players rows;
    SET NULL nullifies teams.country_code.
    """
    from src.definitions.countries import COUNTRIES

    logger.info(phase_marker("prune_countries"))
    active_codes = list(COUNTRIES.keys())
    if not active_codes:
        return 0

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM core.countries WHERE code NOT IN %s",
                (tuple(active_codes),),
            )
            deleted = cur.rowcount
            if deleted:
                logger.info(
                    "Deleted %d stale countries from core (+ cascaded)", deleted
                )
        conn.commit()

    return deleted


# ============================================================================
# TOP-LEVEL RUNNER
# ============================================================================


def run_etl(
    league_code: str | None = None,
    stage: str | None = None,
) -> None:
    """Run all ETL phase clusters for a league or all leagues.

    *stage* restricts execution to a subset of clusters:
        ``"ingest"``  — execution_start + league_setup + league_ingest
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
            _run_cluster("league_setup", lcode)
            _run_cluster("league_ingest", lcode)

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
        # Defensively DB-log so the crash is durable even if the cluster-level
        # console log scrolls out of view.
        # Wrap in try/except to avoid masking the original exception if the
        # DB itself is down (which may have *caused* the crash).
        try:
            log_error(
                phase=cluster,
                message=(
                    f"Cluster aborted: league={league_code} cluster={cluster} "
                    f"-- see traceback above"
                ),
            )
        except (ConnectionError, OSError, RuntimeError):
            logger.warning(
                "Failed to record cluster error to core.errors (DB may be unavailable)."
            )


def _run_phases(
    league_code: str,
    phases: list[str],
    cluster: str,
    season_range: list[str] | None = None,
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

    failed: list[dict[str, Any]] = []
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
        try:
            total_rows += fn(ctx)
        except Exception as exc:
            logger.exception("Phase %s failed for league %s.", phase, league_code)
            failed.append({"phase": phase, "error": str(exc)})
            log_error(
                phase=phase,
                message=(
                    f"Phase failed: league={league_code} cluster={cluster} "
                    f"phase={phase} -- {exc}"
                ),
                exc_info=exc,
            )
            # Continue to next phase instead of aborting the entire cluster.
            # Downstream phases that depend on this phase's output will fail
            # on their own terms (missing data -> natural error), while
            # independent phases still run.
            continue

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)

    return total_rows


# ═══════════════════════════════════════════════════════════════════════════
# Phase dispatch  --  explicit mapping from phase name to handler function
# ═══════════════════════════════════════════════════════════════════════════


def _phase_bootstrap_schema(ctx: dict) -> int:
    logger.info(phase_marker("bootstrap_schema"))
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
        from datetime import UTC, datetime, timedelta

        lookback_date = (
            datetime.now(UTC).date() - timedelta(days=GAME_LOOKBACK_DAYS)
        ).isoformat()

        with db_connection() as conn:
            with conn.cursor() as cur:
                # Reset season-level coverage for active types in current season
                cur.execute(
                    """UPDATE core.season_coverages SET covered = false
                        WHERE league_code = %s AND season = %s
                          AND season_type = ANY(%s)""",
                    (league_code, season, active),
                )
                season_reset = cur.rowcount

                # Reset game-level coverage for games within the lookback window
                cur.execute(
                    """UPDATE core.game_coverages SET covered = false
                        WHERE league_code = %s
                          AND game_id IN (
                              SELECT game_id FROM core.games
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
        if not _identity_supports_league(identity_code, league_code):
            continue
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
        if not _identity_supports_league(identity_code, league_code):
            continue
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

    for identity_code, identity_source, phase_datasets in _iter_league_identities(
        league_code, handler
    ):
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

    for identity_code, identity_source, phase_datasets in _iter_league_identities(
        league_code, handler
    ):
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
    for identity_code, identity_source, _ in _iter_league_identities(
        league_code, "maintain_games"
    ):
        total_rows += _maintain_games(
            league_code, season, season_range, identity_code, identity_source, failed
        )
    return total_rows


def _phase_maintain_seasons(ctx: dict) -> int:
    league_code = ctx["league_code"]
    season = ctx["season"]
    season_range = ctx["season_range"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_seasons"))
    for identity_code, identity_source, _ in _iter_league_identities(
        league_code, "maintain_seasons"
    ):
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
    for identity_code, identity_source, _ in _iter_league_identities(
        league_code, "maintain_profiles"
    ):
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


def _phase_merge_staging(ctx: dict) -> int:
    total = 0
    league_code = ctx["league_code"]
    for identity_code in DATASETS:
        if not _identity_supports_league(identity_code, league_code):
            continue
        total += _merge_staging(league_code, identity_code)
    return total


def _phase_promote_intermediate(ctx: dict) -> int:
    return _promote_intermediate(ctx["league_code"])


def _phase_clean_staging(ctx: dict) -> int:
    total = 0
    for identity_code in DATASETS:
        total += _clean_staging(ctx["league_code"], identity_code)
    return total


def _phase_clean_intermediate(ctx: dict) -> int:
    return _clean_intermediate()


def _phase_prune_stats(ctx: dict) -> int:
    logger.info(phase_marker("prune_stats"))
    return prune_stats_retention(current_season=ctx["season"])


def _phase_prune_entities(ctx: dict) -> int:
    logger.info(phase_marker("prune_entities"))
    result = prune_entities()
    return result.get("players", 0) + result.get("teams", 0)


def _phase_prune_countries(ctx: dict) -> int:
    logger.info(phase_marker("prune_countries"))
    return _prune_countries()


def _phase_prune_coverage(ctx: dict) -> int:
    logger.info(phase_marker("prune_coverage"))
    total = 0
    for lcode in LEAGUES:
        total += prune_coverage(lcode)
    return total


# ============================================================================
# maintain_pbp
# ============================================================================


def _phase_maintain_pbp(ctx: dict) -> int:
    """Phase handler for play-by-play maintenance.

    Iterates over games for the current season, calls the PBP API for
    each game, normalizes the response, accumulates into team/player
    result sets, and writes to staging via db_columns.

    After all identities are processed, cleans up local source files
    if the source declares ``local_files: True``.
    """
    league_code = ctx["league_code"]
    season = ctx["season"]
    failed = ctx["failed"]
    total_rows = 0
    logger.info(phase_marker("maintain_pbp"))

    for identity_code, identity_source, phase_datasets in _iter_league_identities(
        league_code, "maintain_pbp"
    ):
        for dataset_name in phase_datasets:
            total_rows += _maintain_pbp(
                league_code, season, identity_code, identity_source,
                dataset_name, failed,
            )

        # ISSUE-06: Clean up local source files after processing
        source_cfg = SOURCES.get(identity_source, {})
        if source_cfg.get("local_files"):
            _config_mod, client_mod = _load_source(identity_source)
            if hasattr(client_mod, "cleanup_season_files"):
                client_mod.cleanup_season_files(season)

    return total_rows


def _maintain_pbp(
    league_code: str,
    season: str,
    identity_code: str,
    identity_source: str,
    dataset_name: str,
    failed: list[dict[str, Any]],
) -> int:
    """Iterate over games and accumulate PBP into staging.

    For each game in the season:
    1. Fetch raw PBP from the source normalizer (source-agnostic)
    2. Derive context events (possessions, substitutions)
    3. Accumulate into team and player result sets
    4. Map result sets to db_columns
    5. Write to staging.team_games and staging.player_games
    """
    from src.lib.entity_resolver import make_entity_resolver
    from src.lib.load import write_staged_stats_rows
    from src.lib.pbp_accumulator import (
        accumulate_result_set,
        player_on_court_intervals,
    )
    from src.lib.pbp_classifier import (
        EventClassifier,
        FunctionMatchStrategy,
        UnclassifiedEventError,
    )
    from src.lib.pbp_deriver import derive_game_context_events

    # Get game IDs for this season from staging.games
    game_rows = _load_pbp_games(league_code, season, identity_code)
    if not game_rows:
        logger.info("No games found for PBP: league=%s season=%s", league_code, season)
        return 0

    # Season gating: skip if outside the dataset's min/max range.
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
    min_s = ds_cfg.get("min_season")
    max_s = ds_cfg.get("max_season")
    if (min_s and season < min_s) or (max_s and season > max_s):
        logger.info(
            "PBP: season %s outside dataset range [%s, %s] -- skipping",
            season, min_s or "-", max_s or "-")
        return 0

    lineup_size = LEAGUES[league_code]["lineup_size"]

    logger.info(
        "PBP: %d games to process for league=%s season=%s identity=%s",
        len(game_rows), league_code, season, identity_code,
    )

    # Build fetcher
    _config_mod, client_mod = _load_source(identity_source)

    if not hasattr(client_mod, "fetch_game_pbp"):
        raise RuntimeError(
            f"Source {identity_source!r} does not expose fetch_game_pbp(). "
            f"Dataset {dataset_name!r} has phase='maintain_pbp' which requires "
            f"a fetch_game_pbp callable on the source's client module."
        )

    # Build the PBP column mapping from db_columns
    pbp_col_map = _build_pbp_column_map(league_code, identity_code, dataset_name)

    # Build entity resolver and event classifier (single DB connection).
    try:
        from src.lib.postgres import db_connection
        with db_connection() as conn:
            entity_resolver = make_entity_resolver(conn, identity_code)

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_key, handling "
                    "FROM core.pbp_events "
                    "WHERE identity = %s AND dataset = %s",
                    (identity_code, dataset_name),
                )
                catalog_rows = [
                    {"event_key": r[0], "handling": r[1]}
                    for r in cur.fetchall()
                ]
            if catalog_rows:
                classifier = EventClassifier(
                    catalog_rows, FunctionMatchStrategy(client_mod),
                )
                logger.info(
                    "PBP classifier loaded: %d classified, %d unreviewed",
                    classifier.classified_count, classifier.unreviewed_count,
                )
            else:
                logger.warning(
                    "PBP event catalog is empty for %s.%s. "
                    "Run 'discover-pbp' first, then review and set handling. "
                    "All games will be skipped until the catalog is populated.",
                    identity_code, dataset_name,
                )
                return 0
    except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("Failed to build PBP resolver/classifier: %s", exc)
        return 0

    total_rows = 0
    for game_info in game_rows:
        ext_game_id = game_info["ext_game_id"]
        home_team_id = game_info.get("home_ext_id", "")
        away_team_id = game_info.get("away_ext_id", "")
        game_season_type = game_info.get("season_type", "regular_season")

        if not home_team_id or not away_team_id:
            logger.debug(
                "Skipping game %s: missing team IDs (home=%s, away=%s)",
                ext_game_id, home_team_id, away_team_id,
            )
            continue

        # 1. Fetch raw rows and classify every event against the catalog.
        #    Any unclassified event stops the entire phase.
        try:
            raw_rows = client_mod.fetch_raw_rows(ext_game_id, season)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            logger.warning("PBP fetch failed for game %s: %s", ext_game_id, exc)
            failed.append({
                "dataset": dataset_name,
                "game_id": ext_game_id,
                "error": str(exc),
            })
            _set_game_status(identity_code, ext_game_id, "error")
            continue

        if not raw_rows:
            logger.debug("No PBP events for game %s", ext_game_id)
            continue

        # Classify every raw row -- collect ALL unclassified, not just first
        unclassified = []
        for row in raw_rows:
            try:
                classifier.classify(row)
            except UnclassifiedEventError as e:
                unclassified.append(e)

        if unclassified:
            for uc in unclassified:
                log_error(
                    phase="maintain_pbp",
                    message=f"Unclassified event in game {ext_game_id}: "
                            f"signature={uc.signature}",
                    detail={
                        "identity": identity_code,
                        "dataset": dataset_name,
                        "ext_game_id": ext_game_id,
                    },
                )
            logger.error(
                "Game %s: %d unclassified event(s). Skipping game. "
                "Run 'discover-pbp %s.%s' to find new event types, "
                "then review core.pbp_events and set handling.",
                ext_game_id, len(unclassified),
                identity_code, dataset_name,
            )
            _set_game_status(identity_code, ext_game_id, "error")
            continue

        # 2. Normalize (all events are classified)
        try:
            events = client_mod.fetch_game_pbp(
                ext_game_id, season, home_team_id, away_team_id,
                entity_resolver,
                classifier,
                identity=identity_code,
            )
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            logger.warning("PBP normalize failed for game %s: %s", ext_game_id, exc)
            failed.append({
                "dataset": dataset_name,
                "game_id": ext_game_id,
                "error": str(exc),
            })
            _set_game_status(identity_code, ext_game_id, "error")
            continue

        if not events:
            logger.debug("No PBP events for game %s", ext_game_id)
            continue

        # 3. Derive context events (possessions, substitutions, lineups)
        derive_result = derive_game_context_events(
            events, home_team_id, away_team_id, lineup_size=lineup_size,
        )
        events = derive_result.events
        derive_errors = derive_result.errors
        for derr in derive_errors:
            log_error(
                phase="maintain_pbp",
                message=derr.message,
                detail={
                    **(derr.detail or {}),
                    "rule": derr.rule,
                    "identity": identity_code,
                    "dataset": dataset_name,
                    "ext_game_id": ext_game_id,
                    "event_id": derr.event_id,
                    "seq": derr.seq,
                    "event": derr.event,
                    "team_id": derr.team_id,
                    "player_id": derr.player_id,
                },
            )
        if derive_errors:
            logger.error(
                "Game %s: %d derivation error(s) -- marked errored for review",
                ext_game_id, len(derive_errors),
            )

        # 4. Accumulate team result sets (per scope: self + opponent rows).
        team_scopes: dict[str, dict[str, dict[str, Any]]] = {}
        for team_id in (home_team_id, away_team_id):
            opp_id = away_team_id if team_id == home_team_id else home_team_id
            team_scopes[team_id] = {
                "team": accumulate_result_set(
                    events, "team", team_id, opp_entity_id=opp_id,
                ),
                "opp_team": accumulate_result_set(
                    events, "opp_team", team_id, opp_entity_id=opp_id,
                ),
            }

        # 4. Accumulate player result sets (per scope: self, opponent,
        #    on-court rows).
        player_scopes: dict[str, dict[str, dict[str, Any]]] = {}
        player_in_events = [e for e in events if e["event"] == "player_in"]

        if player_in_events:
            player_teams: dict[str, str] = {}
            for e in player_in_events:
                pid = e.get("player_id", "")
                if pid and pid != "0":
                    player_teams[pid] = e["team_id"]

            for player_id, player_team in player_teams.items():
                intervals = player_on_court_intervals(events, player_id)
                opp_team = away_team_id if player_team == home_team_id else home_team_id
                player_scopes[player_id] = {
                    "player": accumulate_result_set(
                        events, "player", player_id,
                        opp_entity_id=opp_team,
                        player_team_id=player_team,
                        on_court_intervals=intervals,
                    ),
                    "opp_player": accumulate_result_set(
                        events, "opp_player", player_id,
                        opp_entity_id=opp_team,
                        player_team_id=player_team,
                        on_court_intervals=intervals,
                    ),
                    "on_player": accumulate_result_set(
                        events, "on_player", player_id,
                        opp_entity_id=opp_team,
                        player_team_id=player_team,
                        on_court_intervals=intervals,
                    ),
                }

        # 5. Write team results to staging
        team_rows = {}
        for team_id, scopes in team_scopes.items():
            row = _map_pbp_result_to_columns(scopes, pbp_col_map, "team_games")
            if row:
                row["ext_team_id"] = team_id
                row["ext_game_id"] = ext_game_id
                team_rows[team_id] = row

        write_failed = False

        if team_rows:
            try:
                written = write_staged_stats_rows(
                    "team",
                    team_rows,
                    season,
                    game_season_type,
                    league_code,
                    identity_code,
                )
                total_rows += written
            except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
                logger.warning(
                    "PBP team write failed for game %s: %s", ext_game_id, exc
                )
                failed.append({
                    "dataset": dataset_name,
                    "game_id": ext_game_id,
                    "error": str(exc),
                })
                write_failed = True

        # 6. Write player results to staging
        if player_scopes:
            player_rows = {}
            for player_id, scopes in player_scopes.items():
                row = _map_pbp_result_to_columns(scopes, pbp_col_map, "player_games")
                if row:
                    row["ext_player_id"] = player_id
                    row["ext_game_id"] = ext_game_id
                    player_rows[player_id] = row

            if player_rows:
                try:
                    written = write_staged_stats_rows(
                        "player",
                        player_rows,
                        season,
                        game_season_type,
                        league_code,
                        identity_code,
                    )
                    total_rows += written
                except Exception as exc:
                    logger.warning(
                        "PBP player write failed for game %s: %s", ext_game_id, exc
                    )
                    failed.append({
                        "dataset": dataset_name,
                        "game_id": ext_game_id,
                        "error": str(exc),
                    })
                    write_failed = True

        # 7. Record the per-game PBP status.  Errored games (derive errors,
        # unclassified events, or write failures) stay in staging with all
        # of their data; they never merge to intermediate and survive
        # cleanup until reviewed and re-run.
        if derive_errors or write_failed:
            _set_game_status(identity_code, ext_game_id, "error")
        else:
            _set_game_status(identity_code, ext_game_id, "ready")

    logger.info("PBP complete: %d rows written for %s", total_rows, season)
    return total_rows


def _set_game_status(identity_code: str, ext_game_id: str, status: str) -> None:
    """Record the processing status for a game on ``staging.games.status``.

    The status drives merge/cleanup gating: ``error`` games are excluded
    from ``_merge_staging`` and survive ``_clean_staging`` until reviewed
    and re-run.
    """
    from src.lib.postgres import db_connection

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE staging.games
                       SET status = %s
                     WHERE identity = %s
                       AND (ext_id = %s OR ext_game_id = %s)
                    """,
                    (status, identity_code, ext_game_id, ext_game_id),
                )
            conn.commit()
    except (ConnectionError, OSError, RuntimeError) as exc:
        logger.warning(
            "Failed to set status=%s for game %s: %s",
            status, ext_game_id, exc,
        )


def _load_pbp_games(
    league_code: str,
    season: str,
    identity_code: str,
) -> list[dict[str, Any]]:
    """Load game IDs, team IDs, and season types from staging.games for PBP processing.

    Home/away team IDs live directly on ``staging.games`` as
    ``ext_home_team_id`` / ``ext_away_team_id``; no team joins are needed.
    """
    from src.lib.load import _resolve_league_id
    from src.lib.postgres import db_connection

    query = """
        SELECT
            g.ext_id AS ext_game_id,
            g.season_type,
            g.ext_home_team_id AS home_ext_id,
            g.ext_away_team_id AS away_ext_id
        FROM staging.games g
        WHERE g.league_code = %s
            AND g.season = %s
            AND g.identity = %s
    """

    try:
        with db_connection() as conn:
            league_val = _resolve_league_id(conn, league_code)
            with conn.cursor() as cur:
                cur.execute(query, (league_val, season, identity_code))
                if cur.description is None:
                    return []
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    except (ConnectionError, OSError, RuntimeError) as exc:
        logger.warning("Failed to load PBP games: %s", exc)
        return []


def _build_pbp_column_map(
    league_code: str,
    identity_code: str,
    dataset_name: str = "pbp_stats",
) -> dict[str, dict[tuple[str, str], str]]:
    """Build mapping from (accumulator field, scope) pairs to DB columns.

    Returns:
        {target_table: {(accumulator_field, scope): db_column_name}}

    Example:
        {
            "team_games": {
                ("fg2m", "team"): "fg2m",
                ("fg2m", "opp_team"): "opp_fg2m",
                ...
            },
            "player_games": {
                ("fg2m", "player"): "fg2m",
                ("fg2m", "on_player"): "on_fg2m",
                ...
            },
        }
    """
    from src.definitions.db_columns import DB_COLUMNS

    col_map: dict[str, dict[tuple[str, str], str]] = {}

    for col_name, col_meta in DB_COLUMNS.items():
        mapping = col_meta.get("dataset_mapping")
        if not mapping:
            continue

        league_map = mapping.get(league_code, {})
        identity_map = league_map.get(identity_code, {})

        for target, target_sources in identity_map.items():
            if not isinstance(target_sources, dict):
                continue
            pbp_source = target_sources.get(dataset_name)
            if not pbp_source:
                continue

            field = pbp_source.get("field")
            result_set = pbp_source.get("result_set")
            if not field or not result_set:
                continue

            target_map = col_map.setdefault(target, {})
            target_map[(field, result_set)] = col_name

    return col_map


def _map_pbp_result_to_columns(
    result_sets_by_scope: dict[str, dict[str, Any]],
    pbp_col_map: dict[str, dict[tuple[str, str], str]],
    target_table: str,
) -> dict[str, Any]:
    """Map per-scope accumulator rows to a DB row.

    Each DB column is keyed by ``(field, scope)``; the value is read
    from the matching scope's accumulator row.
    """
    target_map = pbp_col_map.get(target_table, {})
    row: dict[str, Any] = {}
    for (field, scope), col_name in target_map.items():
        val = result_sets_by_scope.get(scope, {}).get(field)
        if val is not None:
            row[col_name] = val
    return row


PHASE_HANDLERS: dict[str, Callable] = {
    "bootstrap_schema": _phase_bootstrap_schema,
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
    "merge_staging": _phase_merge_staging,
    "promote_intermediate": _phase_promote_intermediate,
    "clean_staging": _phase_clean_staging,
    "clean_intermediate": _phase_clean_intermediate,
    "prune_stats": _phase_prune_stats,
    "prune_entities": _phase_prune_entities,
    "prune_countries": _phase_prune_countries,
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
