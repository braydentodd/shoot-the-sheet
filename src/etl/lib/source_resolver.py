"""
Shoot the Sheet - Source Resolvers

Pure resolvers over :data:`src.etl.definitions.sources.SOURCES`,
:data:`src.etl.definitions.datasets.DATASETS`, and
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.sources import SOURCES, LeagueEntryDef


def get_identity_entities(identity_code: str) -> set:
    """Return the set of entities supported by an identity, derived from db_columns."""
    from src.core.definitions.db_columns import DB_COLUMNS

    entities = set()
    for col_name, col_def in DB_COLUMNS.items():
        dataset_mapping = col_def.get("dataset_mapping")
        if not dataset_mapping:
            continue
        for league_code, league_mapping in dataset_mapping.items():
            identity_mapping = league_mapping.get(identity_code, {})
            entities.update(identity_mapping.keys())
    return entities


def get_external_sources_for_league(league_code: str) -> list[str]:
    """Return sorted external source module keys available for a league."""
    from src.etl.definitions.datasets import DATASETS

    if league_code not in LEAGUES:
        raise ValueError(f"Unknown league: {league_code!r}")

    source_keys = set()
    for identity_code, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            source = ds_def.get("source")
            if source:
                source_keys.add(source)
    return sorted(source_keys)


def get_source_league_id(source_code: str, league_code: str) -> str:
    """Return the source-specific league identifier for a league/source pair."""
    entry = _get_league_entry(source_code, league_code)
    return entry["id"]


def get_default_external_source(league_code: str) -> str:
    """Return a deterministic default external source for a league."""
    sources = get_external_sources_for_league(league_code)
    if not sources:
        raise ValueError(f"League {league_code!r} has no external sources configured")
    return sources[0]


def _get_league_entry(source_code: str, league_code: str) -> "LeagueEntryDef":
    """Return the league entry dict (``{id, season_format}``)."""
    if source_code not in SOURCES:
        raise ValueError(f"Unknown source: {source_code!r}")
    if league_code not in LEAGUES:
        raise ValueError(f"Unknown league: {league_code!r}")
    leagues = SOURCES[source_code].get("leagues", {})
    if league_code not in leagues:
        raise ValueError(
            f"Source {source_code!r} does not support league {league_code!r}"
        )
    return leagues[league_code]


# ============================================================================
# SEASON TYPE RESOLVERS
# ============================================================================


def get_source_season_type_code(
    source_code: str, league_code: str, canonical_key: str
) -> str:
    """Return the source-specific parameter value for a canonical season type.

    Looks up ``SOURCES[source_code]["leagues"][league_code]["season_types"]``.
    Falls back to the canonical key if not defined.
    """
    entry = _get_league_entry(source_code, league_code)
    season_types = entry.get("season_types", {})
    return season_types.get(canonical_key, canonical_key)
