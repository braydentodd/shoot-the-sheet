"""
Shoot the Sheet - Unified Dataset Registry

Single source of truth for all dataset definitions across every identity.

Each identity (e.g. ``nba_id``, ``internal``) has its own namespace so
dataset names only need to be unique within an identity.  Every entry
carries the same generic orchestrator-level fields plus a ``source_mapping``
dict that holds source-specific wire parameters.

Shape:

    DATASETS[identity_key][dataset_name] -> Dataset
    Dataset['source'] -> source_module_key (e.g. 'nba_api', 'shoot_the_sheet')
    Dataset['source_mapping'] -> SourceMapping

Keys in ``source_mapping`` fall into two categories:

    * **Meta-keys** — consumed by the client's parameter builder
      (class_name, result_set, season_type_param, per_mode_param,
       season_param, endpoint).
    * **Pass-through keys** — forwarded directly as API call parameters
      (e.g. pt_measure_type, measure_type_detailed_defense).

``target_tables`` is the authoritative, schema-qualified list of every
staging table a dataset writes rows into (e.g. ``"staging.teams"``),
matching ``src.definitions.schema.SCHEMAS``. The orchestrator always
derives its write targets from this field -- it must never be
hardcoded per-phase. A table appears here even when the dataset
supplies no ``db_columns.py``-mapped field for it (e.g. pure
existence/junction tables such as ``staging.leagues_teams``, or tables
whose identity/FK columns are resolved outside the generic column
mapping system, such as ``staging.games``).

``prune_tables`` is the schema-qualified list of staging tables that
should be truncated of stale rows (rows not touched by the current
run) after this dataset's fetch completes.

This mirrors the ``dataset_mapping`` pattern in ``db_columns.py``.
"""

from typing import Dict, List, Literal, TypedDict, Union

from src.definitions.pipeline import Phase

# ============================================================================
# TYPE ALIASES
# ============================================================================

ExecutionTier = Literal["per_league", "per_team", "per_player", "per_game"]

Coverage = Literal[
    "current_season", "all_seasons", "seasons_coverage", "games_coverage"
]

RowFilterOp = Literal["lte", "gte", "eq"]


class SourceMapping(TypedDict, total=False):
    """Source-specific wire parameters -- how to call the API endpoint."""

    class_name: str
    result_set: Union[str, None]
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    season_param: Union[str, None]
    season_param_format: Union[Dict[str, str], None]
    endpoint: Union[str, None]

    # Pass-through — forwarded directly as API params.
    measure_type_detailed_defense: Union[str, None]
    pt_measure_type: Union[str, None]
    player_or_team: Union[str, None]
    player_or_team_abbreviation: Union[str, None]


class RowFilter(TypedDict):
    """Post-API row filter — keeps only rows matching all conditions.

    Attributes:
        field: Source field name to filter on.
        op: Comparison operator.
        value_template: Template string for value comparison (e.g. '{season_end_year}').
    """

    field: str
    op: RowFilterOp
    value_template: str


class Dataset(TypedDict):
    """Generic dataset metadata, uniform across every identity.

    Attributes:
        min_season: Earliest season to fetch (None for no lower bound).
        max_season: Latest season to fetch (None for no upper bound).
        source: Source module key (e.g. 'nba_api').
        phase: ETL phase that triggers this dataset.
        coverage: Coverage level for backfill behavior.
        execution_tier: API execution level (per_league, per_team, per_player, per_game).
        season_type_separated: Whether the dataset returns data for one season
            type at a time (True) or all season types in one call (False).
            When True, the orchestrator calls the dataset once per season type.
            When False, it is called once and the response covers all types.
        source_mapping: Source-specific API parameters.
        target_tables: Schema-qualified staging tables this dataset writes to.
        prune_tables: Schema-qualified staging tables to truncate before loading.
        row_filters: Post-fetch row filters.
    """

    min_season: Union[str, None]
    max_season: Union[str, None]
    source: str
    phase: Phase
    coverage: Coverage
    execution_tier: ExecutionTier
    season_type_separated: bool
    source_mapping: SourceMapping
    target_tables: Union[List[str], None]
    prune_tables: Union[List[str], None]
    row_filters: Union[List[RowFilter], None]


