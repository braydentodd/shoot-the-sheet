"""
Shoot the Sheet - League Definitions

Per-league operational settings: calendar window, retention, season grammar.

Season types are declared as ``consolidated_group -> [canonical_keys]``.
The canonical keys (e.g. ``"regular_season"``, ``"playoffs"``, ``"play_in"``,
``"showcase_cup"``) are defined in each source's config module.  The
consolidated groups (``"regular_season"`` / ``"postseason"``) are what
core stats tables store.

Example::

    "NBA": {
        "season_types": {
            "regular_season": ["regular_season"],
            "postseason":     ["playoffs", "play_in"],
        }
    }

Dataset-level role assignments and source wiring live in
:data:`src.etl.definitions.datasets.DATASETS` and
:data:`src.core.definitions.db_columns.DB_COLUMNS`.

Pure declarative data; helpers live in :mod:`src.core.lib.leagues_resolver`.
"""

from typing import Dict, List, TypedDict

# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({"same_year", "split_year"})
VALID_LEAGUE_GENDERS = frozenset({"M", "W"})
VALID_SEASON_TYPE_GROUPS = frozenset({"regular_season", "postseason"})
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


class LeagueDef(TypedDict):
    """Per-league operational configuration.

    Attributes:
        name: Full display name (e.g. "National Basketball Association").
        gender: "M" or "W" -- used for schema-level categorization.
        season_format: "split_year" (NBA-style, "2025-26") or
            "same_year" (single calendar year, "2025").
        season_types: Mapping of consolidated groups to canonical
            season-type keys.  Keys are "regular_season" / "postseason";
            values are lists of canonical type identifiers
            (e.g. ``["regular_season", "showcase_cup"]``).
        combined_season_types: Mapping of a "lead" canonical key to the
            full list of canonical keys it covers in a single API call.
            e.g. ``{"regular_season": ["regular_season", "showcase_cup"]}``
            means one call with wire_name "Regular Season" also returns
            Showcase Cup data, saving an API call for the latter.
            Leagues without combinations use an empty dict.
        calendar_flip: "MM/DD" string -- the approximate month/day when
            the off-season turns into the next season year.
        stat_rates: Which rate modes to compute (e.g. ["per_poss", "per_min"]).
        retention_seasons: Number of past seasons to keep in stats tables.
        season_detector: Dataset name (from
            :data:`src.etl.definitions.datasets.DATASETS["nba_id"]`)
            that provides game-by-game data used to check whether any
            games have been played recently (within ``GAME_LOOKBACK_DAYS``).
        team_discovery_dataset: Dataset name that provides the full list
            of active team source IDs for the current season.  Used by
            the pipeline to discover which per-team calls to make.
    """

    name: str
    gender: str
    season_format: str
    season_types: Dict[str, List[str]]
    combined_season_types: Dict[str, List[str]]
    calendar_flip: str
    stat_rates: List[str]
    retention_seasons: int
    season_detector: str
    team_discovery_dataset: str


# ============================================================================
# LEAGUE REGISTRY
# ============================================================================

LEAGUES: Dict[str, LeagueDef] = {
    "NBA": {
        "name": "National Basketball Association",
        "gender": "M",
        "season_format": "split_year",
        "season_types": {
            "regular_season": ["regular_season"],
            "postseason": ["playoffs", "play_in"],
        },
        "combined_season_types": {},
        "calendar_flip": "08/01",
        "stat_rates": ["per_poss", "per_min"],
        "retention_seasons": 6,
        "season_detector": "league_game_finder",
        "team_discovery_dataset": "team_years",
    },
    "WNBA": {
        "name": "Women's National Basketball Association",
        "gender": "W",
        "season_format": "same_year",
        "season_types": {
            "regular_season": ["regular_season"],
            "postseason": ["playoffs"],
        },
        "combined_season_types": {},
        "calendar_flip": "12/31",
        "stat_rates": ["per_poss", "per_min"],
        "retention_seasons": 6,
        "season_detector": "league_game_finder",
        "team_discovery_dataset": "team_years",
    },
    "GLG": {
        "name": "NBA G League",
        "gender": "M",
        "season_format": "split_year",
        "season_types": {
            "regular_season": ["regular_season", "showcase_cup"],
            "postseason": ["playoffs"],
        },
        "combined_season_types": {
            "regular_season": ["regular_season", "showcase_cup"],
        },
        "calendar_flip": "08/01",
        "stat_rates": ["per_poss", "per_min"],
        "retention_seasons": 6,
        "season_detector": "league_game_finder",
        "team_discovery_dataset": "team_years",
    },
}
