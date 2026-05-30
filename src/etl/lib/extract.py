"""
The Glass - ETL Extraction Engine

Source-agnostic field extraction from API responses using config-driven
source mappings.  Reads a provider's SOURCES dict and an API result dict,
and produces DB-ready {column: value} dicts per entity.

This module never calls the API directly — it only interprets the raw
JSON response that the provider client returns.
"""

import logging
from typing import Any, Dict, List, Literal, Union

from src.etl.lib.transform import apply_transform


import ast
import operator

logger = logging.getLogger(__name__)

_AST_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_math_expr(expr: str, variables: Dict[str, float]) -> float:
    """Safely evaluate a mathematical expression using AST parsing.

    Only allows basic arithmetic operations and variables.
    """
    node = ast.parse(expr, mode='eval')

    def _eval(node_to_eval):
        if isinstance(node_to_eval, ast.Expression):
            return _eval(node_to_eval.body)
        elif isinstance(node_to_eval, ast.Constant):
            if isinstance(node_to_eval.value, (int, float)):
                return node_to_eval.value
            raise TypeError(f"Unsupported constant type in math expression: {type(node_to_eval.value)}")
        elif isinstance(node_to_eval, ast.Num):  # for python < 3.8
            return node_to_eval.n
        elif isinstance(node_to_eval, ast.Name):
            if node_to_eval.id in variables:
                return variables[node_to_eval.id]
            raise NameError(f"Undefined variable in math expression: {node_to_eval.id}")
        elif isinstance(node_to_eval, ast.BinOp):
            op_type = type(node_to_eval.op)
            if op_type in _AST_OPERATORS:
                return _AST_OPERATORS[op_type](_eval(node_to_eval.left), _eval(node_to_eval.right))
            raise TypeError(f"Unsupported binary operator: {op_type}")
        elif isinstance(node_to_eval, ast.UnaryOp):
            op_type = type(node_to_eval.op)
            if op_type in _AST_OPERATORS:
                return _AST_OPERATORS[op_type](_eval(node_to_eval.operand))
            raise TypeError(f"Unsupported unary operator: {op_type}")
        else:
            raise TypeError(f"Unsupported AST node type in math expression: {type(node_to_eval)}")

    return _eval(node)

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
    field = source.get('field')
    if not field or field not in headers:
        return None

    raw_value = row[headers.index(field)]

    # Reject complex types (some datasets return nested objects)
    if isinstance(raw_value, (dict, list)):
        return None

    transform_name = source.get('transform', 'safe_int')
    scale = source.get('scale', 1)

    return apply_transform(raw_value, transform_name, scale)


def extract_derived_field(
    row: List[Any],
    headers: List[str],
    source: Dict[str, Any],
) -> Any:
    """Extract a derived field via algebraic expression interpolation."""
    derived = source.get('derived')
    if not derived:
        return extract_field(row, headers, source)

    math_expr = derived.get('math')
    if not math_expr:
        return extract_field(row, headers, source)

    fields = derived.get('fields', [])
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
        value = _eval_math_expr(math_expr, locals_dict)
    except Exception:
        return None

    transform_name = source.get('transform', 'safe_int')
    scale = source.get('scale', 1)
    return apply_transform(value, transform_name, scale)


# ============================================================================
# BATCH EXTRACTION
# ============================================================================

def extract_columns_from_result(
    api_result: Dict[str, Any],
    columns: Dict[str, Dict[str, Any]],
    entity: Literal['player', 'team'],
    entity_id_field: str,
    result_set_name: Union[str, None] = None,
    id_aliases: Union[Dict[str, List[str]], None] = None,
) -> Dict[int, Dict[str, Any]]:
    """Extract all mapped columns from an API result for every entity.

    Args:
        api_result: Raw API JSON with ``resultSets``.
        columns: ``{canonical_col_name: source_config}`` — typically a
                 subset of SOURCES filtered for a specific dataset.
        entity: 'player' or 'team'.
        entity_id_field: API header name for the entity ID (e.g. 'PLAYER_ID').
        result_set_name: If given, only process this result set.

    Returns:
        ``{entity_id: {col_name: value, ...}, ...}``
    """
    all_entities: Dict[int, Dict[str, Any]] = {}

    for rs in api_result.get('resultSets', []):
        if result_set_name and rs['name'] != result_set_name:
            continue

        headers = rs['headers']

        # Resolve entity ID field, falling back to source-provided aliases
        id_field = entity_id_field
        if id_field not in headers:
            aliases = (id_aliases or {}).get(entity_id_field, [])
            id_field = next(
                (a for a in aliases if a in headers),
                None,
            )
            if id_field is None:
                continue

        id_idx = headers.index(id_field)

        for row in rs['rowSet']:
            entity_id = row[id_idx]
            if entity_id is None:
                continue

            existing = all_entities.setdefault(entity_id, {})
            for col_name, source in columns.items():
                # Skip columns with pipeline or multi_call sources
                if 'pipeline' in source:
                    continue

                if source.get('derived'):
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
    return {
        name: src for name, src in columns.items()
        if 'pipeline' not in src
    }


def get_pipeline_columns(
    columns: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Filter to columns that require a transformation pipeline."""
    return {
        name: src for name, src in columns.items()
        if 'pipeline' in src
    }


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

    for rs in api_result.get('resultSets', []):
        if result_set_name and rs['name'] != result_set_name:
            continue
        headers = rs['headers']
        if entity_id_field not in headers:
            continue
        id_idx = headers.index(entity_id_field)
        filter_idx = headers.index(filter_field) if filter_field and filter_field in headers else None
        for row in rs['rowSet']:
            if filter_idx is not None and accepted is not None:
                if row[filter_idx] not in accepted:
                    continue
            eid = row[id_idx]
            if eid is not None:
                grouped.setdefault(eid, []).append(dict(zip(headers, row)))

    return grouped

