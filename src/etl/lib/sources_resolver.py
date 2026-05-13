"""
The Glass - Source Resolvers

Pure resolvers over :data:`src.etl.definitions.sources.SOURCES` and the
per-league primary-source assignment in
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.sources import SOURCES


def get_primary_source(league_key: str) -> str:
    """Return the registry key of the primary source assigned to ``league_key``.

    The primary source is the first source run for a league.  It owns the
    external IDs (e.g. NBA Stats PERSON_ID) and is responsible for defining
    the current team rosters.

    Raises:
        ValueError: if the league has no primary_source configured, the
                    key is not registered, or the registered source is not external.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    source_key = LEAGUES[league_key].get('primary_source')
    if not source_key:
        raise ValueError(f"League {league_key!r} has no primary_source configured")

    if source_key not in SOURCES:
        raise ValueError(
            f"League {league_key!r} primary_source {source_key!r} is not in SOURCES"
        )
    if not SOURCES[source_key]['external']:
        raise ValueError(
            f"Source {source_key!r} configured as primary_source for "
            f"{league_key!r} has external=False"
        )
    return source_key


def get_source_id_column(source_key: str) -> str:
    """Return the per-source identity column name for profile tables.

    Convention: ``{source_key}_id`` (e.g. ``nba_api_id``).
    """
    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key!r}")
    return f'{source_key}_id'
