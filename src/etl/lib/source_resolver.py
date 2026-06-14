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


def get_source_entities(source_key: str) -> set:
    """Return the set of entities supported by a source module, derived from datasets.

    Derives from DATASETS by looking up which identities use this source module.
    """
    from src.etl.definitions.datasets import DATASETS

    entities = set()
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            if ds_def.get("source") == source_key:
                # Determine entities from dataset tier or we could inspect db_columns.
                # For now, infer from dataset name prefixes as a heuristic.
                ds_name_lower = ds_name.lower()
                if "player" in ds_name_lower:
                    entities.add("player")
                if "team" in ds_name_lower:
                    entities.add("team")
    return entities


def get_source_id_column(source_key: str) -> str:
    """Return the source identity column name.

    In the identity-based system, staging tables use the generic ``source_id``
    column and the ``source`` column stores the identity key.  Profile tables
    no longer maintain per-source identity columns; use
    ``identities_entities`` for resolution.

    This function is retained for backward compatibility during the migration.
    """
    return "source_id"


def get_external_identities_for_league(league_key: str) -> list[str]:
    """Return sorted external identity keys available for a league.

    An identity is external if any of its datasets use a source other than
    the internal ``shoot_the_sheet`` source.
    """
    from src.etl.definitions.datasets import DATASETS

    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    identities = []
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            source = ds_def.get("source")
            if source and source != "shoot_the_sheet":
                identities.append(identity_key)
                break
    return sorted(set(identities))


def get_external_sources_for_league(league_key: str) -> list[str]:
    """Return sorted external source module keys available for a league."""
    from src.etl.definitions.datasets import DATASETS

    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")

    source_keys = set()
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            source = ds_def.get("source")
            if source and source != "shoot_the_sheet":
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
# ROSTER FIELD EXTRACTOR
# ============================================================================


def build_source_id_columns() -> Dict[str, List[Tuple[str, str]]]:
    """Return ``{entity: [(col_name, pg_type), ...]}`` for all external sources.

    In the identity-based system, profile tables no longer carry per-source
    identity columns.  This returns an empty dict.
    """
    return {}


def get_rosters_fields(league_key: str, identity_key: str) -> Dict[str, str]:
    """Extract roster column field mappings for a league/identity.

    Returns a dict of column_name -> source_field_name for all columns whose
    ``tables`` includes ``teams_players`` and that have a dataset_mapping for
    the given league/identity.

    Example:
        get_rosters_fields('NBA', 'nba_id') returns
        {'jersey_num': 'JERSEY', 'seasons_exp': 'SEASON_EXP'}

    Args:
        league_key: League identifier (e.g. 'NBA')
        identity_key: Identity key (e.g. 'nba_id')

    Returns:
        Dict mapping column names to their source field names, or empty dict
        if the league/identity has no roster-scoped columns.
    """
    from src.core.definitions.db_columns import DB_COLUMNS

    result = {}

    for col_name, col_def in DB_COLUMNS.items():
        tables = col_def.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        if "teams_players" not in tables:
            continue

        dataset_mapping = col_def.get("dataset_mapping")
        if not dataset_mapping:
            continue

        # Navigate: league -> identity -> entity -> {dataset, field}
        league_mapping = dataset_mapping.get(league_key, {})
        identity_mapping = league_mapping.get(identity_key, {})

        # For rosters, we typically only have 'player' entity
        player_mapping = identity_mapping.get("player")
        if player_mapping:
            field = player_mapping.get("field")
            if field:
                result[col_name] = field

    return result


# ============================================================================
# SEASON TYPE RESOLVERS
# ============================================================================


def get_season_type_wire_name(source_key: str, canonical_key: str) -> str:
    """Return the API wire name for a canonical season type key.

    Looks up the source's ``SEASON_TYPES[canonical_key]["wire_name"]``.
    Falls back to the canonical key if the source doesn't define it.

    Example:
        get_season_type_wire_name('nba_api', 'regular_season') -> 'Regular Season'
        get_season_type_wire_name('pbp_stats', 'play_in') -> 'Play In Tournament'
    """
    from src.etl.sources.registry import get_source_modules

    config_mod, _ = get_source_modules(source_key)
    if not config_mod or not hasattr(config_mod, "SEASON_TYPES"):
        return canonical_key
    st = config_mod.SEASON_TYPES.get(canonical_key, {})
    return st.get("wire_name", canonical_key)


def get_season_types_for_source(source_key: str) -> Dict[str, str]:
    """Return all canonical -> wire_name mappings for a source."""
    from src.etl.sources.registry import get_source_modules

    config_mod, _ = get_source_modules(source_key)
    result = {}
    if config_mod and hasattr(config_mod, "SEASON_TYPES"):
        for key, cfg in config_mod.SEASON_TYPES.items():
            result[key] = cfg.get("wire_name", key)
    return result
