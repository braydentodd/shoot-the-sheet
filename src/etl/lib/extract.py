"""
Shoot the Sheet - ETL Extraction Engine

Source-agnostic field extraction from API responses using config-driven
source mappings.  Reads a provider's SOURCES dict and an API result dict,
and produces DB-ready {column: value} dicts per entity.

This module never calls the API directly — it only interprets the raw
JSON response that the provider client returns.
"""

import logging
from typing import Any, Dict, List, Union

from src.core.lib.math_evaluator import evaluate as eval_math_expr
from src.etl.lib.transform import apply_transform

logger = logging.getLogger(__name__)

# ============================================================================
# FIELD EXTRACTION
# ============================================================================


def extract_field(
    row: List[Any],
    headers: List[str],
    source: Dict[str, Any],
) -> Any:
    """Extract and transform a single field from an API result row.

    Args:
        row: A single row from a resultSet's rowSet.
        headers: The column headers for the result set.
        source: Source config dict with 'field', 'transform', and optional 'scale'.

    Returns:
        The transformed value, or None if the field is missing.
    """
    field = source.get("field")
    if not field:
        return None
    if field not in headers:
        logger.debug(
            "Field %r not found in API headers: %s", field, sorted(headers)[:20]
        )
        return None

    raw_value = row[headers.index(field)]

    # Reject complex types (some datasets return nested objects)
    if isinstance(raw_value, (dict, list)):
        return None

    transform_name = source.get("transform", "safe_int")
    scale = source.get("scale", 1)
    params = source.get("params")

    return apply_transform(raw_value, transform_name, scale, params)


def extract_derived_field(
    row: List[Any],
    headers: List[str],
    source: Dict[str, Any],
) -> Any:
    """Extract a derived field via concat or algebraic expression."""
    derived = source.get("derived")
    if not derived:
        return extract_field(row, headers, source)

    # String concatenation
    concat_fields = derived.get("concat")
    if concat_fields:
        separator = derived.get("separator", " ")
        parts = []
        for f in concat_fields:
            if f not in headers:
                return None
            raw = row[headers.index(f)]
            if raw is None:
                raw = ""
            parts.append(str(raw))
        value = separator.join(parts)
        if not value.strip():
            return None
        transform_name = source.get("transform", "safe_str")
        return apply_transform(value, transform_name, params=source.get("params"))

    # Numeric math
    math_expr = derived.get("math")
    if not math_expr:
        return extract_field(row, headers, source)

    fields = derived.get("fields", [])
    locals_dict = {}
    valid = True

    for field_name in fields:
        if field_name not in headers:
            valid = False
            break
        raw = row[headers.index(field_name)]
        if raw is None:
            valid = False
            break
        try:
            locals_dict[field_name] = float(raw)
        except (ValueError, TypeError):
            valid = False
            break

    if not valid:
        return None

    try:
        value = eval_math_expr(math_expr, locals_dict)
    except Exception:
        return None

    transform_name = source.get("transform", "safe_int")
    scale = source.get("scale", 1)
    return apply_transform(value, transform_name, scale, source.get("params"))


# ============================================================================
# BATCH EXTRACTION
# ============================================================================


