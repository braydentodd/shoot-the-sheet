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


# Hard-coded primary (entity, scope) -> table mapping.
# Must be explicit because multiple tables can share the same entity and
# schema (e.g. teams_players and countries_players both map to
# entity='player', schema='rosters').  get_table_name resolves the
# primary table for each combination.
_TABLE_BY_ENTITY_SCOPE: Dict[Tuple[str, str], Tuple[str, str]] = {
    ('league', 'profiles'): ('leagues', 'profiles'),
    ('team', 'profiles'): ('teams', 'profiles'),
    ('player', 'profiles'): ('players', 'profiles'),
    ('country', 'profiles'): ('countries', 'profiles'),
    ('team', 'staging'): ('unmatched_teams', 'staging'),
    ('player', 'staging'): ('unmatched_players', 'staging'),
    ('team', 'rosters'): ('leagues_teams', 'rosters'),
    ('player', 'rosters'): ('teams_players', 'rosters'),
    ('team', 'stats'): ('team_seasons', 'stats'),
    ('player', 'stats'): ('player_seasons', 'stats'),
    ('coverage', 'ops'): ('coverages', 'ops'),
    ('run', 'ops'): ('runs', 'ops'),
    ('task', 'ops'): ('tasks', 'ops'),
}


# Single source of truth for table -> entity relationships.
TABLE_ENTITY: Dict[str, str] = {
    table_name: meta['entity'] for table_name, meta in TABLES.items()
}


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
