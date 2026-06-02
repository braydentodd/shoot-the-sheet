"""
The Glass - ETL Execution Engine

Executes a single call group against a configured source, routing to the
correct strategy based on the group's execution tier:

  - per_league: one API call returns all entities at once
  - per_team:   per-team API calls (with aggregation when needed)
  - per_player: per-player API calls (with aggregation when needed)

This module is the workhorse for API-driven phases.  Phase ordering lives
in :mod:`src.etl.orchestrator`; the CLI lives in :mod:`src.etl.cli`.
"""

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List

from src.core.lib.postgres import db_connection, quote_col
from src.etl.lib.sources_resolver import get_source_id_column
from src.core.lib.tables_resolver import get_table_name
from src.etl.lib.extract import (
    extract_columns_from_result,
    extract_raw_rows,
    extract_value_from_raw_dict,
    get_pipeline_columns,
    get_simple_columns,
)
from src.etl.lib.load import write_entity_rows
from src.etl.lib.transform import (
    aggregate_multi_season_most_recent_non_null,
    execute_pipeline,
)
from src.etl.definitions.execution import ENTITY_CHUNK_SIZE

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION CONTEXT
# ============================================================================


@dataclass
class ExecutionContext:
    """Bundles everything the execution engine needs from the provider.

    Note:
        ``db_schema`` always equals the league key (``'nba'``, ``'ncaa'``, ...)
        and is used wherever a schema prefix is expected.  ``source_key`` is the
        registered source (``'nba_api'``) and drives source-id column resolution.
    """

    entity: str
    scope: str
    season: str
    season_type: str
    season_type_name: str
    entity_id_field: str
    db_schema: str
    source_key: str
    api_fetcher: Callable
    team_ids: Dict[str, int] = field(default_factory=dict)
    max_consecutive_failures: int = 5
    id_aliases: Dict[str, list] = field(default_factory=dict)
    _null_entity_cache: Dict[frozenset, List[Any]] = field(default_factory=dict, init=False)


def _should_abort(
    consecutive_failures: int,
    max_failures: int,
    dataset: str,
) -> bool:
    """Return True when consecutive failures exceed the abort threshold."""
    if consecutive_failures >= max_failures:
        logger.error(
            'Aborting %s after %d consecutive failures',
            dataset, consecutive_failures,
        )
        return True
    return False


# ============================================================================
# EXECUTION STRATEGIES
# ============================================================================

def _fetch_null_entity_ids(
    ctx: ExecutionContext,
    columns: List[str],
    conn=None,
) -> List[Any]:
    """Fetch entity source IDs that have NULL values for target columns.

    Uses ``conn`` when provided; otherwise opens a fresh ``db_connection()``.
    Results are cached in ``ctx._null_entity_cache``.
    """
    cols_key = frozenset(columns)
    if cols_key in ctx._null_entity_cache:
        return ctx._null_entity_cache[cols_key]

    source_id_col = get_source_id_column(ctx.source_key)
    entity_table = get_table_name(ctx.entity, 'profiles')
    target_table = get_table_name(ctx.entity, ctx.scope)

    def _query(cur):
        if entity_table == target_table:
            null_checks = ' OR '.join(f'{quote_col(c)} IS NULL' for c in columns)
            cur.execute(
                f"SELECT {quote_col(source_id_col)} FROM {entity_table} "
                f"WHERE {null_checks}"
            )
        else:
            tg_id = quote_col('the_glass_id')
            null_checks = ' OR '.join(f't.{quote_col(c)} IS NULL' for c in columns)
            cur.execute(
                f"SELECT e.{quote_col(source_id_col)} FROM {entity_table} e "
                f"LEFT JOIN {target_table} t "
                f"ON e.{tg_id} = t.{tg_id} AND t.season = %s AND t.season_type = %s "
                f"WHERE t.{tg_id} IS NULL OR {null_checks}",
                (ctx.season, ctx.season_type),
            )
        return [row[0] for row in cur.fetchall() if row[0] is not None]

    if conn is not None:
        with conn.cursor() as cur:
            source_ids = _query(cur)
    else:
        with db_connection() as fresh_conn:
            with fresh_conn.cursor() as cur:
                source_ids = _query(cur)

    ctx._null_entity_cache[cols_key] = source_ids
    return source_ids


