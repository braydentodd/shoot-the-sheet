"""
Shoot the Sheet - League Definitions

Per-league operational settings: calendar window, retention, season grammar.

Season types are declared as ``{canonical_key: {is_postseason, min_season}}``.
The ``is_postseason`` boolean groups types for core stats table purposes.
``min_season`` gates whether a season type is valid for a given season
(e.g. Play-In started in 2020-21).

Dataset-level role assignments and source wiring live in
:data:`src.definitions.datasets.DATASETS` and
:data:`src.definitions.db_columns.DB_COLUMNS`.

Pure declarative data; helpers live in :mod:`src.lib.leagues_resolver`.
"""

from typing import Dict, Literal, TypedDict, Union

# ============================================================================
# SCHEMA
# ============================================================================


class SeasonType(TypedDict):
    """Per-season-type configuration within a league."""

    is_postseason: bool
    min_season: Union[str, None]


class League(TypedDict):
    """Per-league operational configuration."""

    name: str
    gender: Literal["M", "W"]
    season_format: str
    season_types: Dict[str, SeasonType]
    calendar_flip: str
    season_retention_start: str
    lineup_size: int


# ============================================================================
# LEAGUE REGISTRY
# ============================================================================

LEAGUES: Dict[str, League] = {
    "NBA": {
        "name": "National Basketball Association",
        "gender": "M",
        "season_format": "split_year",
        "season_types": {
            "regular_season": {
                "is_postseason": False,
                "min_season": None,
            },
            "playoffs": {
                "is_postseason": True,
                "min_season": None,
            },
            "play_in": {
                "is_postseason": True,
                "min_season": "2020-21",
            },
        },
        "calendar_flip": "07/01",
        "season_retention_start": "2024-25",
        "lineup_size": 5,
    },
}
