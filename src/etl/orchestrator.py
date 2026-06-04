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

import logging
from typing import Any, Callable, Dict, List, Tuple, Union

from src.core.lib.terminal import progress
from src.core.lib.schema_builder import bootstrap_schema
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.core.lib.seasons_resolver import parse_season_end_year
from src.etl.lib.sources_resolver import (
    build_source_id_columns,
    get_external_sources_for_league,
    get_source_id_column,
)
from src.etl.sources.registry import get_source_modules
from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.datasets import DATASETS
from src.etl.definitions.pipeline import (
    PIPELINE_PHASES,
    VALID_ETL_PHASES,
)
from src.etl.definitions.sources import SOURCES
from src.core.lib.leagues_resolver import get_current_season, get_retained_seasons
from src.etl.lib.cleanup import (
    normalize_stats_domains,
    prune_entities,
    prune_stats_retention,
)
from src.etl.lib.coverage_tracker import (
    _resolve_league_id,
    is_group_coverage_current,
    prune_coverages,
    upsert_group_coverage,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.call_groups import build_call_groups
from src.etl.lib.progress_tracker import (
    complete_run,
    fail_run,
    mark_group_completed,
    mark_group_failed,
    mark_group_started,
    resolve_work,
    update_run_completed_groups,
)
from src.etl.lib.entity_matcher import promote_staged_entities
from src.etl.lib.roster_maintainer import stage_rosters

logger = logging.getLogger(__name__)


VALID_PHASES = set(VALID_ETL_PHASES)


OPS_SCHEMA = 'ops'


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
            ON lr.team_id = t.{quote_col('the_glass_id')}
          JOIN profiles.leagues lp
            ON lp.{quote_col('the_glass_id')} = lr.league_id
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
        Callable[[str, str, List[Dict[str, Any]], int, bool, Any], None]
    , None] = None,
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
                    entity, season, source_key, scope=scope,
                    league_key=league_key, in_season=in_season,
                )
            if not groups:
                continue

            logger.info(
                '%s: %s %s -- %d call groups', scope, entity, season, len(groups),
            )

            season_end_year = parse_season_end_year(season, LEAGUES[league_key]['season_format'])
            ctx = ExecutionContext(
                entity=entity,
                scope=scope,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names['entity_id'][entity],
                db_schema=league_key,
                source_key=source_key,
                api_fetcher=make_fetcher(league_key, season_end_year, season_type_name, entity),
                team_ids=team_ids,
                max_consecutive_failures=api_config.get('max_consecutive_failures', 5),
                id_aliases=api_field_names.get('id_aliases', {}),
            )

            with db_connection() as conn:
                league_id = _resolve_league_id(conn, league_key)
                run_process_id, work_items = resolve_work(
                    conn, OPS_SCHEMA, entity, season, season_type, groups,
                    True, league_id=league_id,
                )

                entity_rows = 0
                failed_before = len(failed)
                succeeded_groups: List[Dict[str, Any]] = []
                bar_desc = f'{scope}/{entity}/{season}'
                try:
                    with progress(
                        total=len(work_items),
                        desc=bar_desc,
                        unit='group',
                        leave=False,
                    ) as bar:
                        for group, progress_id in work_items:
                            bar.set_postfix_str(group['dataset'], refresh=False)
                            mark_group_started(conn, OPS_SCHEMA, progress_id)
                            try:
                                rows = execute_group(group, ctx, failed, conn=conn)
                                entity_rows += rows
                                mark_group_completed(
                                    conn, OPS_SCHEMA, progress_id, rows,
                                    dataset=group.get('dataset'),
                                    tier=group.get('tier'),
                                )
                                succeeded_groups.append(group)
                            except Exception as exc:
                                logger.exception(
                                    'Group %s failed: %s', group['dataset'], exc,
                                )
                                mark_group_failed(conn, OPS_SCHEMA, progress_id, str(exc))
                                failed.append({
                                    'dataset': group['dataset'], 'error': str(exc),
                                })
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
# ETL PHASES
# ============================================================================

def _stage_profiles(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    **source_kw,
) -> int:
    """Phase: extract and upsert profiles.{entity}s rows."""
    logger.info(phase_marker('stage_profiles', f'{len(seasons)} season(s)'))
    return _run_groups(
        'profiles', entities, seasons,
        season_type, season_type_name, team_ids, failed,
        **source_kw,
    )


