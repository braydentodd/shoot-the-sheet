"""
The Glass - Source Resolvers

Pure resolvers over :data:`src.etl.definitions.sources.SOURCES` and the
per-league source-role assignments in
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from typing import Any, Dict

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.sources import SOURCES


def get_role_config(league_key: str, role: str) -> Dict[str, Any]:
    """Return the config object for a league source role."""
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    league_cfg = LEAGUES[league_key]
    role_map = league_cfg.get('source_roles')
    if not isinstance(role_map, dict):
        raise ValueError(f"League {league_key!r} has invalid source_roles config")

    role_cfg = role_map.get(role)
    if not isinstance(role_cfg, dict):
        raise ValueError(f"League {league_key!r} has no source role {role!r} configured")

    return role_cfg


def get_source_for_role(league_key: str, role: str) -> str:
    """Return the source key assigned to a league source role."""
    role_cfg = get_role_config(league_key, role)
    
    if not role_cfg:
        raise ValueError(f"League {league_key!r} role {role!r} is configured with an empty dict")
        
    source_key = list(role_cfg.keys())[0]

    if source_key not in SOURCES:
        raise ValueError(
            f"League {league_key!r} role {role!r} source {source_key!r} is not in SOURCES"
        )

    source_meta = SOURCES[source_key]
    if not source_meta.get('external'):
        raise ValueError(
            f"Source {source_key!r} configured for role {role!r} in {league_key!r} "
            'has external=False'
        )
    if league_key not in source_meta.get('leagues', []):
        raise ValueError(
            f"Source {source_key!r} configured for role {role!r} in {league_key!r} "
            f"does not list {league_key!r} in its leagues"
        )

    return source_key


def get_source_id_column(source_key: str) -> str:
    """Return the configured source identity column for profile tables."""
    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key!r}")

    id_column = SOURCES[source_key].get('id_column')
    if not id_column:
        raise ValueError(f"Source {source_key!r} has no configured id_column")
    return id_column


def get_external_sources_for_league(league_key: str) -> list[str]:
    """Return sorted external source keys available for a league."""
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    sources = [
        source_key
        for source_key, meta in SOURCES.items()
        if meta.get('external') and league_key in meta.get('leagues', [])
    ]
    return sorted(sources)


def get_default_external_source(league_key: str) -> str:
    """Return a deterministic default external source for a league."""
    sources = get_external_sources_for_league(league_key)
    if not sources:
        raise ValueError(
            f"League {league_key!r} has no external sources configured"
        )
    return sources[0]


# ============================================================================
# ROSTER FIELD EXTRACTOR
# ============================================================================

def get_rosters_fields(league_key: str, source_key: str) -> Dict[str, str]:
    """Extract rosters-scoped column field mappings for a league/source.
    
    Returns a dict of column_name -> source_field_name for all columns with
    'rosters' in their scope and a dataset_mapping for the given league/source.
    
    Example:
        get_rosters_fields('nba', 'nba_api') returns
        {'jersey_num': 'JERSEY', 'seasons_exp': 'SEASON_EXP'}
    
    Args:
        league_key: League identifier (e.g. 'nba')
        source_key: Source system identifier (e.g. 'nba_api')
    
    Returns:
        Dict mapping column names to their source field names, or empty dict
        if the league/source has no rosters-scoped columns.
    """
    from src.core.definitions.db_columns import DB_COLUMNS
    result = {}
    
    for col_name, col_def in DB_COLUMNS.items():
        scope = col_def.get('scope', [])
        if 'rosters' not in scope:
            continue
            
        dataset_mapping = col_def.get('dataset_mapping')
        if not dataset_mapping:
            continue
            
        # Navigate: league -> source -> entity -> {dataset, field}
        league_mapping = dataset_mapping.get(league_key, {})
        source_mapping = league_mapping.get(source_key, {})
        
        # For rosters, we typically only have 'player' entity
        player_mapping = source_mapping.get('player')
        if player_mapping:
            field = player_mapping.get('field')
            if field:
                result[col_name] = field
    
    return result
