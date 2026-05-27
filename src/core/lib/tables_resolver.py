"""
The Glass - Schema Helpers

Pure resolvers over the table registries in
:mod:`src.core.definitions.tables`.  Builds qualified table names.
"""

from src.core.definitions.tables import CORE_SCHEMA, TABLES


def _normalize_scope(s: str) -> str:
    if not s:
        return s
    return s if s.endswith('s') else f"{s}s"


def get_table_name(entity: str, scope: str, league_key: str = None) -> str:
    """Resolve the schema-qualified table name for an entity / scope.

    ``scope == 'profiles'`` -> ``core.{entity}_profiles`` (league_key ignored).
    ``scope == 'stats'``  -> ``{league_key}.{entity}_season_stats`` (league_key required).
    """
    norm_scope = _normalize_scope(scope)

    candidates = []
    for name, meta in TABLES.items():
        meta_scope = _normalize_scope(meta.get('scope') or '')
        if meta.get('entity') != entity:
            continue
        if meta_scope != norm_scope:
            continue
        candidates.append((name, meta))

    if not candidates:
        raise ValueError(f"No table for entity {entity!r} scope {scope!r}")
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous table resolution for entity {entity!r} scope {scope!r}")

    name, meta = candidates[0]
    schema = meta.get('schema') or 'core'
    if schema == 'league':
        if not league_key:
            raise ValueError(f"league_key required for scope {scope!r} (entity {entity!r})")
        return f"{league_key}.{name}"
    if schema == 'core':
        return f"{CORE_SCHEMA}.{name}"
    return f"{schema}.{name}"