def _get_roster_dataset(league_key: str, source_key: str) -> Union[str, None]:
    """Return the first roster_maintainer dataset for a league/source pair."""
    for ds_name, ds_cfg in DATASETS.get(source_key, {}).items():
        if ds_cfg.get('role') == 'roster_maintainer' and league_key in ds_cfg.get('leagues', []):
            return ds_name
    return None


def _stage_rosters_phase(
    league_key: str,
    source_key: str,
    season: str,
    season_type_name: str,
    client_mod: Any,
    dataset: Union[str, None],
    failed: List[Dict[str, Any]],
) -> int:
    """Phase: pull a roster snapshot from the source and stage it.

    The source client must expose ``fetch_roster_memberships(league_key, season,
    season_type_name, dataset)`` returning an iterable of
    ``(team_source_id, player_source_id[, jersey_num])`` tuples.
    Sources that don't support this skip silently.
    """
    logger.info(phase_marker('stage_rosters', f'league={league_key} source={source_key}'))

    fetcher = getattr(client_mod, 'fetch_roster_memberships', None)
    if fetcher is None:
        logger.warning(
            'Source %r has no fetch_roster_memberships(); skipping roster sync',
            source_key,
        )
        return 0

    try:
        roster_pairs = fetcher(league_key, season, season_type_name, dataset)
    except Exception as exc:
        logger.exception(
            'Roster staging snapshot for %s/%s failed: %s', league_key, source_key, exc,
        )
        failed.append({'phase': 'stage_rosters', 'league': league_key, 'error': str(exc)})
        return 0

    counts = stage_rosters(league_key, source_key, roster_pairs, season)
    return counts['teams_staged'] + counts['players_staged']


def _stage_and_match_entities(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    client_mod: Any,
    **source_kw,
) -> int:
    """Stage entity rows and roster snapshots, then promote staged rows."""
    total_rows = _stage_profiles(
        entities,
        seasons,
        season_type,
        season_type_name,
        team_ids,
        failed,
        **source_kw,
    )

    dataset = _get_roster_dataset(source_kw['league_key'], source_kw['source_key'])
    for sync_season in seasons:
        total_rows += _stage_rosters_phase(
            source_kw['league_key'],
            source_kw['source_key'],
            sync_season,
            season_type_name,
            client_mod,
            dataset,
            failed,
        )

    promoted = promote_staged_entities(source_kw['league_key'], source_kw['source_key'])
    total_rows += (
        promoted['teams_promoted']
        + promoted['players_promoted']
        + promoted['league_rosters_written']
        + promoted['team_rosters_written']
    )
    return total_rows


def _backfill(
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    **source_kw,
) -> int:
    """Phase: fetch stats for every season in the retention window."""
    logger.info(phase_marker('backfill', f'{len(seasons)} seasons'))

    in_season = source_kw.get('in_season', True)
    groups_to_run: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    with db_connection() as conn:
        for season in seasons:
            for entity in entities:
                groups = build_call_groups(
                    entity,
                    season,
                    source_kw['source_key'],
                    scope='stats',
                    league_key=source_kw['league_key'],
                    in_season=in_season,
                )
                if not groups:
                    continue
                non_current = [
                    g for g in groups
                    if not is_group_coverage_current(
                        conn,
                        source_kw['league_key'],
                        entity,
                        season,
                        season_type,
                        source_kw['source_key'],
                        g,
                    )
                ]
                if not non_current:
                    logger.info(
                        'Skipping backfill %s/%s (%s): all groups current',
                        entity, season, source_kw['source_key'],
                    )
                    continue
                groups_to_run[(entity, season)] = non_current

    if not groups_to_run:
        logger.info('Backfill skipped: all previous seasons are already complete')
        return 0

    def _on_backfill_finished(
        entity: str,
        completed_season: str,
        succeeded_groups: List[Dict[str, Any]],
        entity_rows: int,
        had_failures: bool,
        tracker_conn,
    ) -> None:
        if had_failures:
            logger.warning(
                'Backfill coverage partially recorded for %s/%s (%d succeeded, had failures)',
                entity, completed_season, len(succeeded_groups),
            )
        for group in succeeded_groups:
            upsert_group_coverage(
                tracker_conn,
                source_kw['league_key'],
                entity,
                completed_season,
                season_type,
                source_kw['source_key'],
                group,
            )
        logger.info(
            'Backfill coverage recorded for %s/%s (%s groups, %s rows)',
            entity, completed_season, len(succeeded_groups), entity_rows,
        )

    return _run_groups(
        'stats', entities, seasons,
        season_type, season_type_name, team_ids, failed,
        groups_override=groups_to_run,
        on_entity_finished=_on_backfill_finished,
        **source_kw,
    )


