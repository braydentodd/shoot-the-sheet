"""
Shoot the Sheet - ETL Execution Engine

Executes a single call group against a configured source, routing to the
correct strategy based on the group's execution tier:

  - per_league: one API call returns all entities at once
  - per_team:   per-team API calls (with aggregation when needed)
  - per_player: per-player API calls (with aggregation when needed)

This module is the workhorse for API-driven phases.  Phase ordering lives
in :mod:`src.orchestrator`; the CLI lives in :mod:`src.cli`.
"""

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List, Union

from src.definitions.datasets import DATASETS
from src.definitions.execution import ENTITY_CHUNK_SIZE
from src.definitions.leagues import LEAGUES
from src.lib.extract import (
    extract_columns_from_result,
    get_pipeline_columns,
    get_simple_columns,
)
from src.lib.load import write_entity_rows
from src.lib.postgres import db_connection, quote_col
from src.lib.season_formatter import format_season_label, parse_season_end_year
from src.lib.transform import (
    aggregate_multi_season_most_recent_non_null,
    execute_pipeline,
)

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION CONTEXT
# ============================================================================


@dataclass
class ExecutionContext:
    """Bundles everything the execution engine needs from the provider.

    ``table_name`` is the bare target table (e.g. ``'players'``,
    ``'player_seasons'``).  It is used to resolve the staging table for
    null-entity queries and to route writes.
    """

    target: str
    table_name: str
    season: str
    season_type: str
    season_type_name: str
    entity_id_field: str
    db_schema: str
    identity_code: str
    api_fetcher: Callable
    team_ids: Dict[str, int] = field(default_factory=dict)
    max_consecutive_failures: int = 5
    id_aliases: Dict[str, list] = field(default_factory=dict)
    _null_entity_cache: Dict[frozenset, List[Any]] = field(
        default_factory=dict, init=False
    )


def _should_abort(
    consecutive_failures: int,
    max_failures: int,
    dataset: str,
) -> bool:
    """Return True when consecutive failures exceed the abort threshold."""
    if consecutive_failures >= max_failures:
        logger.error(
            "Aborting %s after %d consecutive failures",
            dataset,
            consecutive_failures,
        )
        return True
    return False


# ============================================================================
# STAGING TABLE RESOLUTION
# ============================================================================

_STATS_TABLES = {"player_seasons", "team_seasons", "player_games", "team_games"}


def _target_api_param(target: str) -> str:
    """Derive the API parameter name from a target key.

    ``player_seasons`` and ``player_games`` both use ``player_id``;
    ``team_seasons`` and ``team_games`` both use ``team_id``.
    """
    return "player_id" if target.startswith("player") else "team_id"


def _resolve_staging_table(table_name: str) -> str:
    """Return the schema-qualified staging table name.

    ``table_name`` is the bare name (e.g. ``'players'``, ``'player_seasons'``).
    The staging table is always ``staging.{table_name}``.
    No ``_staging`` suffix is appended -- the schema prefix is the convention.
    """
    return f"staging.{table_name}"


# ============================================================================
# NULL-ENTITY ID FETCHING
# ============================================================================


