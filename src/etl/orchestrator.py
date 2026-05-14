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
        +--> src.etl.lib.roster_maintainer  (junction sync)
        +--> src.etl.lib.executor           (one API call group)
        +--> src.etl.lib.cleanup            (post-run hygiene)

Each phase is a thin wrapper around the lib function it drives; orchestration
logic that has no business in lib (e.g. resolving the active source, building
ExecutionContext) lives here.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional

from src.core.lib.terminal import progress
from src.core.lib.ddl import ensure_all, ensure_league_profile
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.etl.lib.sources_resolver import get_primary_source, get_source_id_column
from src.core.definitions.leagues import LEAGUES
from src.core.definitions.tables import CORE_SCHEMA, THE_GLASS_ID_COLUMN
from src.etl.definitions.sources import SOURCES
from src.core.lib.leagues_resolver import get_current_season, get_retained_seasons
from src.etl.lib.cleanup import (
    cleanup_stat_domains,
    prune_orphan_profiles,
    prune_stats_retention,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.load import seed_empty_stats
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


VALID_PHASES = {'full', 'discover', 'rosters', 'backfill', 'update', 'prune', 'orphan'}


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
    src_col = get_source_id_column(source_key)
    sql = f"""
        SELECT t.abbr, t.{quote_col(src_col)}
          FROM {CORE_SCHEMA}.team_profiles t
          JOIN {CORE_SCHEMA}.league_rosters lr
            ON lr.team_id = t.{quote_col(THE_GLASS_ID_COLUMN)}
          JOIN {CORE_SCHEMA}.league_profiles lp
            ON lp.{quote_col(THE_GLASS_ID_COLUMN)} = lr.league_id
         WHERE lp.league_key = %s AND lr.is_active = TRUE
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
    datasets: dict,
    api_field_names: dict,
    api_config: dict,
    make_fetcher: Callable,
) -> int:
    """Execute call groups for a given scope across entities and seasons."""
    total_rows = 0

    for season in seasons:
        for ent in entities:
            groups = build_call_groups(
                ent, season, source_key, datasets, scope=scope,
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
                except Exception as exc:
                    fail_run(conn, league_key, run_id, str(exc))
                    raise

    return total_rows


# ============================================================================
# ETL PHASES
# ============================================================================

def _discover_entities(
    entities: List[str],
    season: str,
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    **source_kw,
) -> int:
    """Phase: populate core.{entity}_profiles from current-season data."""
    logger.info(phase_marker('discover'))
    return _run_groups(
        'entity', entities, [season],
        season_type, season_type_name, team_ids, failed,
        **source_kw,
    )


def _sync_rosters_phase(
    league_key: str,
    source_key: str,
    season: str,
    season_type_name: str,
    client_mod: Any,
    failed: List[Dict[str, Any]],
) -> int:
    """Phase: pull a roster snapshot from the source and apply to junctions.

    The source client must expose ``fetch_roster_snapshot(league_key, season,
    season_type_name)`` returning an iterable of ``(team_source_id,
    player_source_id)`` tuples.  Sources that don't support this skip silently.
    """
    logger.info(phase_marker('rosters', f'league={league_key} source={source_key}'))

    fetcher = getattr(client_mod, 'fetch_roster_snapshot', None)
    if fetcher is None:
        logger.warning(
            'Source %r has no fetch_roster_snapshot(); skipping roster sync',
            source_key,
        )
        return 0

    try:
        roster_pairs = fetcher(league_key, season, season_type_name)
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
    **source_kw,
) -> int:
    """Phase: fetch stats for every season in the retention window."""
    logger.info(phase_marker('backfill', f'{len(seasons)} seasons'))
    return _run_groups(
        'stats', entities, seasons,
        season_type, season_type_name, team_ids, failed,
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
    return _run_groups(
        'stats', entities, [season],
        season_type, season_type_name, team_ids, failed,
        **source_kw,
    )


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

    source_key = get_primary_source(league_key)
    config_mod, client_mod = _load_source(source_key)

    season_types = config_mod.SEASON_TYPES
    datasets = config_mod.DATASETS
    api_config = config_mod.API_CONFIG
    api_field_names = config_mod.API_FIELD_NAMES

    league_cfg = LEAGUES[league_key]
    season = season or get_current_season(league_key)

    # Discover / rosters always use the league's canonical regular-season type.
    regular_st = league_cfg['regular_season_types'][0]
    regular_st_info = season_types.get(regular_st, season_types['rs'])
    regular_st_name = regular_st_info['name']

    # Stats phases use the CLI-selected season type.
    st_info = season_types.get(season_type, season_types['rs'])
    season_type_name = st_info['name']

    logger.info(
        'ETL starting: league=%s source=%s phase=%s season=%s type=%s entity=%s',
        league_key, source_key, phase, season, season_type_name, entity,
    )

    # Schema bootstrap (idempotent).
    ensure_all(league_key)
    with db_connection() as conn:
        ensure_league_profile(league_key, conn)

    entities = ['team', 'player'] if entity == 'all' else [entity]
    season_range = get_retained_seasons(league_key, season)
    team_ids = _get_active_team_source_ids(league_key, source_key)
    failed: List[Dict[str, Any]] = []
    total_rows = 0

    source_kw = dict(
        league_key=league_key,
        source_key=source_key,
        datasets=datasets,
        api_field_names=api_field_names,
        api_config=api_config,
        make_fetcher=client_mod.make_fetcher,
    )

    if phase in ('full', 'discover'):
        total_rows += _discover_entities(
            entities, season, regular_st, regular_st_name, team_ids, failed,
            **source_kw,
        )

    if phase in ('full', 'discover', 'rosters'):
        total_rows += _sync_rosters_phase(
            league_key, source_key, season, regular_st_name, client_mod, failed,
        )
        # Seed empty RS stats rows for active rosters; PO/PI seeded only when
        # those season types are explicitly backfilled.
        for ent in entities:
            total_rows += seed_empty_stats(ent, season, regular_st, league_key)

    if phase in ('full', 'backfill'):
        total_rows += _backfill(
            entities, season_range, season_type, season_type_name,
            team_ids, failed, **source_kw,
        )

    if phase in ('full', 'update'):
        total_rows += _update_current(
            entities, season, season_type, season_type_name,
            team_ids, failed, **source_kw,
        )

    # Domain coherency cleanup -- only after stats writes
    if phase in ('full', 'backfill', 'update'):
        logger.info(phase_marker('cleanup'))
        seasons_to_clean = season_range if phase in ('full', 'backfill') else [season]
        for s in seasons_to_clean:
            for ent in entities:
                total_rows += cleanup_stat_domains(league_key, ent, s, season_type)

    if phase in ('full', 'prune'):
        logger.info(phase_marker('prune'))
        total_rows += prune_stats_retention(league_key, season)

    logger.info('ETL complete: %d total rows written/pruned', total_rows)

    if failed:
        logger.warning('%d failures:', len(failed))
        for f in failed:
            logger.warning('  %s', f)
