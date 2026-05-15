"""
The Glass - ETL Orchestrator

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
        +--> src.etl.lib.roster_maintainer  (roster sync)
        +--> src.etl.lib.executor           (one API call group)
        +--> src.etl.lib.cleanup            (post-run hygiene)

Each phase is a thin wrapper around the lib function it drives; orchestration
logic that has no business in lib (e.g. resolving the active source, building
ExecutionContext) lives here.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.core.lib.terminal import progress
from src.core.lib.ddl import ensure_all, ensure_league_profile
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.etl.lib.sources_resolver import (
    get_external_sources_for_league,
    get_role_config,
    get_source_id_column,
)
from src.core.definitions.leagues import LEAGUES
from src.core.definitions.tables import CORE_SCHEMA, THE_GLASS_ID_COLUMN
from src.etl.definitions.pipeline import (
    HANDLER_UPDATE_FREQUENCY_FILTERS,
    PIPELINE_PHASES,
    PIPELINE_STEPS,
    PROFILE_BOOTSTRAP_COLUMNS,
    VALID_ETL_PHASES,
)
from src.etl.definitions.sources import SOURCES
from src.core.lib.leagues_resolver import get_current_season, get_retained_seasons
from src.etl.lib.cleanup import (
    normalize_stats_domains,
    prune_orphan_profiles,
    prune_stats_retention,
)
from src.etl.lib.backfill_tracker import (
    compute_backfill_signature,
    is_backfill_coverage_current,
    upsert_backfill_coverage,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.plan import build_call_groups
from src.etl.lib.progress_tracker import (
    complete_run,
    fail_run,
    mark_group_completed,
    mark_group_failed,
    mark_group_started,
    resolve_work,
    update_run_completed_groups,
)
from src.etl.lib.roster_maintainer import sync_rosters

logger = logging.getLogger(__name__)


VALID_PHASES = set(VALID_ETL_PHASES) | {'orphan'}


# ============================================================================
# DYNAMIC SOURCE LOADING
# ============================================================================

def _load_source(source_key: str):
    """Dynamically import a source's config and client modules."""
    if source_key not in SOURCES:
        raise ValueError(
            f"Unknown source {source_key!r}. Registered: {sorted(SOURCES)}"
        )
    config_mod = importlib.import_module(f'src.etl.sources.{source_key}.config')
    client_mod = importlib.import_module(f'src.etl.sources.{source_key}.client')
    return config_mod, client_mod


# ============================================================================
# CORE-AWARE LOOKUPS
# ============================================================================

def _get_active_team_source_ids(league_key: str, source_key: str) -> Dict[str, int]:
    """Return ``{team_abbr: team_source_id}`` for teams currently active in
    ``core.league_rosters`` for the given league.

    Used by per-team execution strategies that need to iterate over the team
    list (e.g. on/off court datasets).
    """
    league_abbr = LEAGUES[league_key]['abbr']
    src_col = get_source_id_column(source_key)
    sql = f"""
        SELECT t.abbr, t.{quote_col(src_col)}
          FROM {CORE_SCHEMA}.team_profiles t
          JOIN {CORE_SCHEMA}.league_rosters lr
            ON lr.team_id = t.{quote_col(THE_GLASS_ID_COLUMN)}
          JOIN {CORE_SCHEMA}.league_profiles lp
            ON lp.{quote_col(THE_GLASS_ID_COLUMN)} = lr.league_id
         WHERE lp.abbr = %s AND lr.is_active = TRUE
         ORDER BY t.abbr
    """
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (league_abbr,))
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
    datasets: dict,
    api_field_names: dict,
    api_config: dict,
    make_fetcher: Callable,
    include_columns: Optional[Set[str]] = None,
    exclude_columns: Optional[Set[str]] = None,
    update_frequencies: Optional[Set[Optional[str]]] = None,
    groups_override: Optional[Dict[Tuple[str, str], List[Dict[str, Any]]]] = None,
    on_entity_finished: Optional[
        Callable[[str, str, List[Dict[str, Any]], int, bool], None]
    ] = None,
) -> int:
    """Execute call groups for a given scope across entities and seasons."""
    total_rows = 0

    for season in seasons:
        for ent in entities:
            if groups_override is not None:
                groups = groups_override.get((ent, season), [])
            else:
                groups = build_call_groups(
                    ent, season, source_key, datasets, scope=scope,
                    league_key=league_key,
                    include_columns=include_columns,
                    exclude_columns=exclude_columns,
                    update_frequencies=update_frequencies,
                )
            if not groups:
                continue

            logger.info(
                '%s: %s %s -- %d call groups', scope, ent, season, len(groups),
            )

            ctx = ExecutionContext(
                entity=ent,
                scope=scope,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names['entity_id'][ent],
                db_schema=league_key,
                source_key=source_key,
                api_fetcher=make_fetcher(season, season_type_name, ent),
                team_ids=team_ids,
                max_consecutive_failures=api_config.get('max_consecutive_failures', 5),
                id_aliases=api_field_names.get('id_aliases', {}),
            )

            with db_connection() as conn:
                run_id, work_items = resolve_work(
                    conn, league_key, ent, season, season_type, groups,
                    True,  # auto_resume
                )

                entity_rows = 0
                failed_before = len(failed)
                bar_desc = f'{scope}/{ent}/{season}'
                try:
                    with progress(
                        total=len(work_items),
                        desc=bar_desc,
                        unit='group',
                        leave=False,
                    ) as bar:
                        for group, progress_id in work_items:
                            bar.set_postfix_str(group['dataset'], refresh=False)
                            mark_group_started(conn, league_key, progress_id)
                            try:
                                rows = execute_group(group, ctx, failed)
                                entity_rows += rows
                                mark_group_completed(conn, league_key, progress_id, rows)
                            except Exception as exc:
                                logger.error(
                                    'Group %s failed: %s', group['dataset'], exc,
                                )
                                mark_group_failed(conn, league_key, progress_id, str(exc))
                                failed.append({
                                    'dataset': group['dataset'], 'error': str(exc),
                                })
                            bar.update(1)

                    total_rows += entity_rows
                    update_run_completed_groups(conn, league_key, run_id)
                    complete_run(conn, league_key, run_id, entity_rows)
                    if on_entity_finished is not None:
                        on_entity_finished(
                            ent,
                            season,
                            groups,
                            entity_rows,
                            len(failed) > failed_before,
                        )
                except Exception as exc:
                    fail_run(conn, league_key, run_id, str(exc))
                    raise

    return total_rows


