"""
The Glass - Schema Helpers

Pure resolvers over the table registries in
:mod:`src.core.definitions.schema`.  Builds qualified table names.
"""

from typing import Dict, Tuple

from src.core.definitions.schema import TABLES


def _normalize_scope(s: str) -> str:
    if not s:
        return s
    return s if s.endswith('s') else f"{s}s"


# Pre-computed O(1) lookup: {(entity, scope): (table_name, schema)}
_TABLE_BY_ENTITY_SCOPE: Dict[Tuple[str, str], Tuple[str, str]] = {}
for _name, _meta in TABLES.items():
    _entity = _meta.get('entity')
    _scope = _meta.get('scope')
    if _entity and _scope:
        _TABLE_BY_ENTITY_SCOPE[(_entity, _scope)] = (_name, _meta['schema'])


def get_table_name(entity: str, scope: str, _league_key: str = None) -> str:
    """Resolve the schema-qualified table name for an entity / scope."""
    norm_scope = _normalize_scope(scope)
    key = (entity, norm_scope)

    if key not in _TABLE_BY_ENTITY_SCOPE:
        raise ValueError(f"No table for entity {entity!r} scope {scope!r}")

    table_name, schema = _TABLE_BY_ENTITY_SCOPE[key]
    if not schema:
        raise ValueError(f"No schema defined for entity {entity!r} scope {scope!r}")
    return f"{schema}.{table_name}"
