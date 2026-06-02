"""
The Glass - Call Group Builder

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
from src.core.lib.tables_resolver import get_table_name, TABLE_ENTITY

logger = logging.getLogger(__name__)


# ============================================================================
# MODULE-LEVEL PRE-INDEXED COLUMN REGISTRIES
# ============================================================================

# Index for get_all_sources_for_entity: {entity_type: [(col_name, col_meta), ...]}
_COLUMNS_BY_ENTITY: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
# Index for build_call_groups: {table_name: [(col_name, col_meta), ...]}
_COLUMNS_BY_TABLE: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}

for col_name, col_meta in DB_COLUMNS.items():
    tables = col_meta.get('tables', [])
    if isinstance(tables, str):
        tables = [tables]

    entities = set()
    for t in tables:
        if t == 'all':
            entities.update({'league', 'player', 'team', 'country'})
        else:
            ent = TABLE_ENTITY.get(t)
            if ent:
                entities.add(ent)

    for ent in entities:
        _COLUMNS_BY_ENTITY.setdefault(ent, []).append((col_name, col_meta))

    for t in tables:
        if t == 'all':
            for known_table in TABLE_ENTITY.keys():
                _COLUMNS_BY_TABLE.setdefault(known_table, []).append((col_name, col_meta))
        else:
            _COLUMNS_BY_TABLE.setdefault(t, []).append((col_name, col_meta))


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _enrich_source(source: Dict[str, Any], col_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Add a default transform to a source based on column type if not already set."""
    enriched = {**source}
    if 'transform' not in enriched and 'pipeline' not in enriched:
        base_type = col_meta.get('type', '').split('(')[0]
        enriched['transform'] = DEFAULT_TYPE_TRANSFORMS.get(base_type, 'safe_int')
    if 'removed_refresh_mode' not in enriched:
        enriched['removed_refresh_mode'] = col_meta.get('removed_refresh_mode', 'null_only')
    return enriched


def _get_source_definition(
    col_meta: Dict[str, Any],
    entity: str,
    source_key: str,
    league_key: str,
) -> Union[Dict[str, Any], None]:
    """Resolve per-entity source definition for a column.

    Expected ``dataset_mapping`` shape:
        ``sources[league_key][source_key][entity]``
    """
    all_sources = col_meta.get('dataset_mapping') or {}
    league_sources = all_sources.get(league_key)
    if not isinstance(league_sources, dict):
        return None
    provider_sources = league_sources.get(source_key)
    if not isinstance(provider_sources, dict):
        return None
    return provider_sources.get(entity)



# ============================================================================
# DATASET AVAILABILITY
# ============================================================================

def is_dataset_available(
    dataset_name: str,
    season: str,
    datasets: Dict[str, Dict[str, Any]],
) -> bool:
    """Check whether a dataset has data for the given season."""
    ds = datasets.get(dataset_name)
    if not ds:
        return False
    min_season = ds.get('min_season')
    if min_season is None:
        return True
    return season >= min_season


# ============================================================================
# COLUMN QUERIES
# ============================================================================

def get_columns_for_dataset(
    dataset_name: str,
    entity: str,
    source_key: str,
    params: Union[Dict[str, Any], None] = None,
    league_key: Union[str, None] = None,
) -> Dict[str, Dict[str, Any]]:
    """Find all columns whose source definition maps to the given dataset.

    Returns ``{col_name: enriched_source_dict}`` with default transforms injected.
    """
    matched: Dict[str, Dict[str, Any]] = {}
    matched_cols = _COLUMNS_BY_ENTITY.get(entity, [])

    for col_name, col_meta in matched_cols:
        source = _get_source_definition(
            col_meta, entity, source_key, league_key=league_key,
        )
        if not source:
            continue

        ds = source.get('dataset')
        if not ds:
            ds = source.get('pipeline', {}).get('dataset')
        if ds != dataset_name:
            continue

        if params:
            source_params = source.get('params', {})
            if not all(source_params.get(k) == v for k, v in params.items()):
                continue

        matched[col_name] = _enrich_source(source, col_meta)

    return matched