# ============================================================================
# ETL PHASES
# ============================================================================

def _discover_entities(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    include_columns: Optional[Set[str]] = None,
    exclude_columns: Optional[Set[str]] = None,
    update_frequencies: Optional[Set[Optional[str]]] = None,
    **source_kw,
) -> int:
    """Phase: populate core.{entity}_profiles from configured discovery seasons."""
    logger.info(phase_marker('discover', f'{len(seasons)} season(s)'))
    return _run_groups(
        'entity', entities, seasons,
        season_type, season_type_name, team_ids, failed,
        include_columns=include_columns,
        exclude_columns=exclude_columns,
        update_frequencies=update_frequencies,
        **source_kw,
    )


def _populate_profiles(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    include_columns: Optional[Set[str]] = None,
    exclude_columns: Optional[Set[str]] = None,
    update_frequencies: Optional[Set[Optional[str]]] = None,
    **source_kw,
) -> int:
    """Phase: enrich core.{entity}_profiles with non-identity attributes."""
    logger.info(phase_marker('populate_profiles', f'{len(seasons)} season(s)'))
    return _run_groups(
        'entity', entities, seasons,
        season_type, season_type_name, team_ids, failed,
        include_columns=include_columns,
        exclude_columns=exclude_columns,
        update_frequencies=update_frequencies,
        **source_kw,
    )


def _sync_rosters_phase(
    league_key: str,
    source_key: str,
    season: str,
    season_type_name: str,
    client_mod: Any,
    roster_snapshot: Dict[str, Any],
    failed: List[Dict[str, Any]],
) -> int:
    """Phase: pull a roster snapshot from the source and apply to roster tables.

    The source client must expose ``fetch_roster_memberships(league_key, season,
    season_type_name, roster_snapshot)`` returning an iterable of
    ``(team_source_id, player_source_id[, jersey_num])`` tuples.
    Sources that don't support this skip silently.
    """
    logger.info(phase_marker('rosters', f'league={league_key} source={source_key}'))

    fetcher = getattr(client_mod, 'fetch_roster_memberships', None)
    if fetcher is None:
        logger.warning(
            'Source %r has no fetch_roster_memberships(); skipping roster sync',
            source_key,
        )
        return 0

    try:
        roster_pairs = fetcher(league_key, season, season_type_name, roster_snapshot)
    except Exception as exc:
        logger.error(
            'Roster snapshot for %s/%s failed: %s', league_key, source_key, exc,
        )
        failed.append({
            'phase': 'rosters', 'league': league_key, 'error': str(exc),
        })
        return 0

    counts = sync_rosters(league_key, source_key, roster_pairs, season)
    return counts['teams_active'] + counts['players_active']


