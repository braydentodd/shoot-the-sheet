"""
Shoot the Sheet - Call Group Builder

Transforms column configuration into executable API call groups for any
data source.  A "call group" is a batch of columns that can be satisfied
by a single API call.

Functions accept source-specific config (``source_key``, ``datasets``)
as parameters rather than importing from a specific source, keeping this
module source-agnostic.
"""

import logging
from typing import Any, Dict, List, Tuple, Union

from src.core.definitions.db_columns import DB_COLUMNS
from src.core.definitions.schema import DEFAULT_TYPE_TRANSFORMS
from src.etl.definitions.datasets import DATASETS
from src.etl.lib.load import ENTITY_SCOPE_TABLE

logger = logging.getLogger(__name__)


# ============================================================================
# COLUMN LOOKUP HELPERS
# ============================================================================


def _columns_for_table(table_name: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Return columns whose ``tables`` list includes *table_name* or ``'all'``."""
    matched: List[Tuple[str, Dict[str, Any]]] = []
    for col_name, col_meta in DB_COLUMNS.items():
        tables = col_meta.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        if table_name in tables or "all" in tables:
            matched.append((col_name, col_meta))
    return matched


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _enrich_source(source: Dict[str, Any], col_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Add a default transform to a source based on column type if not already set."""
    enriched = {**source}
    if "transform" not in enriched and "pipeline" not in enriched:
        base_type = col_meta.get("type", "").split("(")[0]
        enriched["transform"] = DEFAULT_TYPE_TRANSFORMS.get(base_type, "safe_int")
    return enriched


def _get_source_definitions(
    col_meta: Dict[str, Any],
    entity: str,
    source_key: str,
    league_key: str,
) -> List[Dict[str, Any]]:
    """Return source entries for a column filtered by entity.

    Config format:
        ``{league: {identity: {entity: {dataset_name: DatasetMapping}}}}``

    Returns enriched dicts with ``"dataset"`` injected from the config key
    so downstream code can resolve ``entry["dataset"]`` uniformly.
    """
    all_sources = col_meta.get("dataset_mapping") or {}
    league_sources = all_sources.get(league_key, {})
    identity_sources = league_sources.get(source_key)
    if not isinstance(identity_sources, dict):
        return []
    entity_sources = identity_sources.get(entity)
    if not isinstance(entity_sources, dict):
        return []
    return [
        {"dataset": dataset_name, **mapping}
        for dataset_name, mapping in entity_sources.items()
    ]


# ============================================================================
# DATASET AVAILABILITY
# ============================================================================


def is_dataset_available(
    dataset_name: str,
    season: str,
    source_key: str,
) -> bool:
    """Check whether a dataset has data for the given season."""
    ds = DATASETS.get(source_key, {}).get(dataset_name)
    if not ds:
        return False
    min_season = ds.get("min_season")
    if min_season is None:
        return True
    return season >= min_season


# ============================================================================
# EXECUTION TIER RESOLUTION
# ============================================================================


def tier_for_dataset(dataset: str, source_key: str) -> str:
    """Get the default execution tier for a dataset."""
    return (
        DATASETS.get(source_key, {})
        .get(dataset, {})
        .get("execution_tier", "per_league")
    )


def tier_for_source(source: Dict[str, Any], dataset: str, source_key: str) -> str:
    """Resolve execution tier from a source config or the dataset default."""
    tier = source.get("tier")
    if tier:
        return tier
    pipeline = source.get("pipeline", {})
    if pipeline.get("tier"):
        return pipeline["tier"]
    return tier_for_dataset(dataset, source_key)


# ============================================================================
# CALL GROUP BUILDING
# ============================================================================


def build_call_groups(
    entity: str,
    season: str,
    source_key: str,
    scope: Union[str, None] = None,
    league_key: Union[str, None] = None,
    in_season: bool = True,
) -> List[Dict[str, Any]]:
    """Group all columns for ``entity`` into API call batches.

    Walks DB_COLUMNS, groups simple/derived columns that share the same
    (dataset, params) so each batch requires exactly one API call.
    Multi-call and pipeline columns get their own entries.

    Args:
        scope: If set, only include columns whose source table maps to this
               scope (e.g. ``'profiles'``, ``'stats'``).
        in_season: If False, excludes in_season_source columns (no games = no stat changes).
                   Columns with manager 'db', 'execution_context', or 'perennial_source'
                   are always included regardless of season state.

    Returns a list of dicts, each with:
        dataset, params, tier, columns ({col_name: enriched_source})
    """
    simple_groups: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
    special: List[Dict[str, Any]] = []

    if scope:
        table_name = ENTITY_SCOPE_TABLE[(entity, scope)]
        matched_cols = _columns_for_table(table_name)
    else:
        matched_cols = list(DB_COLUMNS.items())

    for col_name, col_meta in matched_cols:
        # Filter in_season_source columns during off-season
        manager = col_meta.get("manager", "perennial_source")
        if not in_season and manager == "in_season_source":
            continue

        # When no recent game activity, skip all stats-scoped columns.
        # Profile and roster columns are always refreshed.
        if not in_season:
            col_tables = col_meta.get("tables", [])
            if isinstance(col_tables, str):
                col_tables = [col_tables]
            stats_tables = {"player_seasons", "team_seasons"}
            if any(t in stats_tables for t in col_tables):
                continue

        sources = _get_source_definitions(
            col_meta,
            entity,
            source_key,
            league_key=league_key,
        )
        if not sources:
            continue

        # Process each source entry (handles multi-source columns)
        for src_entry in sources:
            enriched = _enrich_source(src_entry, col_meta)

            ds = enriched.get("dataset")
            if not ds:
                ds = enriched.get("pipeline", {}).get("dataset")
            if not ds:
                continue
            if not is_dataset_available(ds, season, source_key):
                continue

            if "pipeline" in enriched:
                special.append(
                    {
                        "dataset": ds,
                        "params": enriched.get("params", {}),
                        "tier": tier_for_source(enriched, ds, source_key),
                        "columns": {col_name: enriched},
                    }
                )
            elif enriched.get("tier") == "per_team":
                special.append(
                    {
                        "dataset": ds,
                        "params": enriched.get("params", {}),
                        "tier": enriched.get("tier"),
                        "columns": {col_name: enriched},
                    }
                )
            else:
                params = enriched.get("params", {})
                key = (ds, frozenset(sorted(params.items())))
                simple_groups.setdefault(key, {})[col_name] = enriched

    groups: List[Dict[str, Any]] = []

    for (ds, frozen_params), cols in simple_groups.items():
        ds_cfg = DATASETS.get(source_key, {}).get(ds, {})
        removed_refresh_mode = (
            "always"
            if ds_cfg.get("coverage") in ("all_years", "current")
            else "null_only"
        )
        groups.append(
            {
                "dataset": ds,
                "params": dict(frozen_params),
                "tier": tier_for_dataset(ds, source_key),
                "columns": cols,
                "removed_refresh_mode": removed_refresh_mode,
            }
        )

    # Merge special-tier columns that share dataset + params into one group.
    special_merged: Dict[str, Dict[tuple, Dict[str, Any]]] = {
        "per_team": {},
    }
    for item in special:
        tier = item["tier"]
        if tier in special_merged:
            params = item.get("params", {})
            key = (item["dataset"], frozenset(sorted(params.items())))
            bucket = special_merged[tier].setdefault(
                key,
                {
                    "dataset": item["dataset"],
                    "params": params,
                    "columns": {},
                },
            )
            bucket["columns"].update(item["columns"])
        else:
            groups.append(item)

    for tier, merged in special_merged.items():
        for bucket in merged.values():
            ds = bucket["dataset"]
            ds_cfg2 = DATASETS.get(source_key, {}).get(ds, {})
            groups.append(
                {
                    "dataset": ds,
                    "params": bucket["params"],
                    "tier": tier,
                    "columns": bucket["columns"],
                    "removed_refresh_mode": (
                        "always"
                        if ds_cfg2.get("coverage") in ("all_years", "current")
                        else "null_only"
                    ),
                }
            )

    return groups