def _update_current(
    entities: List[str],
    season: str,
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    **source_kw,
) -> int:
    """Phase: refresh stats for the current season only."""
    logger.info(phase_marker('update', f'season={season}'))

    def _on_update_finished(
        entity: str,
        completed_season: str,
        succeeded_groups: List[Dict[str, Any]],
        entity_rows: int,
        had_failures: bool,
        tracker_conn,
    ) -> None:
        if had_failures:
            logger.warning(
                'Update coverage partially recorded for %s/%s (%d succeeded, had failures)',
                entity, completed_season, len(succeeded_groups),
            )
        for group in succeeded_groups:
            upsert_group_coverage(
                tracker_conn,
                source_kw['league_key'],
                entity,
                completed_season,
                season_type,
                source_kw['source_key'],
                group,
            )
        logger.info(
            'Update coverage recorded for %s/%s (%s groups, %s rows)',
            entity, completed_season, len(succeeded_groups), entity_rows,
        )

    return _run_groups(
        'stats', entities, [season],
        season_type, season_type_name, team_ids, failed,
        on_entity_finished=_on_update_finished,
        **source_kw,
    )


def _resolve_handler_seasons(
    handler: str,
    season: str,
    season_range: List[str],
) -> List[str]:
    """Return the seasons a handler should process."""
    if handler == 'stage_and_match_entities':
        return season_range
    if handler == 'backfill_stats':
        return [s for s in season_range if s != season]
    if handler in {'update_current_stats', 'prune_stats_retention'}:
        return [season]
    if handler == 'normalize_stats_domains':
        return season_range
    return []


def _resolve_handler_season_type(
    handler: str,
    regular_st: str,
    regular_st_name: str,
    requested_st: str,
    requested_st_name: str,
) -> Tuple[Union[str, None], Union[str, None]]:
    """Return the season-type pair a handler should use."""
    if handler == 'stage_and_match_entities':
        return regular_st, regular_st_name
    if handler in {'prune_stats_retention', 'prune_entities', 'prune_coverages'}:
        return None, None
    return requested_st, requested_st_name