def _backfill(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    update_frequencies: Optional[Set[Optional[str]]] = None,
    **source_kw,
) -> int:
    """Phase: fetch stats for every season in the retention window."""
    logger.info(phase_marker('backfill', f'{len(seasons)} seasons'))

    signatures: Dict[Tuple[str, str], str] = {}
    groups_to_run: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    with db_connection() as conn:
        for season in seasons:
            for ent in entities:
                groups = build_call_groups(
                    ent,
                    season,
                    source_kw['source_key'],
                    source_kw['datasets'],
                    scope='stats',
                    league_key=source_kw['league_key'],
                    update_frequencies=update_frequencies,
                )
                if not groups:
                    continue
                signature = compute_backfill_signature(ent, groups)
                if is_backfill_coverage_current(
                    conn,
                    source_kw['league_key'],
                    ent,
                    season,
                    season_type,
                    source_kw['source_key'],
                    signature,
                ):
                    logger.info(
                        'Skipping backfill %s/%s (%s): coverage already current',
                        ent,
                        season,
                        source_kw['source_key'],
                    )
                    continue
                key = (ent, season)
                groups_to_run[key] = groups
                signatures[key] = signature

    if not groups_to_run:
        logger.info('Backfill skipped: all retained seasons are already complete')
        return 0

    def _record_backfill(
        ent: str,
        completed_season: str,
        groups: List[Dict[str, Any]],
        entity_rows: int,
        had_failures: bool,
    ) -> None:
        if had_failures:
            logger.warning(
                'Backfill coverage not recorded for %s/%s due to group failures',
                ent,
                completed_season,
            )
            return
        signature = signatures.get((ent, completed_season))
        if not signature:
            return
        with db_connection() as tracker_conn:
            upsert_backfill_coverage(
                tracker_conn,
                source_kw['league_key'],
                ent,
                completed_season,
                season_type,
                source_kw['source_key'],
                signature,
            )
        logger.info(
            'Backfill coverage recorded for %s/%s (%s groups, %s rows)',
            ent,
            completed_season,
            len(groups),
            entity_rows,
        )

    return _run_groups(
        'stats', entities, seasons,
        season_type, season_type_name, team_ids, failed,
        update_frequencies=update_frequencies,
        groups_override=groups_to_run,
        on_entity_finished=_record_backfill,
        **source_kw,
    )


def _update_current(
    entities: List[str],
    season: str,
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    update_frequencies: Optional[Set[Optional[str]]] = None,
    **source_kw,
) -> int:
    """Phase: refresh stats for the current season only."""
    logger.info(phase_marker('update', f'season={season}'))
    return _run_groups(
        'stats', entities, [season],
        season_type, season_type_name, team_ids, failed,
        update_frequencies=update_frequencies,
        **source_kw,
    )


def _resolve_stage_seasons(
    stage: Dict[str, Any],
    season: str,
    season_range: List[str],
) -> List[str]:
    """Resolve stage season scope from declarative stage config."""
    window = stage['season_window']
    if window == 'current':
        return [season]
    if window == 'retained':
        return season_range
    return []