def get_all_sources_for_entity(
    entity: str,
    source_key: str,
    datasets: Dict[str, Dict[str, Any]],
    season: Union[str, None] = None,
    league_key: Union[str, None] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return every column with a source definition for the given entity.

    If ``season`` is provided, excludes datasets not available for that season.
    """
    matched: Dict[str, Dict[str, Any]] = {}
    matched_cols = _COLUMNS_BY_ENTITY.get(entity, [])

    for col_name, col_meta in matched_cols:
        source = _get_source_definition(
            col_meta, entity, source_key, league_key=league_key,
        )
        if not source:
            continue

        if season:
            ds = source.get('dataset') or source.get('pipeline', {}).get('dataset', '')
            if not is_dataset_available(ds, season, datasets):
                continue

        matched[col_name] = _enrich_source(source, col_meta)

    return matched


# ============================================================================
# EXECUTION TIER RESOLUTION
# ============================================================================

def tier_for_dataset(
    dataset: str,
    datasets: Dict[str, Dict[str, Any]],
) -> str:
    """Get the default execution tier for a dataset."""
    return datasets.get(dataset, {}).get('execution_tier', 'per_league')


def tier_for_source(
    source: Dict[str, Any],
    dataset: str,
    datasets: Dict[str, Dict[str, Any]],
) -> str:
    """Resolve execution tier from a source config or the dataset default."""
    tier = source.get('tier')
    if tier:
        return tier
    pipeline = source.get('pipeline', {})
    if pipeline.get('tier'):
        return pipeline['tier']
    return tier_for_dataset(dataset, datasets)


# ============================================================================
# CALL GROUP BUILDING
# ============================================================================

def build_call_groups(
    entity: str,
    season: str,
    source_key: str,
    datasets: Dict[str, Dict[str, Any]],
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
        dataset, params, tier, extraction_mode, columns ({col_name: enriched_source})
    """
    simple_groups: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
    special: List[Dict[str, Any]] = []

    if scope:
        table_name = get_table_name(entity, scope).split('.', 1)[1]
        matched_cols = _COLUMNS_BY_TABLE.get(table_name, [])
    else:
        matched_cols = _COLUMNS_BY_ENTITY.get(entity, [])

    for col_name, col_meta in matched_cols:
        # Filter in_season_source columns during off-season
        manager = col_meta.get('manager', 'perennial_source')
        if not in_season and manager == 'in_season_source':
            continue

        source = _get_source_definition(
            col_meta, entity, source_key, league_key=league_key,
        )
        if not source:
            continue

        enriched = _enrich_source(source, col_meta)

        ds = enriched.get('dataset')
        if not ds:
            ds = enriched.get('pipeline', {}).get('dataset')
        if not ds:
            continue
        if not is_dataset_available(ds, season, datasets):
            continue

        if 'pipeline' in enriched:
            special.append({
                'dataset': ds,
                'params': enriched.get('params', {}),
                'tier': tier_for_source(enriched, ds, datasets),
                'extraction_mode': datasets.get(ds, {}).get('extraction_mode', 'standard'),
                'columns': {col_name: enriched},
            })
        elif enriched.get('tier') == 'per_team':
            special.append({
                'dataset': ds,
                'params': enriched.get('params', {}),
                'tier': enriched.get('tier'),
                'extraction_mode': datasets.get(ds, {}).get('extraction_mode', 'standard'),
                'columns': {col_name: enriched},
            })
        else:
            params = enriched.get('params', {})
            key = (ds, frozenset(sorted(params.items())))
            simple_groups.setdefault(key, {})[col_name] = enriched

    groups: List[Dict[str, Any]] = []

    for (ds, frozen_params), cols in simple_groups.items():
        removed_refresh_mode = 'always' if any(
            src.get('removed_refresh_mode') == 'always' for src in cols.values()
        ) else 'null_only'
        groups.append({
            'dataset': ds,
            'params': dict(frozen_params),
            'tier': tier_for_dataset(ds, datasets),
            'extraction_mode': datasets.get(ds, {}).get('extraction_mode', 'standard'),
            'columns': cols,
            'removed_refresh_mode': removed_refresh_mode,
        })

    # Merge special-tier columns that share dataset + params into one group.
    special_merged: Dict[str, Dict[tuple, Dict[str, Any]]] = {
        'per_team': {},
    }
    for item in special:
        tier = item['tier']
        if tier in special_merged:
            params = item.get('params', {})
            key = (item['dataset'], frozenset(sorted(params.items())))
            bucket = special_merged[tier].setdefault(
                key,
                {
                    'dataset': item['dataset'],
                    'params': params,
                    'columns': {},
                },
            )
            bucket['columns'].update(item['columns'])
        else:
            groups.append(item)

    for tier, merged in special_merged.items():
        for bucket in merged.values():
            ds = bucket['dataset']
            groups.append({
                'dataset': ds,
                'params': bucket['params'],
                'tier': tier,
                'extraction_mode': datasets.get(ds, {}).get('extraction_mode', 'standard'),
                'columns': bucket['columns'],
                'removed_refresh_mode': 'null_only',
            })

    return groups
