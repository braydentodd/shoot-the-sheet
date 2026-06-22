"""
Shoot the Sheet - League Definitions

Per-league operational settings: calendar window, retention, season grammar.

Season types are declared as ``{canonical_key: {is_postseason, min_season}}``.
The ``is_postseason`` boolean groups types for core stats table purposes.
``min_season`` gates whether a season type is valid for a given season
(e.g. Play-In started in 2020-21).

Dataset-level role assignments and source wiring live in
:data:`src.etl.definitions.datasets.DATASETS` and
:data:`src.core.definitions.db_columns.DB_COLUMNS`.

Pure declarative data; helpers live in :mod:`src.core.lib.leagues_resolver`.
"""

from typing import Dict, List, TypedDict, Union

# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({"same_year", "split_year"})
VALID_LEAGUE_GENDERS = frozenset({"M", "W"})
VALID_SEASON_TYPE_GROUPS = frozenset({"regular", "postseason"})
VALID_CANONICAL_SEASON_TYPES = frozenset(
    {
        "regular_season",
        "playoffs",
        "play_in",
        "showcase_cup",
    }
)


# ============================================================================
# SCHEMA
# ============================================================================


class SeasonTypeDef(TypedDict):
    """Per-season-type configuration within a league."""

    is_postseason: bool
    min_season: Union[str, None]


class LeagueDef(TypedDict):
    """Per-league operational configuration."""

    name: str
    gender: str
    season_format: str
    season_types: Dict[str, SeasonTypeDef]
    calendar_flip: str
    stat_rates: List[str]
    season_retention_start: str


# ============================================================================
# LEAGUE REGISTRY
# ============================================================================

LEAGUES: Dict[str, LeagueDef] = {
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
        "stat_rates": ["per_poss", "per_min"],
        "season_retention_start": "2000-01",
    },
    "WNBA": {
        "name": "Women's National Basketball Association",
        "gender": "W",
        "season_format": "same_year",
        "season_types": {
            "regular_season": {
                "is_postseason": False,
                "min_season": None,
            },
            "playoffs": {
                "is_postseason": True,
                "min_season": None,
            },
        },
        "calendar_flip": "12/31",
        "stat_rates": ["per_poss", "per_min"],
        "season_retention_start": "2000",
    },
    "GLG": {
        "name": "NBA G League",
        "gender": "M",
        "season_format": "split_year",
        "season_types": {
            "regular_season": {
                "is_postseason": False,
                "min_season": None,
            },
            "showcase_cup": {
                "is_postseason": False,
                "min_season": "2022-23",
            },
            "playoffs": {
                "is_postseason": True,
                "min_season": None,
            },
        },
        "calendar_flip": "08/01",
        "stat_rates": ["per_poss", "per_min"],
        "season_retention_start": "2001-02",
    },
}