def _execute_multi_season_league_wide(
    dataset: str,
    params: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    multi_season_config: Dict[str, Any],
    conn=None,
) -> int:
    """Fetch data across multiple years and aggregate using most_recent_non_null."""
    start_year = multi_season_config['start_year']
    current_year = int(ctx.season.split('-')[0])
    
    # Collect values by entity by year
    entity_values_by_year: Dict[int, Dict[int, Any]] = {}
    
    logger.info(
        'Multi-season fetch for %s: years %d-%d',
        dataset, start_year, current_year
    )
    
    for year in range(start_year, current_year + 1):
        try:
            year_params = {**params, 'season': f'{year}-{str(year + 1)[-2:]}'}
            result = ctx.api_fetcher(dataset, year_params)
            
            if result:
                rows = extract_columns_from_result(
                    result, columns, ctx.entity, ctx.entity_id_field,
                    id_aliases=ctx.id_aliases,
                )
                # Store values by entity by year
                for entity_id, row_data in rows.items():
                    if entity_id not in entity_values_by_year:
                        entity_values_by_year[entity_id] = {}
                    # Assuming single column per multi_season group
                    col_name = next(iter(columns.keys()))
                    entity_values_by_year[entity_id][year] = row_data.get(col_name)
        except Exception as exc:
            logger.warning('Multi-season %s year %d failed: %s', dataset, year, exc)
            continue
    
    # Aggregate: most recent non-null per entity
    final_rows: Dict[int, Dict[str, Any]] = {}
    col_name = next(iter(columns.keys()))
    
    for entity_id, values_by_year in entity_values_by_year.items():
        aggregated_value = aggregate_multi_season_most_recent_non_null(values_by_year)
        if aggregated_value is not None:
            final_rows[entity_id] = {col_name: aggregated_value}
    
    if not final_rows:
        return 0
    
    return write_entity_rows(
        ctx.entity, ctx.scope, final_rows, ctx.season, ctx.season_type,
        ctx.db_schema, ctx.source_key,
    )


