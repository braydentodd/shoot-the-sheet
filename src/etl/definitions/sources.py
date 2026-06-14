"""
Shoot the Sheet - Source Registry

Declarative registry of every external data source.

``leagues`` maps league keys to source-specific metadata:
    - ``id``: the source's identifier for this league (e.g. ``"00"`` for NBA)
    - ``season_param_format``: the wire token format this source uses for season
      parameters (e.g. ``"SSSS-EE"`` for "2025-26", ``"EEEE"`` for "2026").

All other source-specific operational settings (rate limits, season types,
API parameters, field name mappings) live in each source's own config
module under ``src/etl/sources/<source>/config.py``.

Helpers that resolve source assignments per league/entity live in
:mod:`src.etl.lib.source_resolver`.
"""

from typing import Dict, TypedDict


class LeagueEntryDef(TypedDict):
    id: str
    season_param_format: str


class SourceDef(TypedDict):
    leagues: Dict[str, LeagueEntryDef]


SOURCES: Dict[str, SourceDef] = {
    "nba_api": {
        "leagues": {
            "NBA": {"id": "00", "season_param_format": "SSSS-EE"},
            "WNBA": {"id": "10", "season_param_format": "EEEE"},
            "GLG": {"id": "20", "season_param_format": "SSSS-EE"},
        },
    },
    "pbp_stats": {
        "leagues": {
            "NBA": {"id": "nba", "season_param_format": "SSSS-EE"},
            "WNBA": {"id": "wnba", "season_param_format": "EEEE"},
        },
    },
    "shoot_the_sheet": {
        "leagues": {
            "NBA": {"id": "nba", "season_param_format": "SSSS-EE"},
            "WNBA": {"id": "wnba", "season_param_format": "EEEE"},
            "GLG": {"id": "gleague", "season_param_format": "SSSS-EE"},
        },
    },
}
