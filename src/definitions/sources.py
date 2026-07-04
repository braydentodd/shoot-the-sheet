"""
Shoot the Sheet - Source Registry

Declarative registry of every external data source.

``leagues`` maps league keys to source-specific metadata:
    - ``id``: the source's identifier for this league (e.g. ``"00"`` for NBA)
    - ``season_types``: canonical key → parameter value the source expects
      for the season_type API parameter (e.g. ``"play_in"`` → ``"PlayIn"``).

Season parameter format is declared per-dataset in
:data:`src.definitions.datasets.SourceMappingDef.season_param_format`.

All other source-specific operational settings (rate limits, API parameters,
field name mappings) live in each source's own config module under
``src/etl/sources/<source>/config.py``.

Helpers that resolve source assignments per league/entity live in
:mod:`src.lib.source_resolver`.
"""

from typing import Dict, TypedDict


class LeagueEntryDef(TypedDict):
    """Per-league configuration for a source.

    Attributes:
        id: Source-specific league identifier.
        season_types: Mapping from canonical season_type to source parameter value.
    """

    id: str
    season_types: Dict[str, str]


class SourceDef(TypedDict):
    """Complete source definition.

    Attributes:
        leagues: Mapping from league_code to league entry configuration.
    """

    leagues: Dict[str, LeagueEntryDef]


SOURCES: Dict[str, SourceDef] = {
    "nba_api": {
        "leagues": {
            "NBA": {
                "id": "00",
                "season_types": {
                    "regular_season": "Regular Season",
                    "playoffs": "Playoffs",
                    "play_in": "PlayIn",
                },
            },
        },
    }
}
