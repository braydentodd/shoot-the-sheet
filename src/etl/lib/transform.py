"""
The Glass - ETL Transform Module

Source-agnostic type converters and transformation pipeline engine.
Type converters turn raw API values into DB-ready values.
The pipeline engine executes multi-step transformations defined in config.
"""

import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Literal, Union

logger = logging.getLogger(__name__)


# ============================================================================
# TYPE CONVERTERS
# ============================================================================

def safe_int(value: Any, scale: int = 1) -> Union[int, None]:
    """Convert value to scaled integer, returning None for unparseable input."""
    if value is None:
        return None
    try:
        return round(float(value) * scale)
    except (ValueError, TypeError):
        return None


def safe_str(value: Any) -> Union[str, None]:
    """Safely convert to string, returning None for empty/NaN."""
    if value is None or value == '':
        return None
    try:
        if isinstance(value, float) and value != value:  # NaN check
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def null_if_zero(value: Any) -> Union[int, None]:
    """Return None for 0/empty values; otherwise safe_int."""
    if value is None or value == '' or str(value).lower() == 'nan':
        return None
    try:
        if int(float(value)) == 0:
            return None
    except (ValueError, TypeError):
        return None
    return safe_int(value)


def parse_height(height_str: Any) -> Union[int, None]:
    """Parse height string (e.g. '6-10') to total inches. Returns None on failure."""
    if not height_str or height_str == '' or height_str == 'None':
        return None
    try:
        s = str(height_str)
        if '-' in s:
            feet, inches = s.split('-')
            return int(feet) * 12 + int(inches)
        return int(float(s)) if s else None
    except (ValueError, AttributeError):
        return None


def parse_birthdate(date_str: Any) -> Union[date, None]:
    """Parse birthdate string to date object. Tries multiple formats."""
    if not date_str or date_str == '' or str(date_str).lower() == 'nan':
        return None
    raw = str(date_str).split('.')[0]  # strip fractional seconds
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def format_season(from_year: Any) -> Union[str, None]:
    """Convert FROM_YEAR (e.g. 2012) to season string (e.g. '2012-13')."""
    if from_year is None or from_year == '' or str(from_year).lower() == 'nan':
        return None
    try:
        year = int(from_year)
        return f"{year}-{str(year + 1)[-2:]}"
    except (ValueError, TypeError):
        return None


# ============================================================================
# TRANSFORM DISPATCH
# ============================================================================

TRANSFORMS: Dict[str, Callable] = {
    'safe_int': safe_int,
    'safe_str': safe_str,
    'null_if_zero': null_if_zero,
    'parse_height': parse_height,
    'parse_birthdate': parse_birthdate,
    'format_season': format_season,
}


def apply_transform(value: Any, transform_name: str, scale: int = 1) -> Any:
    """Apply a named transform to a value.

    For safe_int the *scale* argument is forwarded; all other transforms
    ignore it.
    """
    func = TRANSFORMS.get(transform_name)
    if func is None:
        raise ValueError(f"Unknown transform: {transform_name}")
    if transform_name == 'safe_int':
        return func(value, scale=scale)
    return func(value)


# ============================================================================
# PIPELINE ENGINE
# ============================================================================
# Executes multi-step transformation pipelines defined declaratively in
# provider config SOURCES entries.  Each pipeline is a list of operations
# applied sequentially to API response data.
#
# Supported operation types:
#   extract            – pull field(s) from a result set, keyed by entity ID
#   multi_league_extract – make multiple API calls and merge results
#   filter             – keep only rows matching filter criteria
#   aggregate          – reduce per-entity lists to single values (sum, avg, etc.)
#   multiply           – multiply two extracted fields per entity
#   math               – perform arithmetic on extracted fields

