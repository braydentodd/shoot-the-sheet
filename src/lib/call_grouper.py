"""Shoot the Sheet - Call Group Builder

Transforms column configuration into executable API call groups for any
data identity.  A "call group" is a batch of columns that can be satisfied
by a single API call.

Functions accept identity-specific config (``identity_code``, ``datasets``)
as parameters rather than importing from a specific identity, keeping this
module identity-agnostic.
"""

import logging
from typing import Any, Dict, List, Tuple, Union

from src.definitions.datasets import DATASETS
from src.definitions.db_columns import DB_COLUMNS
from src.definitions.schema import DEFAULT_TYPE_TRANSFORMS

logger = logging.getLogger(__name__)


# ============================================================================
# COLUMN DISCOVERY
# ============================================================================


def columns_for_table(table_name: str) -> List[Tuple[str, Any]]:
    """Return columns whose ``tables`` list includes *table_name* or ``'all'``.

    Handles both bare table names (``"games"``) and schema-qualified names
    (``"staging.games"``) -- the table part is extracted from qualified names
    before comparison, so a column declared with ``"staging.games"`` is found
    when queried with bare ``"games"``.
    """
    matched: List[Tuple[str, Any]] = []
    for col_name, col_meta in DB_COLUMNS.items():
        tables = col_meta.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        for entry in tables:
            if entry == "all":
                matched.append((col_name, col_meta))
                break
            # Strip schema qualifier ("staging.games" -> "games") before matching
            entry_table = entry.split(".", 1)[1] if "." in entry else entry
            if entry_table == table_name:
                matched.append((col_name, col_meta))
                break
    if not matched:
        logger.debug("No columns found for table=%s", table_name)
    return matched


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _enrich_source(source: Dict[str, Any], col_meta: Any) -> Dict[str, Any]:
    """Add a default transform based on column type if not already set."""
    enriched = {**source}
    if "transform" not in enriched and "pipeline" not in enriched:
        base_type = col_meta.get("type", "").split("(")[0]
        enriched["transform"] = DEFAULT_TYPE_TRANSFORMS.get(base_type, "safe_int")
    return enriched


def _get_all_target_sources(
    col_meta: Any,
    identity_code: str,
    league_code: str,
) -> List[Dict[str, Any]]:
    """Return source entries for ALL targets that reference this column."""
    all_sources = col_meta.get("dataset_mapping") or {}
    league_sources = all_sources.get(league_code, {})
    identity_sources = league_sources.get(identity_code)
    if not isinstance(identity_sources, dict):
        return []
    results: List[Dict[str, Any]] = []
    for target, target_sources in identity_sources.items():
        if not isinstance(target_sources, dict):
            continue
        for dataset_name, mapping in target_sources.items():
            results.append({"dataset": dataset_name, "target": target, **mapping})
    return results


# ============================================================================
# DATASET AVAILABILITY
# ============================================================================


def is_dataset_available(
    dataset_name: str,
    season: str,
    identity_code: str,
) -> bool:
    """Check whether a dataset has data for the given season."""
    ds = DATASETS.get(identity_code, {}).get(dataset_name)
    if not ds:
        return False
    min_season = ds.get("min_season")
    max_season = ds.get("max_season")
    if min_season and season < min_season:
        return False
    if max_season and season > max_season:
        return False
    return True


# ============================================================================
# EXECUTION TIER RESOLUTION
# ============================================================================


def tier_for_dataset(dataset: str, identity_code: str) -> str:
    """Get the default iteration strategy for a dataset."""
    return DATASETS.get(identity_code, {}).get(dataset, {}).get("iterates_by", "none")


def tier_for_source(source: Dict[str, Any], dataset: str, identity_code: str) -> str:
    """Resolve execution tier from a source config or the dataset default."""
    tier = source.get("tier")
    if tier:
        return tier
    pipeline = source.get("pipeline", {})
    if pipeline.get("tier"):
        return pipeline["tier"]
    return tier_for_dataset(dataset, identity_code)


# ============================================================================
# CALL GROUP BUILDING
# ============================================================================


def build_call_groups(
    season: str,
    identity_code: str,
    dataset: str,
    table_name: Union[str, None] = None,
    league_code: Union[str, None] = None,
    in_season: bool = True,
) -> List[Dict[str, Any]]:
    """Group ALL columns across ALL targets that reference *dataset*.

    A call group is a batch of columns satisfied by a single API call.
    Columns from every target are included - the orchestrator extracts
    per-target after fetching.

    Returns a list of dicts, each with:
        dataset, params, tier, columns ({col_name: enriched_source})
    """
    league_wide: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
    per_entity: List[Dict[str, Any]] = []

    if table_name:
        matched_cols = columns_for_table(table_name)
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

        # Collect sources across ALL targets for this column
        all_sources = _get_all_target_sources(
            col_meta,
            identity_code,
            league_code=league_code or "",
        )
        if not all_sources:
            continue

        # Process each source entry (handles multi-source columns)
        for src_entry in all_sources:
            enriched = _enrich_source(src_entry, col_meta)

            ds = enriched.get("dataset")
            if not ds:
                ds = enriched.get("pipeline", {}).get("dataset")
            if not ds:
                continue
            if not is_dataset_available(ds, season, identity_code):
                continue

            if ds != dataset:
                continue

            if "pipeline" in enriched:
                per_entity.append(
                    {
                        "dataset": ds,
                        "params": enriched.get("params", {}),
                        "tier": tier_for_source(enriched, ds, identity_code),
                        "columns": {col_name: enriched},
                    }
                )
            elif enriched.get("tier") == "team":
                per_entity.append(
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
                league_wide.setdefault(key, {})[col_name] = enriched

    groups: List[Dict[str, Any]] = []

    for (ds, frozen_params), cols in league_wide.items():
        ds_cfg = DATASETS.get(identity_code, {}).get(ds, {})
        removed_refresh_mode = (
            "always"
            if ds_cfg.get("coverage") in ("all_seasons", "current_season")
            else "null_only"
        )
        groups.append(
            {
                "dataset": ds,
                "params": dict(frozen_params),
                "tier": tier_for_dataset(ds, identity_code),
                "columns": cols,
                "removed_refresh_mode": removed_refresh_mode,
            }
        )

    # Merge per_entity columns that share dataset + params into one group.
    per_entity_merged: Dict[str, Dict[tuple, Dict[str, Any]]] = {
        "team": {},
        "game": {},
        "player": {},
    }
    for item in per_entity:
        tier = item["tier"]
        if tier in per_entity_merged:
            params = item.get("params", {})
            key = (item["dataset"], frozenset(sorted(params.items())))
            bucket = per_entity_merged[tier].setdefault(
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

    for tier, merged in per_entity_merged.items():
        for bucket in merged.values():
            ds = bucket["dataset"]
            ds_cfg2 = DATASETS.get(identity_code, {}).get(ds, {})
            groups.append(
                {
                    "dataset": ds,
                    "params": bucket["params"],
                    "tier": tier,
                    "columns": bucket["columns"],
                    "removed_refresh_mode": (
                        "always"
                        if ds_cfg2.get("coverage") in ("all_seasons", "current_season")
                        else "null_only"
                    ),
                }
            )

    logger.debug(
        "build_call_groups: table=%s dataset=%s -> %d groups (%d league_wide, %d per_entity)",
        table_name,
        dataset,
        len(groups),
        len(league_wide),
        len(per_entity),
    )
    return groups