def _resolve_stage_season_type(
    stage: Dict[str, Any],
    regular_st: str,
    regular_st_name: str,
    requested_st: str,
    requested_st_name: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve stage season-type mode from declarative stage config."""
    mode = stage['season_type_mode']
    if mode == 'regular':
        return regular_st, regular_st_name
    if mode == 'requested':
        return requested_st, requested_st_name
    return None, None


def _resolve_source_season_type_names(
    source_bundle: Dict[str, Any],
    regular_st: str,
    requested_st: str,
) -> Tuple[str, str]:
    """Resolve regular/requested season type names for a specific source."""
    season_types = source_bundle['config_mod'].SEASON_TYPES
    regular_info = season_types.get(regular_st, season_types.get('rs', {}))
    requested_info = season_types.get(requested_st, season_types.get('rs', {}))
    regular_name = regular_info.get('name', regular_st)
    requested_name = requested_info.get('name', requested_st)
    return regular_name, requested_name


# ============================================================================
# PUBLIC ENTRY
# ============================================================================

def run_etl(
    league_key: Optional[str] = None,
    phase: str = 'full',
    entity: str = 'all',
    season: Optional[str] = None,
    season_type: str = 'rs',
) -> None:
    """Run one or more ETL phases for a league.

    Args:
        league_key:      Registered league key (e.g. ``'nba'``).  Required
                         for every phase except ``'orphan'``.
        phase:           Execution phase (see VALID_PHASES).
        entity:          ``'player'``, ``'team'``, or ``'all'``.
        season:          Season label.  Defaults to the league's current season.
        season_type:     ``'rs'`` / ``'po'`` / ``'pi'``.

    Caller (the CLI) is expected to have already configured logging and run
    config validation; this function never touches stdout directly.
    """
    if phase not in VALID_PHASES:
        raise ValueError(
            f"Invalid phase {phase!r}. Must be one of {sorted(VALID_PHASES)}"
        )

    # Cross-league orphan sweep is a special case (no league required).
    if phase == 'orphan':
        out = prune_orphan_profiles()
        logger.info('Orphan sweep complete: %s', out)
        return

    if not league_key:
        raise ValueError(f"Phase {phase!r} requires --league")
    if league_key not in LEAGUES:
        raise ValueError(
            f"Unknown league {league_key!r}. Registered: {sorted(LEAGUES)}"
        )

    league_cfg = LEAGUES[league_key]
    execution_source_keys = get_external_sources_for_league(league_key)
    if not execution_source_keys:
        raise ValueError(
            f"League {league_key!r} has no external sources available for ETL execution"
        )

    roster_role_cfg = get_role_config(league_key, 'roster_maintainer')
    roster_source_key = list(roster_role_cfg.keys())[0]
    roster_source_config = roster_role_cfg[roster_source_key]
    
    retained_discoverer_cfg = get_role_config(league_key, 'retained_discoverer')
    retained_discoverer_source_key = list(retained_discoverer_cfg.keys())[0]
    retained_discoverer_config = retained_discoverer_cfg[retained_discoverer_source_key]

    season = season or get_current_season(league_key)

    # Discover / rosters use the league's canonical regular-season type code.
    regular_st = league_cfg['regular_season_types'][0]

    logger.info(
        'ETL starting: league=%s sources=%s phase=%s season=%s type=%s entity=%s',
        league_key,
        ','.join(execution_source_keys),
        phase,
        season,
        season_type,
        entity,
    )

    # Schema bootstrap (idempotent).
    ensure_all(league_key)
    with db_connection() as conn:
        ensure_league_profile(league_key, conn)

    requested_entities = ['team', 'player'] if entity == 'all' else [entity]
    season_range = get_retained_seasons(league_key, season)
    identity_columns = set(PROFILE_BOOTSTRAP_COLUMNS)
    failed: List[Dict[str, Any]] = []
    total_rows = 0

    source_bundle_cache: Dict[str, Dict[str, Any]] = {}

    def _get_source_bundle(stage_source_key: str) -> Dict[str, Any]:
        if stage_source_key not in source_bundle_cache:
            cfg_mod, cli_mod = _load_source(stage_source_key)
            source_bundle_cache[stage_source_key] = {
                'config_mod': cfg_mod,
                'client_mod': cli_mod,
                'datasets': cfg_mod.DATASETS,
                'api_config': cfg_mod.API_CONFIG,
                'api_field_names': cfg_mod.API_FIELD_NAMES,
            }
        return source_bundle_cache[stage_source_key]

    team_ids_cache: Dict[str, Dict[str, int]] = {}

    def _get_team_ids_for_source(stage_source_key: str) -> Dict[str, int]:
        if stage_source_key not in team_ids_cache:
            team_ids_cache[stage_source_key] = _get_active_team_source_ids(
                league_key, stage_source_key,
            )
        return team_ids_cache[stage_source_key]

    configured_steps = PIPELINE_PHASES.get(phase, [])

    for stage_name in configured_steps:
        stage = PIPELINE_STEPS[stage_name]
        handler = stage['handler']
        stage_entities = requested_entities

        stage_include_columns: Optional[Set[str]] = None
        stage_exclude_columns: Optional[Set[str]] = None
        if handler == 'discover_entities':
            stage_include_columns = identity_columns
        elif handler == 'populate_profiles':
            stage_exclude_columns = identity_columns

        raw_stage_frequencies = HANDLER_UPDATE_FREQUENCY_FILTERS.get(handler)
        stage_update_frequencies: Optional[Set[Optional[str]]] = (
            set(raw_stage_frequencies) if raw_stage_frequencies is not None else None
        )

        stage_seasons = _resolve_stage_seasons(stage, season, season_range)
        if not stage_seasons:
            logger.info('Skipping stage %s: no seasons resolved', stage_name)
            continue
        if handler in {
            'discover_entities',
            'populate_profiles',
            'backfill_stats',
            'update_current_stats',
        }:
            if handler == 'discover_entities':
                if stage['season_window'] == 'current':
                    stage_source_keys = [roster_source_key]
                else:
                    stage_source_keys = [retained_discoverer_source_key]
            else:
                stage_source_keys = execution_source_keys

            for stage_source_key in stage_source_keys:
                stage_bundle = _get_source_bundle(stage_source_key)
                regular_st_name, requested_st_name = _resolve_source_season_type_names(
                    stage_bundle,
                    regular_st,
                    season_type,
                )
                stage_st, stage_st_name = _resolve_stage_season_type(
                    stage,
                    regular_st,
                    regular_st_name,
                    season_type,
                    requested_st_name,
                )

                stage_source_kw = dict(
                    league_key=league_key,
                    source_key=stage_source_key,
                    datasets=stage_bundle['datasets'],
                    api_field_names=stage_bundle['api_field_names'],
                    api_config=stage_bundle['api_config'],
                    make_fetcher=stage_bundle['client_mod'].make_fetcher,
                )
                stage_team_ids = _get_team_ids_for_source(stage_source_key)

                logger.info(phase_marker(stage_name, f'source={stage_source_key}'))

                if handler == 'discover_entities':
                    total_rows += _discover_entities(
                        stage_entities,
                        stage_seasons,
                        stage_st,
                        stage_st_name,
                        stage_team_ids,
                        failed,
                        include_columns=stage_include_columns,
                        exclude_columns=stage_exclude_columns,
                        update_frequencies=stage_update_frequencies,
                        **stage_source_kw,
                    )
                elif handler == 'populate_profiles':
                    total_rows += _populate_profiles(
                        stage_entities,
                        stage_seasons,
                        stage_st,
                        stage_st_name,
                        stage_team_ids,
                        failed,
                        include_columns=stage_include_columns,
                        exclude_columns=stage_exclude_columns,
                        update_frequencies=stage_update_frequencies,
                        **stage_source_kw,
                    )
                elif handler == 'backfill_stats':
                    total_rows += _backfill(
                        stage_entities,
                        stage_seasons,
                        stage_st,
                        stage_st_name,
                        stage_team_ids,
                        failed,
                        update_frequencies=stage_update_frequencies,
                        **stage_source_kw,
                    )
                elif handler == 'update_current_stats':
                    total_rows += _update_current(
                        stage_entities,
                        stage_seasons[0],
                        stage_st,
                        stage_st_name,
                        stage_team_ids,
                        failed,
                        update_frequencies=stage_update_frequencies,
                        **stage_source_kw,
                    )
        elif handler == 'sync_rosters':
            if stage['season_window'] == 'current':
                stage_source_key = roster_source_key
                stage_source_config = roster_source_config
            else:
                stage_source_key = retained_discoverer_source_key
                stage_source_config = retained_discoverer_config
                
            stage_bundle = _get_source_bundle(stage_source_key)
            regular_st_name, requested_st_name = _resolve_source_season_type_names(
                stage_bundle,
                regular_st,
                season_type,
            )
            stage_st, stage_st_name = _resolve_stage_season_type(
                stage,
                regular_st,
                regular_st_name,
                season_type,
                requested_st_name,
            )

            logger.info(phase_marker(stage_name, f'source={stage_source_key}'))
            for sync_season in stage_seasons:
                total_rows += _sync_rosters_phase(
                    league_key,
                    stage_source_key,
                    sync_season,
                    stage_st_name,
                    stage_bundle['client_mod'],
                    stage_source_config,
                    failed,
                )
            # Roster sync can change active-team sets for all sources.
            team_ids_cache.clear()
        elif handler == 'normalize_stats_domains':
            stage_st, _ = _resolve_stage_season_type(
                stage,
                regular_st,
                regular_st,
                season_type,
                season_type,
            )
            logger.info(phase_marker(stage_name))
            for s in stage_seasons:
                for ent in stage_entities:
                    total_rows += normalize_stats_domains(league_key, ent, s, stage_st)
        elif handler == 'prune_stats_retention':
            logger.info(phase_marker(stage_name))
            total_rows += prune_stats_retention(league_key, stage_seasons[0])
        else:
            raise ValueError(
                f"Unknown ETL stage handler {handler!r} for league {league_key!r}"
            )

    logger.info('ETL complete: %d total rows written/pruned', total_rows)

    if failed:
        logger.warning('%d failures:', len(failed))
        for f in failed:
            logger.warning('  %s', f)