def execute_pipeline(
    pipeline_config: Dict[str, Any],
    api_fetcher: Callable,
    entity: Literal['player', 'team'],
    season: str,
    season_type_name: str,
    entity_id_field: str,
    default_entity_id: Any = None,
) -> Dict[int, Any]:
    """Execute a transformation pipeline and return ``{entity_id: value}``.

    Args:
        pipeline_config: The ``transformation`` dict from a SOURCES entry.
        api_fetcher: Callable ``(dataset, params, execution_tier) -> raw_result``
            that handles the actual API call (provided by the runner).
        entity: 'player' or 'team'.
        season: Season string.
        season_type_name: e.g. 'Regular Season'.
        entity_id_field: API header name for the entity's ID
            (e.g. 'PLAYER_ID', 'TEAM_ID').

    Returns:
        Dict mapping entity ID to the final computed value.
    """
    dataset = pipeline_config['dataset']
    execution_tier = pipeline_config.get('tier', 'per_league')
    operations = pipeline_config['operations']
    dataset_params = pipeline_config.get('params', {})

    # Determine if any operation needs API data
    needs_api = operations[0].get('type') == 'extract'

    api_result = None
    if needs_api:
        api_result = api_fetcher(dataset, dataset_params, execution_tier)

    data: Dict[int, Any] = {}
    for op in operations:
        op_type = op['type']
        if op_type == 'extract':
            data = _op_extract(api_result, op, entity_id_field, default_entity_id)
        elif op_type == 'multi_league_extract':
            data = _op_multi_league_extract(op, api_fetcher, dataset, entity_id_field, season, season_type_name)
        elif op_type == 'filter':
            data = _op_filter(data, op)
        elif op_type == 'aggregate':
            data = _op_aggregate(data, op)
        elif op_type == 'math':
            data = _op_math(data, op)
        else:
            raise ValueError(f"Unknown pipeline operation: {op_type}")

    return data


# ============================================================================
# PIPELINE OPERATIONS (private)
# ============================================================================

def _op_extract(
    api_result: Dict[str, Any],
    op: Dict[str, Any],
    entity_id_field: str,
    default_entity_id: Any = None,
) -> Dict[int, Any]:
    """Extract a field from a specific result set, keyed by entity ID.

    Supports optional ``filter_field`` / ``filter_values`` to keep only
    matching rows, and ``fields`` (dict) for multi-field extraction.
    """
    target_rs = op.get('result_set')
    id_field = entity_id_field

    for rs in api_result.get('resultSets', []):
        if target_rs and rs['name'] != target_rs:
            continue

        headers = rs['headers']
        id_idx = headers.index(id_field) if id_field in headers else None
        
        if id_idx is None and default_entity_id is None:
            continue
        rows = rs['rowSet']

        # Optional row-level filter
        filter_field = op.get('filter_field')
        filter_values = op.get('filter_values')

        # Multi-field extraction (for multiply pipelines)
        if 'fields' in op:
            result: Dict[int, Dict[str, Any]] = {}
            field_map = op['fields']  # {alias: api_field}
            for row in rows:
                if filter_field and filter_values:
                    if filter_field in headers and row[headers.index(filter_field)] not in filter_values:
                        continue
                eid = row[id_idx] if id_idx is not None else default_entity_id
                entry = result.setdefault(eid, {alias: [] for alias in field_map})
                for alias, api_field in field_map.items():
                    if api_field in headers:
                        entry[alias].append(row[headers.index(api_field)])
            return result

        # Single-field extraction
        field = op['field']
        if field not in headers:
            return {}
        field_idx = headers.index(field)

        result = {}
        for row in rows:
            if filter_field and filter_values:
                if filter_field in headers and row[headers.index(filter_field)] not in filter_values:
                    continue
            eid = row[id_idx] if id_idx is not None else default_entity_id
            val = row[field_idx]
            if eid in result:
                # Multiple matching rows — accumulate in a list for later aggregation
                existing = result[eid]
                if isinstance(existing, list):
                    existing.append(val)
                else:
                    result[eid] = [existing, val]
            else:
                result[eid] = val
        return result

    return {}


def _op_multi_league_extract(
    op: Dict[str, Any],
    api_fetcher: Callable,
    base_dataset: str,
    entity_id_field: str,
    season: str,
    season_type_name: str,
) -> Dict[int, Any]:
    """Make multiple API calls with different params and sum results per entity."""
    field = op['field']
    result_set = op.get('result_set')
    calls = op['calls']
    id_field = entity_id_field

    totals: Dict[int, int] = {}

    for call_params in calls:
        api_result = api_fetcher(base_dataset, call_params, 'per_league')
        for rs in api_result.get('resultSets', []):
            if result_set and rs['name'] != result_set:
                continue
            headers = rs['headers']
            if id_field not in headers or field not in headers:
                continue
            id_idx = headers.index(id_field)
            field_idx = headers.index(field)
            for row in rs['rowSet']:
                eid = row[id_idx]
                val = safe_int(row[field_idx])
                if val is not None:
                    totals[eid] = totals.get(eid, 0) + val
            break

    return totals