def _resolve_handler_season_types(
    handler: str,
    regular_st: str,
    all_season_types: List[str],
) -> List[str]:
    """Return the list of season types a handler should process."""
    if handler == 'stage_and_match_entities':
        return [regular_st]
    if handler in {'prune_stats_retention', 'prune_entities', 'prune_coverages'}:
        return [regular_st]
    return all_season_types


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
    league_key: Union[str, None] = None,
    phase: str = 'full',
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
            logger.info('=' * 80)
            logger.info('Executing ETL for league: %s', lkey)
            logger.info('=' * 80)
            try:
                run_etl(league_key=lkey, phase=phase)
                success_count += 1
            except KeyboardInterrupt:
                logger.warning('Interrupted by user.')
                raise
            except Exception as exc:
                logger.exception('ETL run failed for league %s.', lkey)
                fail_count += 1
                failures.append((lkey, str(exc)))

        if len(leagues_to_run) > 1:
            logger.info('=' * 80)
            logger.info('Multi-League Run Summary:')
            logger.info('  Total leagues: %d', len(leagues_to_run))
            logger.info('  Successes:     %d', success_count)
            logger.info('  Failures:      %d', fail_count)
            if failures:
                for league_key_failed, err in failures:
                    logger.error('    - %s: %s', league_key_failed, err)
            logger.info('=' * 80)
            if fail_count > 0:
                raise RuntimeError(f'{fail_count} league(s) failed')
        return
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

    season = get_current_season(league_key)

    # Detect season state to filter columns by manager type
    from src.etl.lib.season_detector import is_league_in_season
    in_season = is_league_in_season(league_key)
    season_state_str = 'IN-SEASON' if in_season else 'OFF-SEASON'

    # Discover / rosters use the league's canonical regular-season type code.
    regular_st = league_cfg['regular_season_types'][0]
    all_season_types = league_cfg['regular_season_types'] + league_cfg['postseason_types']

    logger.info(
        'ETL starting: league=%s sources=%s phase=%s season=%s types=%s state=%s',
        league_key,
        ','.join(execution_source_keys),
        phase,
        season,
        ','.join(all_season_types),
        season_state_str,
    )

    with db_connection() as conn:
        bootstrap_schema(league_key, conn=conn, source_id_columns=build_source_id_columns())

    requested_entities = ['team', 'player']
    season_range = get_retained_seasons(league_key, season)
    failed: List[Dict[str, Any]] = []
    total_rows = 0

    source_bundle_cache: Dict[str, Dict[str, Any]] = {}

    def _get_source_bundle(stage_source_key: str) -> Dict[str, Any]:
        if stage_source_key not in source_bundle_cache:
            cfg_mod, cli_mod = _load_source(stage_source_key)
            source_bundle_cache[stage_source_key] = {
                'config_mod': cfg_mod,
                'client_mod': cli_mod,
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

    configured_handlers = PIPELINE_PHASES.get(phase, [])

    for handler in configured_handlers:
        stage_entities = requested_entities

        stage_seasons = _resolve_handler_seasons(handler, season, season_range)
        if not stage_seasons:
            logger.info('Skipping handler %s: no seasons resolved', handler)
            continue
        if handler in {'stage_and_match_entities', 'backfill_stats', 'update_current_stats'}:
            stage_source_keys = execution_source_keys

            for stage_source_key in stage_source_keys:
                stage_bundle = _get_source_bundle(stage_source_key)
                stage_team_ids = _get_team_ids_for_source(stage_source_key)

                for st in _resolve_handler_season_types(handler, regular_st, all_season_types):
                    regular_st_name, requested_st_name = _resolve_source_season_type_names(
                        stage_bundle,
                        regular_st,
                        st,
                    )
                    stage_st, stage_st_name = _resolve_handler_season_type(
                        handler,
                        regular_st,
                        regular_st_name,
                        st,
                        requested_st_name,
                    )

                    stage_source_kw = dict(
                        league_key=league_key,
                        source_key=stage_source_key,
                        api_field_names=stage_bundle['api_field_names'],
                        api_config=stage_bundle['api_config'],
                        make_fetcher=stage_bundle['client_mod'].make_fetcher,
                        in_season=in_season,
                    )
                    stage_client_mod = stage_bundle['client_mod']

                    logger.info(phase_marker(handler, f'source={stage_source_key} season_type={st}'))

                    if handler == 'stage_and_match_entities':
                        total_rows += _stage_and_match_entities(
                            stage_entities,
                            stage_seasons,
                            stage_st,
                            stage_st_name,
                            stage_team_ids,
                            failed,
                            stage_client_mod,
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
                            **stage_source_kw,
                        )
        elif handler == 'normalize_stats_domains':
            logger.info(phase_marker(handler))
            for st in _resolve_handler_season_types(handler, regular_st, all_season_types):
                for entity in stage_entities:
                    total_rows += normalize_stats_domains(league_key, entity, stage_seasons, st)
        elif handler == 'prune_stats_retention':
            logger.info(phase_marker(handler))
            total_rows += prune_stats_retention(league_key, stage_seasons[0])
        elif handler == 'prune_entities':
            logger.info(phase_marker(handler))
            total_rows += prune_entities()
        elif handler == 'prune_coverages':
            logger.info(phase_marker(handler))
            total_rows += prune_coverages(league_key)
        else:
            raise ValueError(
                f"Unknown ETL stage handler {handler!r} for league {league_key!r}"
            )

    logger.info('ETL complete: %d total rows written/pruned', total_rows)

    if failed:
        logger.warning('%d failures:', len(failed))
        for f in failed:
            logger.warning('  %s', f)