DATASETS: Dict[str, Dict[str, Dataset]] = {
    "nba_id": {
        "league_schedule": {
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_games",
            "coverage": "games_coverage",
            "execution_tier": "per_league",
            "season_type_separated": False,
            "row_filters": None,
            "target_tables": ["staging.games"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "scheduleleaguev2",
            },
        },
        "recent_games": {
            "coverage": "current_season",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "detect_season_activity",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguegamelog",
                "season_type_param": "season_type_all_star",
            },
        },
        "leagues_teams_rosters": {
            "coverage": "current_season",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_leagues_teams",
            "execution_tier": "per_league",
            "season_type_separated": False,
            "row_filters": [
                {
                    "field": "MIN_YEAR",
                    "op": "lte",
                    "value_template": "{season_end_year}",
                },
                {
                    "field": "MAX_YEAR",
                    "op": "gte",
                    "value_template": "{season_end_year}",
                },
            ],
            "target_tables": ["staging.teams", "staging.leagues_teams"],
            "prune_tables": ["staging.leagues_teams"],
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "commonteamyears",
            },
        },
        "teams_players_rosters": {
            "coverage": "current_season",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_teams_players",
            "execution_tier": "per_team",
            "season_type_separated": False,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.teams_players"],
            "prune_tables": ["staging.teams_players"],
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "commonteamroster",
            },
        },
        "team_basic_stats": {
            "min_season": "2003-04",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashteamstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "team_advanced_stats": {
            "min_season": "2003-04",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashteamstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Advanced",
            },
        },
        "team_passing_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
                "player_or_team": "Team",
            },
        },
        "team_possession_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
                "player_or_team": "Team",
            },
        },
        "team_hustle_stats": {
            "min_season": "2015-16",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguehustlestatsplayer",
                "season_type_param": "season_type_all_star",
                "player_or_team": "Team",
                "per_mode_param": "per_mode_time",
            },
        },
        "team_defense_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptteamdefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
            },
        },
        "team_opp_stats": {
            "min_season": "2003-04",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.team_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashteamstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Opponent",
            },
        },
        "player_basic_stats": {
            "min_season": "2003-04",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashplayerstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "player_advanced_stats": {
            "min_season": "2003-04",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashplayerstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Advanced",
            },
        },
        "player_passing_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
                "player_or_team": "Player",
            },
        },
        "player_possession_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptstats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
                "player_or_team": "Player",
            },
        },
        "player_hustle_stats": {
            "min_season": "2016-17",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguehustlestatsplayer",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_time",
            },
        },
        "player_defense_stats": {
            "min_season": "2013-14",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashptdefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
            },
        },
        "player_on_stats": {
            "min_season": "2007-08",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_seasons",
            "coverage": "seasons_coverage",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.players", "staging.player_seasons"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguedashlineups",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "team_game_stats": {
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_games",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": [
                "staging.teams",
                "staging.games",
                "staging.team_games",
            ],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguegamelog",
                "season_type_param": "season_type_all_star",
                "player_or_team_abbreviation": "T",
            },
        },
        "player_game_stats": {
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_games",
            "coverage": "seasons_coverage",
            "execution_tier": "per_league",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": [
                "staging.players",
                "staging.player_games",
            ],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguegamelog",
                "season_type_param": "season_type_all_star",
                "player_or_team_abbreviation": "P",
            },
        },
        "combine_anthros": {
            "min_season": "2000-01",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "coverage": "all_seasons",
            "execution_tier": "per_league",
            "season_type_separated": False,
            "row_filters": None,
            "target_tables": ["staging.players"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "draftcombinestats",
                "season_param": "season_all_time",
            },
        },
        "draft_years": {
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "coverage": "all_seasons",
            "execution_tier": "per_league",
            "season_type_separated": False,
            "row_filters": None,
            "target_tables": ["staging.players"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "EEEE"},
                "class_name": "draftBoard",
                "season_param": "season_year",
            },
        },
        "player_profiles": {
            "coverage": "current_season",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "execution_tier": "per_league",
            "season_type_separated": False,
            "row_filters": None,
            "target_tables": [
                "staging.players",
                "staging.countries_players",
                "staging.teams_players",
            ],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "playerindex",
            },
        },
        "team_profiles": {
            "coverage": "current_season",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "execution_tier": "per_team",
            "season_type_separated": True,
            "row_filters": None,
            "target_tables": ["staging.teams", "staging.leagues_teams"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "teaminfocommon",
                "season_type_param": "season_type_all_star",
            },
        },
    },
}


# ============================================================================
# DERIVED VALUE SETS
# ============================================================================

VALID_IDENTITIES = frozenset(DATASETS.keys())
