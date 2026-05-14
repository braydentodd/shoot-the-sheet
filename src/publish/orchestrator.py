"""
The Glass - Publish Orchestrator

Top-level orchestration for the publish layer.  Mirrors :mod:`src.etl.orchestrator`:

    src.publish.cli           (argparse + dispatch)
        |
        v
    src.publish.orchestrator  (this module: build SyncContext, drive tabs)
        |
        +--> src.publish.lib.executor    (one tab at a time)
        +--> src.publish.lib.calculations (percentile populations)
        +--> src.publish.lib.queries      (reads from the warehouse)

Knows nothing about HTTP transports or argparse -- just builds the run
context, precomputes shared percentile populations once, and dispatches
to the per-tab workers in :mod:`src.publish.lib.executor`.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Optional

from src.core.lib.terminal import progress
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import get_db_connection
from src.core.lib.tables_resolver import get_table_name
from src.core.definitions.leagues import LEAGUES
from src.core.lib.leagues_resolver import (
    format_season_label,
    get_current_season,
    get_current_season_year,
)
from src.publish.definitions.destinations import DESTINATIONS
from src.publish.definitions.layout import AGGREGATE_TABS, SECTIONS_CONFIG
from src.publish.definitions.stats import HISTORICAL_TIMEFRAMES
from src.publish.destinations.sheets.config import (
    GOOGLE_SHEETS_CONFIG,
    SHEETS_FORMATTING,
)
from src.publish.destinations.sheets.client import get_sheets_client
from src.publish.lib.calculations import compute_pct_by_rate, derive_db_fields
from src.publish.lib.executor import (
    SyncContext,
    sync_players_tab,
    sync_team_tab,
    sync_teams_tab,
)
from src.publish.destinations.sheets.config_exporter import export_config
from src.publish.lib.progress_tracker import (
    complete_run,
    fail_run,
    mark_tab_completed,
    mark_tab_failed,
    mark_tab_started,
    resolve_work,
    update_run_completed_tabs,
)
from src.publish.lib.queries import (
    fetch_all_players,
    fetch_all_teams,
    get_teams_from_db,
)

logger = logging.getLogger(__name__)

_AUTO_RESUME = True


def _push_apps_script_config(league: str, destination: str) -> None:
    """Regenerate the Apps Script config file and push it via clasp.

    Reads the apps_script directory from the destination config.  Failures
    are logged but never raised: the sheet sync has already succeeded by the
    time this runs, and a missing clasp install or a transient push failure
    should not invalidate the upstream work.
    """
    dest_cfg = DESTINATIONS.get(destination, {})
    apps_script_cfg = dest_cfg.get('apps_script', {})
    if not apps_script_cfg.get('enabled', False):
        return

    apps_script_dir = (
        Path(__file__).resolve().parents[2] / apps_script_cfg['directory']
    )

    try:
        path = export_config(league)
        logger.info('Apps Script config exported to %s', path)
    except Exception:
        logger.exception('Apps Script config export failed.')
        return

    logger.info('Running clasp push from %s', apps_script_dir)
    try:
        subprocess.run(['clasp', 'push', '-f'], cwd=apps_script_dir, check=True)
        logger.info('clasp push succeeded')
    except subprocess.CalledProcessError as exc:
        logger.error('clasp push failed: %s', exc)
    except FileNotFoundError:
        logger.error('The clasp CLI is not installed or not in PATH.')


# ---------------------------------------------------------------------------
# Percentile pre-computation  (one-shot, used by every tab below)
# ---------------------------------------------------------------------------

def _precompute_percentiles(
    ctx: SyncContext,
    historical_config: dict,
) -> dict:
    """Pre-compute league-wide percentile populations for every stat rate.

    Called once per orchestrator run so every team and aggregate tab share
    the same population baselines (consistency + speed).
    """
    current_season = ctx.league_config[ctx.season_key]
    current_season_year = ctx.league_config['current_season_year']
    season_type_val = ctx.league_config.get('season_type', 'rs')

    query_kw = dict(
        historical_config=historical_config,
        ctx=ctx,
        current_season=current_season,
        current_season_year=current_season_year,
        season_type_val=season_type_val,
    )

    needs_current = True
    needs_historical = True
    needs_postseason = True

    supported_years = list(HISTORICAL_TIMEFRAMES.keys())
    empty_teams = {'teams': [], 'opponents': []}

    conn = get_db_connection()
    try:
        all_players_curr = (
            fetch_all_players(conn, 'current_stats', **query_kw)
            if needs_current else []
        )
        all_teams_curr = (
            fetch_all_teams(conn, 'current_stats', **query_kw)
            if needs_current else empty_teams
        )

        all_players_hist: dict = {}
        all_players_post: dict = {}
        all_teams_hist: dict = {}
        all_teams_post: dict = {}

        for y in supported_years:
            hist_kw = query_kw.copy()
            hist_kw['historical_config'] = {'mode': 'seasons', 'value': y}
            all_players_hist[y] = (
                fetch_all_players(conn, 'historical_stats', **hist_kw)
                if needs_historical else []
            )
            all_players_post[y] = (
                fetch_all_players(conn, 'postseason_stats', **hist_kw)
                if needs_postseason else []
            )
            all_teams_hist[y] = (
                fetch_all_teams(conn, 'historical_stats', **hist_kw)
                if needs_historical else empty_teams
            )
            all_teams_post[y] = (
                fetch_all_teams(conn, 'postseason_stats', **hist_kw)
                if needs_postseason else empty_teams
            )

        # Build player groups for team_average context in team percentiles.
        player_groups = defaultdict(list)
        for p in all_players_curr:
            ta = p.get(ctx.team_abbr_field)
            if ta:
                player_groups[ta].append(p)

        def _team_context_fn(entity):
            abbr = entity.get(ctx.team_abbr_field)
            return {'team_players': player_groups.get(abbr, [])}

        player_dict = {'current_stats': all_players_curr}
        team_dict = {'current_stats': all_teams_curr['teams']}
        opp_dict = {'current_stats': all_teams_curr['opponents']}

        for y in supported_years:
            player_dict[f'historical_stats_{y}yr'] = all_players_hist[y]
            player_dict[f'postseason_stats_{y}yr'] = all_players_post[y]
            team_dict[f'historical_stats_{y}yr'] = all_teams_hist[y]['teams']
            team_dict[f'postseason_stats_{y}yr'] = all_teams_post[y]['teams']
            opp_dict[f'historical_stats_{y}yr'] = all_teams_hist[y]['opponents']
            opp_dict[f'postseason_stats_{y}yr'] = all_teams_post[y]['opponents']

        precomputed = {
            'player': compute_pct_by_rate(player_dict, 'player'),
            'team': compute_pct_by_rate(
                team_dict, 'team', context_fn=_team_context_fn,
            ),
            'opponents': compute_pct_by_rate(opp_dict, 'opponents'),
            'data': {
                'player': player_dict,
                'team': team_dict,
                'opponents': opp_dict,
            },
        }
        logger.info('Percentile populations ready')
        return precomputed
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tab-loop helper
# ---------------------------------------------------------------------------

def _sync_all_tabs(
    ctx,
    client,
    spreadsheet,
    conn,
    run_id: int,
    *,
    team_tabs,
    aggregate_tabs,
    pending_lookup: dict,
    team_names: dict,
    precomputed: dict,
    delay: float,
    sync_kwargs: dict,
) -> list:
    """Iterate team tabs then aggregate tabs, tracking progress per tab.

    Returns a list of tab names that failed.
    """
    db_schema = ctx.db_schema
    total_pending = sum(
        1 for t in list(team_tabs) + list(aggregate_tabs) if t in pending_lookup
    )
    failed_tabs = []

    with progress(total=total_pending, desc='publish', unit='tab', leave=False) as bar:
        for tab in team_tabs:
            if tab not in pending_lookup:
                continue
            pid = pending_lookup[tab]
            bar.set_postfix_str(tab, refresh=False)
            mark_tab_started(conn, db_schema, pid)
            try:
                sync_team_tab(
                    ctx, client, spreadsheet, tab,
                    team_name=team_names.get(tab, tab),
                    precomputed=precomputed,
                    **sync_kwargs,
                )
                mark_tab_completed(conn, db_schema, pid)
                update_run_completed_tabs(conn, db_schema, run_id)
            except Exception as exc:
                logger.error('%s failed: %s', tab, exc, exc_info=True)
                failed_tabs.append(tab)
                mark_tab_failed(conn, db_schema, pid, str(exc))
            bar.update(1)
            time.sleep(delay)

        for tab in aggregate_tabs:
            if tab not in pending_lookup:
                continue
            pid = pending_lookup[tab]
            bar.set_postfix_str(tab, refresh=False)
            mark_tab_started(conn, db_schema, pid)
            try:
                if tab == 'all_players':
                    sync_players_tab(
                        ctx, client, spreadsheet,
                        precomputed=precomputed, **sync_kwargs,
                    )
                else:
                    sync_teams_tab(
                        ctx, client, spreadsheet,
                        precomputed=precomputed, **sync_kwargs,
                    )
                mark_tab_completed(conn, db_schema, pid)
                update_run_completed_tabs(conn, db_schema, run_id)
            except Exception as exc:
                logger.error('%s tab failed: %s', tab, exc, exc_info=True)
                failed_tabs.append(tab)
                mark_tab_failed(conn, db_schema, pid, str(exc))
            bar.update(1)
            time.sleep(delay)

    return failed_tabs


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def run_publish(
    league: str,
    stat_rate: str,
    show_advanced: bool,
    historical_config: dict,
    data_only: bool,
    priority_tab: Optional[str],
    config_export: bool = True,
    destination: str = 'google_sheets',
) -> None:
    """Run a full sync for a league to the specified destination.

    Caller (the CLI) is expected to have configured logging and validated
    config before calling this function; nothing here touches stdout.
    """
    if league not in LEAGUES:
        raise ValueError(f"Unknown league: {league!r}")

    db_schema = league

    league_config = {
        'current_season':      get_current_season(league),
        'current_season_year': get_current_season_year(league),
        'season_type':         LEAGUES[league]['regular_season_types'][0],
    }

    # Bind format_season_label to the league's season_format so downstream
    # consumers (queries, header formatters) can call it with just an end-year.
    season_format_fn = partial(
        format_season_label, league_season_format=LEAGUES[league]['season_format'],
    )

    stats_sections = frozenset(
        name for name, cfg in SECTIONS_CONFIG.items()
        if cfg.get('stats_timeframe')
    )
    db_fields = derive_db_fields(league, stats_sections, set())

    ctx = SyncContext(
        league=league,
        google_sheets_config=GOOGLE_SHEETS_CONFIG[league],
        sheet_formatting=SHEETS_FORMATTING,
        league_config=league_config,
        db_schema=db_schema,
        player_entity_table=get_table_name('player', 'entity', db_schema),
        team_entity_table=get_table_name('team', 'entity', db_schema),
        player_stats_table=get_table_name('player', 'stats', db_schema),
        team_stats_table=get_table_name('team', 'stats', db_schema),
        player_entity_fields=db_fields['player_entity_fields'],
        team_entity_fields=db_fields['team_entity_fields'],
        stat_fields=db_fields['stat_fields'],
        team_stat_fields=db_fields['team_stat_fields'],
        primary_minutes_col=(
            'minutes_x10' if 'minutes_x10' in db_fields['stat_fields'] else 'minutes'
        ),
        season_format_fn=season_format_fn,
    )

    logger.info(phase_marker('publish', f'league={league} rate={stat_rate}'))
    logger.info('Starting %s sync', 'partial update' if data_only else 'full')
    delay = (
        ctx.sheet_formatting.get('data_only_sync_delay_seconds', 0)
        if data_only
        else ctx.sheet_formatting.get('sync_delay_seconds', 0)
    )

    client = get_sheets_client(ctx.google_sheets_config)
    spreadsheet = client.open_by_key(ctx.google_sheets_config['spreadsheet_id'])

    sync_kwargs = dict(
        mode=stat_rate,
        show_advanced=show_advanced,
        historical_config=historical_config,
        data_only=data_only,
    )

    logger.info(phase_marker('precompute_percentiles'))
    precomputed = _precompute_percentiles(ctx, historical_config)

    teams_db = get_teams_from_db(ctx.db_schema)
    team_names = {abbr: name for _, (abbr, name) in teams_db.items()}
    abbrs = sorted(team_names.keys())

    if priority_tab:
        pt = priority_tab.upper()
        if pt in abbrs:
            abbrs = [pt] + [a for a in abbrs if a != pt]

    aggregate_order = list(AGGREGATE_TABS)
    if priority_tab and priority_tab.lower() in aggregate_order:
        first = priority_tab.lower()
        aggregate_order = [first] + [s for s in aggregate_order if s != first]

    all_tabs = abbrs + aggregate_order

    # Auto-resume: resolve pending work (may be subset if resuming)
    conn = get_db_connection()
    try:
        run_id, pending_items = resolve_work(
            conn, db_schema, league, all_tabs, auto_resume=_AUTO_RESUME,
        )
    except Exception:
        conn.close()
        raise

    pending_lookup = {tab: pid for tab, pid in pending_items}
    total_pending = len(pending_items)
    logger.info(
        phase_marker('publish_tabs', f'{total_pending} pending of {len(all_tabs)} total'),
    )

    # Build team_gids for aggregate tabs (needed for hyperlink resolution)
    team_gids = {ws.title: ws.id for ws in spreadsheet.worksheets()}
    sync_kwargs['team_gids'] = team_gids

    failed_tabs = _sync_all_tabs(
        ctx, client, spreadsheet, conn, run_id,
        team_tabs=abbrs, aggregate_tabs=aggregate_order,
        pending_lookup=pending_lookup, team_names=team_names,
        precomputed=precomputed, delay=delay, sync_kwargs=sync_kwargs,
    )

    if failed_tabs:
        failed_list = ', '.join(failed_tabs)
        logger.error('Sync finished with failures: %s', failed_list)
        fail_run(conn, db_schema, run_id, f'Sync failed for tab(s): {failed_list}')
        conn.close()
        raise RuntimeError(f'Sync failed for tab(s): {failed_list}')

    logger.info('Sync complete')
    complete_run(conn, db_schema, run_id)
    conn.close()

    # Apps Script config export is driven by destination config
    if config_export and DESTINATIONS.get(destination, {}).get('apps_script', {}).get('enabled', False):
        logger.info(phase_marker('apps_script_push'))
        _push_apps_script_config(league, destination)
