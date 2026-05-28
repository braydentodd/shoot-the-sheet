"""
The Glass - ETL Execution Engine

Executes a single call group against a configured source, routing to the
correct strategy based on the group's execution tier:

  - league_wide:   one API call returns all entities at once
  - team / player: per-entity API calls (with aggregation when needed)
  - team_call:     one per-team call returning player-level data

This module is the workhorse for API-driven phases.  Phase ordering lives
in :mod:`src.etl.orchestrator`; the CLI lives in :mod:`src.etl.cli`.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from src.core.lib.postgres import db_connection, quote_col
from src.etl.lib.sources_resolver import get_source_id_column
from src.core.lib.tables_resolver import get_table_name
from src.etl.lib.extract import (
    extract_columns_from_result,
    extract_raw_rows,
    get_pipeline_columns,
    get_simple_columns,
)
from src.etl.lib.load import write_entity_rows
from src.etl.lib.transform import aggregate_team_rows, execute_pipeline
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


# ============================================================================
# EXECUTION STRATEGIES
# ============================================================================

def _fetch_null_entity_ids(ctx: ExecutionContext, columns: List[str]) -> List[Any]:
    """Helper to fetch entity source IDs that have NULL values for any of the target columns,
    with caching built into the ExecutionContext to prevent duplicate DB lookups.
    """
    cols_key = frozenset(columns)
    if cols_key in ctx._null_entity_cache:
        return ctx._null_entity_cache[cols_key]

    source_id_col = get_source_id_column(ctx.source_key)
    entity_table = get_table_name(ctx.entity, 'profiles')
    target_table = get_table_name(ctx.entity, ctx.scope, ctx.db_schema)

    with db_connection() as conn:
        with conn.cursor() as cur:
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
                    (ctx.season, ctx.season_type)
                )
            source_ids = [row[0] for row in cur.fetchall() if row[0] is not None]

    ctx._null_entity_cache[cols_key] = source_ids
    return source_ids


def _execute_league_wide(
    dataset: str,
    params: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
) -> int:
    """One API call returns all entities -- extract, transform, write."""
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


def _execute_pipeline_per_entity(
    col_name: str,
    source: Dict[str, Any],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
) -> int:
    pipeline_config = source['extraction_config']
    dataset = pipeline_config['dataset']

    source_ids = _fetch_null_entity_ids(ctx, [col_name])

    if not source_ids:
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = f'{ctx.entity}_id'

    for sid in source_ids:
        def single_entity_fetcher(ds, extra_params, tier):
            # inject the current entity id
            call_params = {**extra_params, id_param: sid}
            try:
                return ctx.api_fetcher(ds, call_params)
            except Exception:
                return {'resultSets': []}

        try:
            result = execute_pipeline(
                pipeline_config, single_entity_fetcher, ctx.entity,
                ctx.season, ctx.season_type_name,
                entity_id_field=ctx.entity_id_field,
                default_entity_id=sid
            )
            consecutive_failures = 0
            if result:
                for eid, val in result.items():
                    all_rows[eid] = {col_name: val}
        except Exception as exc:
            consecutive_failures += 1
            if consecutive_failures >= ctx.max_consecutive_failures:
                logger.error('Aborting %s per-entity after %d consecutive failures', dataset, consecutive_failures)
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
) -> int:
    """Execute a transformation pipeline for a single column."""
    pipeline_config = source['extraction_config']
    tier = pipeline_config.get('tier', 'per_league')
    
    if tier in ('player', 'team'):
        return _execute_pipeline_per_entity(col_name, source, ctx, failed)

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
) -> int:
    """Per-team calls returning player-level data (e.g. on/off court).

    Aggregates across teams for traded players using per-column
    aggregation setting (sum or minute_weighted).
    """
    first_source = next(iter(columns.values()))
    result_set_name = first_source.get('result_set')
    player_id_field = first_source.get('player_id_field')
    minutes_field = first_source.get('minutes_field', 'MIN')

    if not result_set_name or not player_id_field:
        logger.error(
            'team_call columns for %s missing required result_set or player_id_field',
            dataset,
        )
        return 0

    consecutive_failures = 0
    player_team_rows: Dict[int, list] = {}
    team_ids = list(ctx.team_ids.values())

    for idx, team_id in enumerate(team_ids):
        try:
            call_params = {**params, 'team_id': team_id}
            result = ctx.api_fetcher(dataset, call_params)
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            logger.warning('Team %d failed for %s: %s', team_id, dataset, exc)
            if consecutive_failures >= ctx.max_consecutive_failures:
                logger.error(
                    'Aborting %s after %d consecutive failures',
                    dataset, consecutive_failures,
                )
                break
            continue

        if result is None:
            continue

        new_rows = extract_raw_rows(result, player_id_field, result_set_name)
        for pid, rows_list in new_rows.items():
            player_team_rows.setdefault(pid, []).extend(rows_list)

    if not player_team_rows:
        return 0

    rows = aggregate_team_rows(player_team_rows, columns, minutes_field)
    return write_entity_rows(
        ctx.entity, ctx.scope, rows, ctx.season, ctx.season_type,
        ctx.db_schema, ctx.source_key,
    )


def _execute_per_entity(
    dataset: str,
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    removed_refresh_mode: str = 'null_only',
) -> int:
    """Per-entity API calls for simple columns.

    Iterates over all known entities in the DB, calls the dataset once
    per entity (passing the entity's source_id), and extracts simple columns.
    """
    if removed_refresh_mode == 'always':
        source_id_col = get_source_id_column(ctx.source_key)
        entity_table = get_table_name(ctx.entity, 'profiles')
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {quote_col(source_id_col)} FROM {entity_table}"
                )
                source_ids = [row[0] for row in cur.fetchall() if row[0] is not None]
    else:
        source_ids = _fetch_null_entity_ids(ctx, list(columns.keys()))

    if not source_ids:
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = f'{ctx.entity}_id'  # e.g., 'player_id' or 'team_id'

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
            if consecutive_failures >= ctx.max_consecutive_failures:
                logger.error(
                    'Aborting %s after %d consecutive failures',
                    dataset, consecutive_failures,
                )
                failed.append({'dataset': dataset, 'error': str(exc)})
                break
            continue

        if result is None:
            continue

        extracted = extract_columns_from_result(
            result, columns, ctx.entity, ctx.entity_id_field,
            id_aliases=ctx.id_aliases,
        )
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

    if tier == 'team_call':
        written += _execute_team_call(dataset, params, columns, ctx, failed)
    elif tier in ('team', 'player'):
        if simple:
            written += _execute_per_entity(
                dataset, simple, ctx, failed,
                removed_refresh_mode=group.get('removed_refresh_mode', 'null_only'),
            )
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(col_name, source, ctx, failed)
    else:
        if simple:
            written += _execute_league_wide(dataset, params, simple, ctx, failed)
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(col_name, source, ctx, failed)

    return written
