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

from typing import Dict, List, TypedDict, Union


class SourceMappingDef(TypedDict, total=False):
    """Source-specific wire parameters -- how to call the API endpoint."""

    class_name: str
    result_set: Union[str, None]
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    season_param: Union[str, None]
    endpoint: Union[str, None]

    # Pass-through — forwarded directly as API params.
    measure_type_detailed_defense: Union[str, None]
    pt_measure_type: Union[str, None]
    player_or_team: Union[str, None]


class RowFilterDef(TypedDict):
    """Post-API row filter — keeps only rows matching all conditions."""

    field: str
    op: str  # "lte" | "gte" | "eq"
    value_template: str  # "{season_end_year}" — resolved by client


class DatasetDef(TypedDict):
    """Generic dataset metadata, uniform across every identity.

    ``coverage`` drives refresh behaviour:
        ``"normal"``   — use stat_coverages to gate re-fetching (default).
        ``"all_years"`` — fetch every season from min_season to current,
                        aggregate most-recent-non-null per entity.
        ``"current"``   — skip coverage, always fetch the current season.
    """

    min_season: Union[str, None]
    execution_tier: str
    source: str
    stage: str
    coverage: str
    source_mapping: SourceMappingDef
    discovery_tables: Union[List[str], None]
    prune_tables: Union[List[str], None]
    row_filters: Union[List[RowFilterDef], None]


DATASETS: Dict[str, Dict[str, DatasetDef]] = {
    # ========================================================================
    # NBA API
    # ========================================================================
    "nba_id": {
        # --- Basic stats (since 2003-04) ---
        "player_basic_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashplayerstats",
                "result_set": "LeagueDashPlayerStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "team_basic_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashteamstats",
                "result_set": "LeagueDashTeamStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        # --- Advanced stats (MeasureType=Advanced) ---
        "player_advanced_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashplayerstats",
                "result_set": "LeagueDashPlayerStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Advanced",
            },
        },
        "team_advanced_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashteamstats",
                "result_set": "LeagueDashTeamStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Advanced",
            },
        },
        # --- Player tracking - Passing (since 2013-14) ---
        "player_passing_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
                "player_or_team": "Player",
            },
        },
        "team_passing_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
                "player_or_team": "Team",
            },
        },
        # --- Player tracking - Possessions (since 2013-14) ---
        "player_possession_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
                "player_or_team": "Player",
            },
        },
        "team_possession_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
                "player_or_team": "Team",
            },
        },
        # --- Hustle stats (since 2015-16) ---
        "player_hustle_stats": {
            "min_season": "2016-17",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguehustlestatsplayer",
                "result_set": "HustleStatsPlayer",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_time",
            },
        },
        "team_hustle_stats": {
            "min_season": "2015-16",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguehustlestatsteam",
                "result_set": "HustleStatsTeam",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_time",
            },
        },
        # --- Defensive matchup (since 2013-14) ---
        "player_defense_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptdefend",
                "result_set": "LeagueDashPtDefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
            },
        },
        "team_defense_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashptteamdefend",
                "result_set": "LeagueDashPtTeamDefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
            },
        },
        # --- Player index (all-time player registry, 1 call) ---
        "player_profiles": {
            "coverage": "current",
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "profile_maintainer",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "class_name": "playerindex",
                "result_set": "PlayerIndex",
            },
        },
        # --- Player roster / profiles (per-team, current season) ---
        "teams_players_rosters": {
            "coverage": "current",
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "teams_players_maintainer",
            "row_filters": None,
            "discovery_tables": ["players_staging", "teams_players_staging"],
            "prune_tables": ["teams_players_staging"],
            "source_mapping": {
                "class_name": "commonteamroster",
                "result_set": "CommonTeamRoster",
            },
        },
        # --- Team discovery (all active teams, 1 call) ---
        "leagues_teams_rosters": {
            "coverage": "current",
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "leagues_teams_maintainer",
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
                "class_name": "commonteamyears",
                "result_set": "TeamYears",
            },
        },
        # --- Season activity detector ---
        "recent_games": {
            "coverage": "current",
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "season_detector",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguegamelog",
                "result_set": "LeagueGameLog",
                "season_type_param": "season_type_all_star",
            },
        },
        # --- Draft combine (since 2000-01) ---
        "combine_measurements": {
            "min_season": "2000-01",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "profile_maintainer",
            "coverage": "all_years",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "class_name": "draftcombineplayeranthro",
                "result_set": "Results",
                "season_param": "season_year",
            },
        },
        # --- On-court stats (since 2007-08) ---
        "player_on_stats": {
            "min_season": "2007-08",
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["players_staging", "player_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "teamplayeronoffdetails",
                "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        # --- Team opponent stats (MeasureType=Opponent) ---
        "team_opp_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_league",
            "source": "nba_api",
            "stage": "stats_maintainer",
            "coverage": "normal",
            "row_filters": None,
            "discovery_tables": ["teams_staging", "team_seasons_staging"],
            "prune_tables": None,
            "source_mapping": {
                "class_name": "leaguedashteamstats",
                "result_set": "LeagueDashTeamStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Opponent",
            },
        },
        # --- Team info (all time) ---
        "team_profiles": {
            "coverage": "current",
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "stage": "profile_maintainer",
            "row_filters": None,
            "discovery_tables": None,
            "prune_tables": None,
            "source_mapping": {
                "class_name": "teaminfocommon",
                "result_set": "TeamInfoCommon",
                "season_type_param": "season_type_all_star",
            },
        },
    },
}
