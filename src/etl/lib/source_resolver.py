"""
Shoot the Sheet - Source Resolvers

Pure resolvers over :data:`src.etl.definitions.sources.SOURCES`,
:data:`src.etl.definitions.datasets.DATASETS`, and
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from typing import Dict, List, Tuple

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.sources import SOURCES


def get_identity_entities(identity_key: str) -> set:
    """Return the set of entities supported by an identity, derived from db_columns."""
    from src.core.definitions.db_columns import DB_COLUMNS

    entities = set()
    for col_name, col_def in DB_COLUMNS.items():
        dataset_mapping = col_def.get("dataset_mapping")
        if not dataset_mapping:
            continue
        for league_key, league_mapping in dataset_mapping.items():
            identity_mapping = league_mapping.get(identity_key, {})
            entities.update(identity_mapping.keys())
    return entities


def get_source_id_column(source_key: str) -> str:
    """Return the source identity column name."""
    return "source_id"


def get_external_sources_for_league(league_key: str) -> list[str]:
    """Return sorted external source module keys available for a league."""
    from src.etl.definitions.datasets import DATASETS

    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    source_keys = set()
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            source = ds_def.get("source")
            if source:
                source_keys.add(source)
    return sorted(source_keys)


def get_source_league_id(source_key: str, league_key: str) -> str:
    """Return the source-specific league identifier for a league/source pair."""
    entry = _get_league_entry(source_key, league_key)
    return entry["id"]


def get_source_league_season_param_format(source_key: str, league_key: str) -> str:
    """Return the wire season token format for a league/source pair.

    e.g. ``"SSSS-EE"`` for NBA on nba_api, ``"EEEE"`` for WNBA on nba_api.
    """
    entry = _get_league_entry(source_key, league_key)
    return entry["season_param_format"]


def _get_league_entry(source_key: str, league_key: str) -> dict:
    """Return the league entry dict (``{id, season_format}``)."""
    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key!r}")
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")
    leagues = SOURCES[source_key].get("leagues", {})
    if league_key not in leagues:
        raise ValueError(
            f"Source {source_key!r} does not support league {league_key!r}"
        )
    return leagues[league_key]


def get_default_external_source(league_key: str) -> str:
    """Return a deterministic default external source for a league."""
    sources = get_external_sources_for_league(league_key)
    if not sources:
        raise ValueError(f"League {league_key!r} has no external sources configured")
    return sources[0]


# ============================================================================
# SEASON TYPE RESOLVERS
# ============================================================================


def get_season_type_wire_name(source_key: str, canonical_key: str) -> str:
    """Return the API wire name for a canonical season type key.

    Looks up the source's ``SEASON_TYPES[canonical_key]["wire_name"]``.
    Falls back to the canonical key if the source doesn't define it.
    """
    from src.etl.sources.registry import get_source_modules

    config_mod, _ = get_source_modules(source_key)
    if not config_mod or not hasattr(config_mod, "SEASON_TYPES"):
        return canonical_key
    st = config_mod.SEASON_TYPES.get(canonical_key, {})
    return st.get("wire_name", canonical_key)