def _fetch_null_entity_ids(
    ctx: ExecutionContext,
    columns: List[str],
    conn=None,
) -> List[Any]:
    """Fetch target source IDs from the staging table that have NULL values
    for the given *columns*."""
    cols_key = frozenset(columns)
    if cols_key in ctx._null_entity_cache:
        return ctx._null_entity_cache[cols_key]

    staging_table = _resolve_staging_table(ctx.table_name)
    is_stats = ctx.table_name in _STATS_TABLES

    def _query(cur):
        null_checks = " OR ".join(f"{quote_col(c)} IS NULL" for c in columns)
        if is_stats:
            cur.execute(
                f"SELECT {quote_col('ext_id')} FROM {staging_table} "
                f"WHERE season = %s AND season_type = %s "
                f"AND ({null_checks})",
                (ctx.season, ctx.season_type),
            )
        else:
            cur.execute(
                f"SELECT {quote_col('ext_id')} FROM {staging_table} WHERE {null_checks}"
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
    logger.debug(
        "_fetch_null_entity_ids: table=%s cols=%s -> %d identities",
        staging_table,
        columns,
        len(source_ids),
    )
    return source_ids


# ============================================================================
# EXECUTION STRATEGIES
# ============================================================================


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
    season_format = LEAGUES[ctx.db_schema]["season_format"]
    ds_cfg = DATASETS.get(ctx.identity_code, {}).get(dataset, {})

    start_year_str = ds_cfg.get("min_season") or "2000-01"
    start_year = parse_season_end_year(start_year_str, season_format)
    current_year = parse_season_end_year(ctx.season, season_format)

    wire = ds_cfg.get("source_mapping", {})
    season_param = wire.get("season_param", "season")

    entity_values_by_year: Dict[int, Dict[int, Any]] = {}

    logger.info(
        "Multi-season fetch for %s: years %d-%d", dataset, start_year, current_year
    )

    for year in range(start_year, current_year + 1):
        try:
            if season_param == "season_year":
                year_params = {**params, season_param: year}
            else:
                year_label = format_season_label(year, season_format)
                year_params = {**params, season_param: year_label}
            result = ctx.api_fetcher(dataset, year_params)

            if result:
                rows = extract_columns_from_result(
                    result,
                    columns,
                    ctx.target,
                    ctx.entity_id_field,
                    id_aliases=ctx.id_aliases,
                )
                for entity_id, row_data in rows.items():
                    if entity_id not in entity_values_by_year:
                        entity_values_by_year[entity_id] = {}
                    col_name = next(iter(columns.keys()))
                    entity_values_by_year[entity_id][year] = row_data.get(col_name)
        except Exception as exc:
            logger.warning("Multi-season %s year %d failed: %s", dataset, year, exc)
            continue

    final_rows: Dict[int, Dict[str, Any]] = {}
    col_name = next(iter(columns.keys()))

    for entity_id, values_by_year in entity_values_by_year.items():
        aggregated_value = aggregate_multi_season_most_recent_non_null(values_by_year)
        if aggregated_value is not None:
            final_rows[entity_id] = {col_name: aggregated_value}

    if not final_rows:
        return 0

    return write_entity_rows(
        ctx.target,
        ctx.table_name,
        final_rows,
        ctx.season,
        ctx.season_type,
        ctx.db_schema,
        ctx.identity_code,
    )


def _execute_league_wide(
    dataset: str,
    params: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
    result: Union[Dict[str, Any], None] = None,
) -> int:
    """One API call returns all entities -- extract, transform, write.

    If *result* is provided, use it instead of calling the API.
    """
    if result is None:
        ds_cfg = DATASETS.get(ctx.identity_code, {}).get(dataset, {})
        multi_season_config = (
            {"aggregation": "most_recent_non_null"}
            if ds_cfg.get("coverage") == "all_years"
            else None
        )
        if multi_season_config:
            return _execute_multi_season_league_wide(
                dataset, params, columns, ctx, failed, multi_season_config, conn=conn
            )

        try:
            result = ctx.api_fetcher(dataset, params)
        except Exception as exc:
            logger.error("League-wide %s failed: %s", dataset, exc)
            failed.append({"dataset": dataset, "params": params, "error": str(exc)})
            return 0

        if result is None:
            return 0

    ds_cfg = DATASETS.get(ctx.identity_code, {}).get(dataset, {})

    rows = extract_columns_from_result(
        result,
        columns,
        ctx.target,
        ctx.entity_id_field,
        id_aliases=ctx.id_aliases,
    )
    logger.debug(
        "_execute_league_wide: %s -> %d entities extracted", dataset, len(rows)
    )
    return write_entity_rows(
        ctx.target,
        ctx.table_name,
        rows,
        ctx.season,
        ctx.season_type,
        ctx.db_schema,
        ctx.identity_code,
    )


def _single_entity_fetcher(
    ctx: ExecutionContext,
    ds: str,
    extra_params: Dict[str, Any],
    tier: str,
    id_param: str,
    identity_value: Any,
) -> Any:
    """Fetch wrapper that injects the current entity identity into API params."""
    call_params = {**extra_params, id_param: identity_value}
    try:
        return ctx.api_fetcher(ds, call_params)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        return {"resultSets": []}


def _execute_pipeline_per_entity(
    col_name: str,
    source: Dict[str, Any],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    conn=None,
) -> int:
    pipeline_config = source["extraction_config"]
    dataset = pipeline_config["dataset"]

    identities = _fetch_null_entity_ids(ctx, [col_name], conn=conn)

    if not identities:
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = _target_api_param(ctx.target)

    for identity_value in identities:
        fetcher = partial(
            _single_entity_fetcher,
            ctx,
            id_param=id_param,
            identity_value=identity_value,
        )
        try:
            result = execute_pipeline(
                pipeline_config,
                fetcher,
                ctx.target,
                ctx.season,
                ctx.season_type_name,
                entity_id_field=ctx.entity_id_field,
                default_entity_id=identity_value,
            )
            consecutive_failures = 0
            if result:
                for eid, val in result.items():
                    all_rows[eid] = {col_name: val}
        except Exception as exc:
            consecutive_failures += 1
            if _should_abort(
                consecutive_failures, ctx.max_consecutive_failures, dataset
            ):
                failed.append({"column": col_name, "error": str(exc)})
                break
            continue

        if len(all_rows) >= ENTITY_CHUNK_SIZE:
            written_count += write_entity_rows(
                ctx.target,
                ctx.table_name,
                all_rows,
                ctx.season,
                ctx.season_type,
                ctx.db_schema,
                ctx.identity_code,
            )
            all_rows = {}

    if all_rows:
        written_count += write_entity_rows(
            ctx.target,
            ctx.table_name,
            all_rows,
            ctx.season,
            ctx.season_type,
            ctx.db_schema,
            ctx.identity_code,
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
    pipeline_config = source["extraction_config"]
    tier = pipeline_config.get("tier", "per_league")

    if tier in ("per_player", "per_team"):
        return _execute_pipeline_per_entity(col_name, source, ctx, failed, conn=conn)

    def pipeline_fetcher(ds, extra_params, tr):
        try:
            return ctx.api_fetcher(ds, extra_params)
        except Exception:
            return {"resultSets": []}

    try:
        result = execute_pipeline(
            pipeline_config,
            pipeline_fetcher,
            ctx.target,
            ctx.season,
            ctx.season_type_name,
            entity_id_field=ctx.entity_id_field,
            default_entity_id=None,
        )
    except Exception as exc:
        logger.error("Pipeline %s failed: %s", col_name, exc)
        failed.append({"column": col_name, "error": str(exc)})
        return 0

    if not result:
        return 0
    rows = {eid: {col_name: val} for eid, val in result.items()}
    return write_entity_rows(
        ctx.target,
        ctx.table_name,
        rows,
        ctx.season,
        ctx.season_type,
        ctx.db_schema,
        ctx.identity_code,
    )


def _execute_per_entity(
    dataset: str,
    columns: Dict[str, Dict[str, Any]],
    ctx: ExecutionContext,
    failed: List[Dict[str, Any]],
    tier: str = "per_player",
    removed_refresh_mode: str = "null_only",
    conn=None,
) -> int:
    """Per-target API calls for simple columns.

    When *tier* is ``'per_team'``, passes ``team_id`` (from ``ctx.team_ids``)
    instead of ``{target}_id``, and iterates over team identities rather
    than target identities.
    """
    if tier == "per_team":
        identities = list(ctx.team_ids.values())
        if not identities:
            logger.debug(
                "Per-entity %s: no team IDs available (table=%s)",
                dataset,
                ctx.table_name,
            )
            return 0
    else:
        identities = _fetch_null_entity_ids(ctx, list(columns.keys()), conn=conn)

    if not identities:
        logger.debug(
            "Per-entity %s: no identities to query (tier=%s refresh=%s)",
            dataset,
            tier,
            removed_refresh_mode,
        )
        return 0

    all_rows: Dict[int, Dict[str, Any]] = {}
    written_count = 0
    consecutive_failures = 0
    id_param = "team_id" if tier == "per_team" else _target_api_param(ctx.target)

    for idx, identity_value in enumerate(identities):
        try:
            result = ctx.api_fetcher(dataset, {id_param: identity_value})
            consecutive_failures = 0
        except KeyError as exc:
            logger.debug(
                "Per-entity %s: no data for %s=%s (KeyError: %s)",
                dataset,
                id_param,
                identity_value,
                exc,
            )
            continue
        except Exception as exc:
            consecutive_failures += 1
            logger.warning(
                "Per-entity %s for %s=%s failed: %s",
                dataset,
                id_param,
                identity_value,
                exc,
            )
            if _should_abort(
                consecutive_failures, ctx.max_consecutive_failures, dataset
            ):
                failed.append({"dataset": dataset, "error": str(exc)})
                break
            continue

        if result is None:
            continue

        extracted = extract_columns_from_result(
            result,
            columns,
            ctx.target,
            ctx.entity_id_field,
            id_aliases=ctx.id_aliases,
        )

        if tier == "per_team":
            for row in extracted.values():
                row["ext_team_id"] = identity_value
            written_count += write_entity_rows(
                ctx.target,
                ctx.table_name,
                extracted,
                ctx.season,
                ctx.season_type,
                ctx.db_schema,
                ctx.identity_code,
            )
        else:
            all_rows.update(extracted)

            if len(all_rows) >= ENTITY_CHUNK_SIZE:
                written_count += write_entity_rows(
                    ctx.target,
                    ctx.table_name,
                    all_rows,
                    ctx.season,
                    ctx.season_type,
                    ctx.db_schema,
                    ctx.identity_code,
                )
                all_rows = {}

    if all_rows:
        written_count += write_entity_rows(
            ctx.target,
            ctx.table_name,
            all_rows,
            ctx.season,
            ctx.season_type,
            ctx.db_schema,
            ctx.identity_code,
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
    result: Union[Dict[str, Any], None] = None,
) -> int:
    """Execute a single call group and return rows written.

    If *result* is provided, use it instead of calling the API.
    """
    dataset = group["dataset"]
    params = group["params"]
    tier = group["tier"]
    columns = group["columns"]

    simple = get_simple_columns(columns)
    pipelines = get_pipeline_columns(columns)

    param_label = " ".join(f"{k}={v}" for k, v in sorted(params.items()))
    if param_label:
        logger.info(
            "Processing %s %s %s %s [%s]",
            ctx.season,
            ctx.season_type_name,
            dataset,
            ctx.target,
            param_label,
        )
    else:
        logger.info(
            "Processing %s %s %s %s",
            ctx.season,
            ctx.season_type_name,
            dataset,
            ctx.target,
        )

    written = 0
    per_entity_tiers = {"per_team", "per_player", "per_game"}

    if tier in per_entity_tiers:
        written += _execute_per_entity(
            dataset,
            simple,
            ctx,
            failed,
            tier,
            removed_refresh_mode=group.get("removed_refresh_mode", "null_only"),
            conn=conn,
        )
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(
                col_name, source, ctx, failed, conn=conn
            )
    else:
        written += _execute_league_wide(
            dataset, params, simple, ctx, failed, conn=conn, result=result
        )
        for col_name, source in pipelines.items():
            written += _execute_pipeline_column(
                col_name, source, ctx, failed, conn=conn
            )

    return written