def _execute_league_wide(
    dataset: str,
    params: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    """One API call returns all entities -- extract, transform, write."""
    # Check if any column requires multi-season aggregation
    multi_season_config = None
    for col_meta in columns.values():
        if 'multi_season' in col_meta:
            multi_season_config = col_meta['multi_season']
            break
    
    if multi_season_config:
        return _execute_multi_season_league_wide(
            dataset, params, columns, ctx, failed, multi_season_config, conn=conn,
        )
    
    try:
        result = ctx.api_fetcher(dataset, params)
    except Exception as exc:
        logger.error('League-wide %s failed: %s', dataset, exc)
        failed.append({'dataset': dataset, 'params': params, 'error': str(exc)})
        return 0

    if result is None:
        return 0

    rows = extract_columns_from_result(
        result, columns, ctx.entity, ctx.entity_id_field,
        id_aliases=ctx.id_aliases,
    )
    return write_entity_rows(
        ctx.entity, ctx.scope, rows, ctx.season, ctx.season_type,
        ctx.db_schema, ctx.source_key,
    )


def _single_entity_fetcher(
    ctx: ExecutionContext,
    ds: str,
    extra_params: Dict[str, Any],
    tier: str,
    id_param: str,
    sid: Any,
) -> Any:
    """Fetch wrapper that injects the current entity id into API params."""
    call_params = {**extra_params, id_param: sid}
    try:
        return ctx.api_fetcher(ds, call_params)
    except Exception:
        return {'resultSets': []}


def _execute_pipeline_per_entity(
    col_name: str,
    source: Dict[str, Any],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    pipeline_config = source['extraction_config']
    dataset = pipeline_config['dataset']

    source_ids = _fetch_null_entity_ids(ctx, [col_name], conn=conn)

    if not source_ids:
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = f'{ctx.entity}_id'

    for sid in source_ids:
        fetcher = partial(_single_entity_fetcher, ctx, id_param=id_param, sid=sid)
        try:
            result = execute_pipeline(
                pipeline_config, fetcher, ctx.entity,
                ctx.season, ctx.season_type_name,
                entity_id_field=ctx.entity_id_field,
                default_entity_id=sid,
            )
            consecutive_failures = 0
            if result:
                for eid, val in result.items():
                    all_rows[eid] = {col_name: val}
        except Exception as exc:
            consecutive_failures += 1
            if _should_abort(consecutive_failures, ctx.max_consecutive_failures, dataset):
                failed.append({'column': col_name, 'error': str(exc)})
                break
            continue

        if len(all_rows) >= ENTITY_CHUNK_SIZE:
            written_count += write_entity_rows(
                ctx.entity, ctx.scope, all_rows, ctx.season, ctx.season_type,
                ctx.db_schema, ctx.source_key,
            )
            all_rows = {}

    if all_rows:
        written_count += write_entity_rows(
            ctx.entity, ctx.scope, all_rows, ctx.season, ctx.season_type,
            ctx.db_schema, ctx.source_key,
        )

    return written_count

def _execute_pipeline_column(
    col_name: str,
    source: Dict[str, Any],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    """Execute a transformation pipeline for a single column."""
    pipeline_config = source['extraction_config']
    tier = pipeline_config.get('tier', 'per_league')

    if tier in ('per_player', 'per_team'):
        return _execute_pipeline_per_entity(col_name, source, ctx, failed, conn=conn)

    def pipeline_fetcher(ds, extra_params, tr):
        try:
            return ctx.api_fetcher(ds, extra_params)
        except Exception:
            return {'resultSets': []}

    try:
        result = execute_pipeline(
            pipeline_config, pipeline_fetcher, ctx.entity,
            ctx.season, ctx.season_type_name,
            entity_id_field=ctx.entity_id_field,
            default_entity_id=None
        )
    except Exception as exc:
        logger.error('Pipeline %s failed: %s', col_name, exc)
        failed.append({'column': col_name, 'error': str(exc)})
        return 0

    if not result:
        return 0
    rows = {eid: {col_name: val} for eid, val in result.items()}
    return write_entity_rows(
        ctx.entity, ctx.scope, rows, ctx.season, ctx.season_type,
        ctx.db_schema, ctx.source_key,
    )


def _execute_team_call(
    dataset: str,
    params: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    """Per-team calls returning player-level data (e.g. on/off splits).

    Each team is queried independently; results are written immediately so
    traded players get one row per stint. No aggregation — each player-team
    combo should have exactly one raw row.
    """
    first_source = next(iter(columns.values()))
    result_set_name = first_source.get('result_set')
    player_id_field = first_source.get('player_id_field')
    filter_field = first_source.get('filter_field')
    filter_values = first_source.get('filter_values')

    if not result_set_name or not player_id_field:
        logger.error(
            'team_call columns for %s missing required result_set or player_id_field',
            dataset,
        )
        return 0

    consecutive_failures = 0
    written_count = 0
    team_ids = list(ctx.team_ids.values())

    for idx, team_id in enumerate(team_ids):
        try:
            call_params = {**params, 'team_id': team_id}
            result = ctx.api_fetcher(dataset, call_params)
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            logger.warning('Team %d failed for %s: %s', team_id, dataset, exc)
            if _should_abort(consecutive_failures, ctx.max_consecutive_failures, dataset):
                break
            continue

        if result is None:
            continue

        new_rows = extract_raw_rows(
            result, player_id_field, result_set_name,
            filter_field=filter_field, filter_values=filter_values,
        )
        if not new_rows:
            continue

        # Extract column values directly from the first (and typically only)
        # raw row per player per team, then inject the queried team_id.
        rows: Dict[int, Dict[str, Any]] = {}
        for pid, raw_list in new_rows.items():
            if not raw_list:
                continue
            raw_dict = raw_list[0]
            values = {
                col_name: extract_value_from_raw_dict(raw_dict, col_source)
                for col_name, col_source in columns.items()
            }
            values['team_id'] = team_id
            rows[pid] = values

        written_count += write_entity_rows(
            ctx.entity, ctx.scope, rows,
            ctx.season, ctx.season_type, ctx.db_schema, ctx.source_key,
        )

    return written_count


def _execute_per_entity(
    dataset: str,
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    tier: str = 'per_player',
    removed_refresh_mode: str = 'null_only',
    conn=None,
) -> int:
    """Per-entity API calls for simple columns.

    Iterates over all known entities in the DB, calls the dataset once
    per entity, and extracts simple columns.

    When *tier* is ``'per_team'``, passes ``team_id`` (from ``ctx.team_ids``)
    instead of ``{entity}_id``, and iterates over team source IDs rather
    than entity source IDs.
    """
    if tier == 'per_team':
        source_ids = list(ctx.team_ids.values())
        if not source_ids:
            return 0
    elif removed_refresh_mode == 'always':
        source_id_col = get_source_id_column(ctx.source_key)
        entity_table = get_table_name(ctx.entity, 'profiles')
        def _query_all(cur):
            cur.execute(f"SELECT {quote_col(source_id_col)} FROM {entity_table}")
            return [row[0] for row in cur.fetchall() if row[0] is not None]
        if conn is not None:
            with conn.cursor() as cur:
                source_ids = _query_all(cur)
        else:
            with db_connection() as fresh_conn:
                with fresh_conn.cursor() as cur:
                    source_ids = _query_all(cur)
    else:
        source_ids = _fetch_null_entity_ids(ctx, list(columns.keys()), conn=conn)

    if not source_ids:
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = 'team_id' if tier == 'per_team' else f'{ctx.entity}_id'

    for idx, sid in enumerate(source_ids):
        try:
            result = ctx.api_fetcher(dataset, {id_param: sid})
            consecutive_failures = 0
        except KeyError as exc:
            # Malformed response for this specific entity (e.g. missing
            # resultSet key) — skip without counting toward API-level abort.
            logger.debug(
                'Per-entity %s: no data for %s=%s (KeyError: %s)',
                dataset, id_param, sid, exc,
            )
            continue
        except Exception as exc:
            consecutive_failures += 1
            logger.warning(
                'Per-entity %s for %s=%s failed: %s', dataset, id_param, sid, exc,
            )
            if _should_abort(consecutive_failures, ctx.max_consecutive_failures, dataset):
                failed.append({'dataset': dataset, 'error': str(exc)})
                break
            continue

        if result is None:
            continue

        extracted = extract_columns_from_result(
            result, columns, ctx.entity, ctx.entity_id_field,
            id_aliases=ctx.id_aliases,
        )

        if tier == 'per_team':
            # Per-team calls: inject the queried team_id and write immediately
            # so traded players get one row per stint instead of overwriting.
            for row in extracted.values():
                row['team_id'] = sid
            written_count += write_entity_rows(
                ctx.entity, ctx.scope, extracted,
                ctx.season, ctx.season_type, ctx.db_schema, ctx.source_key,
            )
        else:
            all_rows.update(extracted)

            if len(all_rows) >= ENTITY_CHUNK_SIZE:
                written_count += write_entity_rows(
                    ctx.entity, ctx.scope, all_rows,
                    ctx.season, ctx.season_type, ctx.db_schema, ctx.source_key,
                )
                all_rows = {}

    if all_rows:
        written_count += write_entity_rows(
            ctx.entity, ctx.scope, all_rows,
            ctx.season, ctx.season_type, ctx.db_schema, ctx.source_key,
        )

    return written_count


# ============================================================================
# DISPATCHER
# ============================================================================

def execute_group(
    group: Dict[str, Any],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    """Execute a single call group and return rows written."""
    dataset = group['dataset']
    params = group['params']
    tier = group['tier']
    columns = group['columns']

    simple = get_simple_columns(columns)
    pipelines = get_pipeline_columns(columns)

    param_label = ' '.join(f'{k}={v}' for k, v in sorted(params.items()))
    logger.info(
        'Processing %s %s %s %s [%s]',
        ctx.season, ctx.season_type_name, dataset, ctx.entity, param_label,
    )

    written = 0

    if tier == 'per_team' and group.get('extraction_mode') == 'raw':
        written += _execute_team_call(dataset, params, columns, ctx, failed, conn=conn)
    elif tier == 'per_team':
        if simple:
            written += _execute_per_entity(
                dataset, simple, ctx, failed, tier,
                removed_refresh_mode=group.get('removed_refresh_mode', 'null_only'),
                conn=conn,
            )
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(col_name, source, ctx, failed, conn=conn)
    elif tier == 'per_player':
        if simple:
            written += _execute_per_entity(
                dataset, simple, ctx, failed, tier,
                removed_refresh_mode=group.get('removed_refresh_mode', 'null_only'),
                conn=conn,
            )
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(col_name, source, ctx, failed, conn=conn)
    else:
        if simple:
            written += _execute_league_wide(dataset, params, simple, ctx, failed, conn=conn)
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(col_name, source, ctx, failed, conn=conn)

    return written