def _op_filter(data: Dict[int, Any], op: Dict[str, Any]) -> Dict[int, Any]:
    """Keep only entries matching filter criteria."""
    values = set(op['values'])
    return {eid: v for eid, v in data.items() if v in values}


def _op_aggregate(data: Dict[int, Any], op: Dict[str, Any]) -> Dict[int, Any]:
    """Reduce list values to a single value per entity."""
    method = op.get('method', 'sum')
    result = {}
    for eid, val in data.items():
        if isinstance(val, list):
            nums = [v for v in val if v is not None]
            if method == 'sum':
                result[eid] = sum(safe_int(v) or 0 for v in nums)
            elif method == 'avg':
                result[eid] = round(sum(float(v) for v in nums) / len(nums)) if nums else None
            else:
                raise ValueError(f"Unknown aggregate method: {method}")
        else:
            result[eid] = safe_int(val) if val is not None else None
    return result






def _op_math(data: Dict[int, Any], op: Dict[str, Any]) -> Dict[int, Any]:
    """Perform arithmetic on extracted fields. Uses eval() with limited variables."""
    expression = op['expression']
    should_round = op.get('round', True)
    result = {}
    
    for eid, field_data in data.items():
        if not isinstance(field_data, dict):
            continue
            
        # Extract first element from lists
        locals_dict = {}
        valid = True
        for k, v in field_data.items():
            val = v[0] if isinstance(v, list) and v else v
            if val is None:
                valid = False
                break
            locals_dict[k] = float(val)
            
        if not valid:
            result[eid] = None
            continue
            
        try:
            val = eval(expression, {"__builtins__": {}}, locals_dict)
            result[eid] = round(val) if should_round else val
        except Exception:
            result[eid] = None
            
    return result


# ============================================================================
# MULTI-SEASON AGGREGATION
# ============================================================================

def aggregate_multi_season_most_recent_non_null(values_by_year: Dict[int, Any]) -> Any:
    """Return most recent non-null value from year-ordered dict.
    
    Args:
        values_by_year: Dict mapping year -> value
        
    Returns:
        Most recent non-null value, or None if all values are null
    """
    if not values_by_year:
        return None
    
    for year in reversed(sorted(values_by_year.keys())):
        value = values_by_year[year]
        if value is not None:
            return value
    return None


# ============================================================================
# PER-TEAM AGGREGATION (used by team_call pattern)
# ============================================================================

DEFAULT_MINUTES_FIELD = 'MIN'


def _aggregate_per_team(
    raw_rows: List[Dict[str, Any]],
    columns: Dict[str, Dict[str, Any]],
    minutes_field: Union[str, None] = None,
) -> Dict[str, Any]:
    """Aggregate a list of raw API rows into one dict of column values.

    Supports ``sum`` (default) and ``minute_weighted`` aggregation modes
    configured via ``source['aggregation']``.
    """
    minutes_field = minutes_field or DEFAULT_MINUTES_FIELD
    total_minutes = sum(float(r.get(minutes_field) or 0) for r in raw_rows)
    values: Dict[str, Any] = {}

    for col_name, source in columns.items():
        nba_field = source.get('field')
        scale = source.get('scale', 1)
        transform_name = source.get('transform', 'safe_int')
        aggregation = source.get('aggregation', 'sum')

        if aggregation == 'minute_weighted' and total_minutes > 0:
            weighted_sum = 0.0
            for r in raw_rows:
                val = r.get(nba_field)
                mins = float(r.get(minutes_field) or 0)
                if val is not None and mins > 0:
                    weighted_sum += float(val) * mins
            raw = weighted_sum / total_minutes
        else:
            raw = sum(float(r.get(nba_field) or 0) for r in raw_rows)

        values[col_name] = apply_transform(raw, transform_name, scale)

    return values
