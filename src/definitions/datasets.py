"""
Shoot the Sheet - Unified Dataset Registry

Single source of truth for all dataset definitions across every identity.

Each identity (e.g. ``nba_id``, ``internal``) has its own namespace so
dataset names only need to be unique within an identity.  Every entry
carries the same generic orchestrator-level fields plus a ``source_mapping``
dict that holds source-specific wire parameters.

Shape:

    DATASETS[identity_key][dataset_name] -> DatasetDef
    DatasetDef['source'] -> source_module_key (e.g. 'nba_api', 'shoot_the_sheet')
    DatasetDef['source_mapping'] -> SourceMappingDef

Keys in ``source_mapping`` fall into two categories:

    * **Meta-keys** — consumed by the client's parameter builder
      (class_name, result_set, season_type_param, per_mode_param,
       season_param, endpoint).
    * **Pass-through keys** — forwarded directly as API call parameters
      (e.g. pt_measure_type, measure_type_detailed_defense).

This mirrors the ``dataset_mapping`` pattern in ``db_columns.py``.
"""

from typing import Dict, List, Literal, TypedDict, Union

# ============================================================================
# TYPE ALIASES
# ============================================================================

ExecutionTierT = Literal["per_league", "per_team", "per_player", "per_game"]

CoverageT = Literal["current", "all_years", "normal"]

RowFilterOpT = Literal["lte", "gte", "eq"]


class SourceMappingDef(TypedDict, total=False):
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


class RowFilterDef(TypedDict):
    """Post-API row filter — keeps only rows matching all conditions.

    Attributes:
        field: Source field name to filter on.
        op: Comparison operator.
        value_template: Template string for value comparison (e.g. '{season_end_year}').
    """

    field: str
    op: RowFilterOpT
    value_template: str


class DatasetDef(TypedDict):
    """Generic dataset metadata, uniform across every identity.

    Attributes:
        min_season: Earliest season to fetch (None for no lower bound).
        max_season: Latest season to fetch (None for no upper bound).
        source: Source module key (e.g. 'nba_api').
        phase: ETL phase that triggers this dataset.
        coverage: Coverage level for backfill behavior.
        execution_tier: API execution level (per_league, per_team, per_player, per_game).
        source_mapping: Source-specific API parameters.
        discovery_tables: Tables to check for new entities.
        prune_tables: Tables to truncate before loading.
        row_filters: Post-fetch row filters.
    """

    min_season: Union[str, None]
    max_season: Union[str, None]
    source: str
    phase: str
    coverage: CoverageT
    execution_tier: ExecutionTierT
    source_mapping: SourceMappingDef
    discovery_tables: Union[List[str], None]
    prune_tables: Union[List[str], None]
    row_filters: Union[List[RowFilterDef], None]


DATASETS: Dict[str, Dict[str, DatasetDef]] = {
    "nba_id": {
        "recent_games": {
            "coverage": "current",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "detect_season_activity",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguegamelog",
                "season_type_param": "season_type_all_star",
            },
        },
        "leagues_teams_rosters": {
            "coverage": "current",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_leagues_teams",
            "execution_tier": "per_league",
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
            "discovery_tables": ["teams_staging", "leagues_teams_staging"],
            "prune_tables": ["leagues_teams_staging"],
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "commonteamyears",
            },
        },
        "teams_players_rosters": {
            "coverage": "current",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_teams_players",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "teams_players_staging"],
            "prune_tables": ["teams_players_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": [
                "teams_staging",
                "games_staging",
                "team_games_staging",
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
            "coverage": "normal",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": [
                "players_staging",
                "games_staging",
                "player_games_staging",
            ],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "leaguegamelog",
                "season_type_param": "season_type_all_star",
                "player_or_team_abbreviation": "P",
            },
        },
        "pbp_data": {
            "min_season": "2000-01",  # playbyplayv3 verified available from 2000-01 onward
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_pbp",
            "coverage": "normal",
            "execution_tier": "per_game",
            "row_filters": None,
            "discovery_tables": [
                "games_staging",
                "pbp_events_staging",
                "player_games_staging",
                "team_games_staging",
            ],
            "prune_tables": ["pbp_events_staging"],
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "playbyplayv3",
                "result_set": "PlayByPlay",
            },
        },
        "combine_anthros": {
            "min_season": "2000-01",
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "coverage": "all_years",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["players"],
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
            "coverage": "all_years",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["players"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "EEEE"},
                "class_name": "draftBoard",
                "season_param": "season_year",
            },
        },
        "player_profiles": {
            "coverage": "current",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "execution_tier": "per_league",
            "row_filters": None,
            "discovery_tables": ["players_staging", "countries_players_staging"],
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "playerindex",
            },
        },
        "team_profiles": {
            "coverage": "current",
            "min_season": None,
            "max_season": None,
            "source": "nba_api",
            "phase": "maintain_profiles",
            "execution_tier": "per_team",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "season_param_format": {"NBA": "SSSS-EE"},
                "class_name": "teaminfocommon",
                "season_type_param": "season_type_all_star",
            },
        },
    },
}
