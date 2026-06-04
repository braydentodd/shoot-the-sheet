"""
The Glass - Source Resolvers

Pure resolvers over :data:`src.etl.definitions.sources.SOURCES` and
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from typing import Any, Dict, List, Tuple

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.datasets import get_source_entities
from src.etl.definitions.sources import SOURCES


def get_source_id_column(source_key: str) -> str:
    """Return the configured source identity column for profile tables."""
    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key!r}")

    external_id = SOURCES[source_key].get('external_id')
    if not external_id:
        raise ValueError(f"Source {source_key!r} has no configured external_id")
    return external_id


def get_external_sources_for_league(league_key: str) -> list[str]:
    """Return sorted external source keys available for a league."""
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    sources = [
        source_key
        for source_key, meta in SOURCES.items()
        if meta.get('external_id') is not None and league_key in meta.get('leagues', {})
    ]
    return sorted(sources)


def get_source_league_id(source_key: str, league_key: str) -> str:
    """Return the source-specific league identifier for a league/source pair."""
    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key!r}")
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")
    leagues = SOURCES[source_key].get('leagues', {})
    if league_key not in leagues:
        raise ValueError(
            f"Source {source_key!r} does not support league {league_key!r}"
        )
    return leagues[league_key]


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

def build_source_id_columns() -> Dict[str, List[Tuple[str, str]]]:
    """Return ``{entity: [(col_name, pg_type), ...]}`` for all external sources.

    Used by :func:`src.core.lib.ddl.bootstrap_schema` to know which
    per-source identity columns to add to profile tables.
    """
    result: Dict[str, List[Tuple[str, str]]] = {}
    seen: Dict[str, set] = {}
    for source_key, meta in sorted(SOURCES.items()):
        if meta.get('id_type') is None:
            continue
        if meta.get('external_id') is None:
            continue
        col_name = get_source_id_column(source_key)
        for entity in get_source_entities(source_key):
            seen.setdefault(entity, set())
            if col_name in seen[entity]:
                continue
            seen[entity].add(col_name)
            result.setdefault(entity, []).append((col_name, meta['id_type']))
    return result


def get_rosters_fields(league_key: str, source_key: str) -> Dict[str, str]:
    """Extract roster column field mappings for a league/source.

    Returns a dict of column_name -> source_field_name for all columns whose
    ``tables`` includes ``teams_players`` and that have a dataset_mapping for
    the given league/source.

    Example:
        get_rosters_fields('nba', 'nba_api') returns
        {'jersey_num': 'JERSEY', 'seasons_exp': 'SEASON_EXP'}

    Args:
        league_key: League identifier (e.g. 'nba')
        source_key: Source system identifier (e.g. 'nba_api')

    Returns:
        Dict mapping column names to their source field names, or empty dict
        if the league/source has no roster-scoped columns.
    """
    from src.core.definitions.db_columns import DB_COLUMNS
    result = {}

    for col_name, col_def in DB_COLUMNS.items():
        tables = col_def.get('tables', [])
        if isinstance(tables, str):
            tables = [tables]
        if 'teams_players' not in tables:
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