def extract_columns_from_result(
    api_result: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    target: str,
    entity_id_field: str,
    id_aliases: Union[Dict[str, List[str]], None] = None,
) -> Dict[int, Dict[str, Any]]:
    """Extract all mapped columns from an API result for every entity.

    Columns route to resultSets via their ``result_set`` field.  Columns
    without a ``result_set`` are extracted from every resultSet that
    contains the entity ID field.

    Args:
        api_result: Raw API JSON with ``resultSets``.
        columns: ``{canonical_col_name: source_config}`` — typically a
                 subset of SOURCES filtered for a specific dataset.
        target: Table routing target (e.g. ``'player_seasons'``, ``'team_games'``).
        entity_id_field: API header name for the entity ID (e.g. 'PLAYER_ID').

    Returns:
        ``{entity_id: {col_name: value, ...}, ...}``
    """
    all_entities: Dict[int, Dict[str, Any]] = {}

    for rs in api_result.get("resultSets", []):
        headers = rs["headers"]

        # Resolve entity ID field, falling back to source-provided aliases
        id_field = entity_id_field
        if id_field not in headers:
            aliases = (id_aliases or {}).get(entity_id_field, [])
            id_field = next(
                (a for a in aliases if a in headers),
                None,
            )
            if id_field is None:
                logger.debug(
                    "Entity ID field %r not found in result set %r headers: %s",
                    entity_id_field,
                    rs.get("name"),
                    sorted(headers)[:15],
                )
                continue

        id_idx = headers.index(id_field)

        for row in rs["rowSet"]:
            entity_id = row[id_idx]
            if entity_id is None:
                continue

            existing = all_entities.setdefault(entity_id, {})
            for col_name, source in columns.items():
                # Skip columns with pipeline or multi_call sources
                if "pipeline" in source:
                    continue

                # Per-column result_set routing: skip resultSets not matching the column's result_set
                col_result_set = source.get("result_set")
                if col_result_set and rs["name"] != col_result_set:
                    continue

                if source.get("derived"):
                    val = extract_derived_field(row, headers, source)
                else:
                    val = extract_field(row, headers, source)

                # Prefer non-None values across multiple result sets
                if val is not None or col_name not in existing:
                    existing[col_name] = val

    return all_entities


# ============================================================================
# COLUMN FILTERING
# ============================================================================


def get_simple_columns(
    columns: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Filter to columns with direct field extraction."""
    return {name: src for name, src in columns.items() if "pipeline" not in src}


def get_pipeline_columns(
    columns: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Filter to columns that require a transformation pipeline."""
    return {name: src for name, src in columns.items() if "pipeline" in src}


def extract_value_from_raw_dict(
    raw_dict: Dict[str, Any],
    source: Dict[str, Any],
) -> Any:
    """Extract a single value from a raw row dict using source config.

    Handles both direct 'field' and 'derived' math expressions.
    Applies transforms and scaling just like extract_field/extract_derived_field.
    """
    derived = source.get("derived")
    if derived and derived.get("math"):
        math_expr = derived["math"]
        fields = derived.get("fields", [])
        locals_dict: Dict[str, float] = {}
        valid = True
        for field_name in fields:
            raw = raw_dict.get(field_name)
            if raw is None:
                valid = False
                break
            try:
                locals_dict[field_name] = float(raw)
            except (ValueError, TypeError):
                valid = False
                break
        if not valid:
            return None
        try:
            value = eval_math_expr(math_expr, locals_dict)
        except Exception:
            return None
        transform_name = source.get("transform", "safe_int")
        scale = source.get("scale", 1)
        return apply_transform(value, transform_name, scale, source.get("params"))

    field = source.get("field")
    if not field:
        return None
    raw_value = raw_dict.get(field)
    if isinstance(raw_value, (dict, list)):
        return None
    transform_name = source.get("transform", "safe_int")
    scale = source.get("scale", 1)
    return apply_transform(raw_value, transform_name, scale, source.get("params"))


def extract_raw_rows(
    api_result: Dict[str, Any],
    entity_id_field: str,
    result_set_name: Union[str, None] = None,
    filter_field: Union[str, None] = None,
    filter_values: Union[List[str], None] = None,
) -> Dict[int, List[Dict[str, Any]]]:
    """Extract raw row dicts from an API result, grouped by entity ID.

    Returns ``{entity_id: [row_dict, ...]}``.
    Used by team-call patterns that collect per-team rows for later aggregation.

    Optional *filter_field* and *filter_values* restrict rows to those whose
    *filter_field* value is in *filter_values*.
    """
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    accepted = set(filter_values) if filter_values else None

    for rs in api_result.get("resultSets", []):
        if result_set_name and rs["name"] != result_set_name:
            continue
        headers = rs["headers"]
        if entity_id_field not in headers:
            continue
        id_idx = headers.index(entity_id_field)
        filter_idx = (
            headers.index(filter_field)
            if filter_field and filter_field in headers
            else None
        )
        for row in rs["rowSet"]:
            if filter_idx is not None and accepted is not None:
                if row[filter_idx] not in accepted:
                    continue
            eid = row[id_idx]
            if eid is not None:
                grouped.setdefault(eid, []).append(dict(zip(headers, row)))

    return grouped
