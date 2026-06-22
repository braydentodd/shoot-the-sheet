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


class DatasetDef(TypedDict):
    """Generic dataset metadata, uniform across every identity."""

    min_season: Union[str, None]
    execution_tier: str
    source: str
    role: str
    coverage_mode: str
    source_mapping: SourceMappingDef


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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
            },
        },
        "team_passing_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Passing",
            },
        },
        # --- Player tracking - Possessions (since 2013-14) ---
        "player_possession_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
            },
        },
        "team_possession_stats": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "pt_measure_type": "Possessions",
            },
        },
        # --- Hustle stats (since 2015-16) ---
        "player_hustle_stats": {
            "min_season": "2016-17",
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashptteamdefend",
                "result_set": "LeagueDashPtTeamDefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
            },
        },
        # --- Player index (all-time player registry, 1 call) ---
        "player_profiles": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "profile_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "playerindex",
                "result_set": "PlayerIndex",
            },
        },
        # --- Player roster / profiles (per-team, current season) ---
        "team_player_rosters": {
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "player_discoverer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "commonteamroster",
                "result_set": "CommonTeamRoster",
            },
        },
        # --- Team discovery (all active teams, 1 call) ---
        "league_team_rosters": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "team_discoverer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "commonteamyears",
                "result_set": "TeamYears",
            },
        },
        # --- Season activity detector ---
        "recent_games": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "season_detector",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguegamefinder",
                "result_set": "LeagueGameFinderResults",
                "season_type_param": "season_type_all_star",
            },
        },
        # --- Draft combine (since 2000-01) ---
        "combine_measurements": {
            "min_season": "2000-01",
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "profile_maintainer",
            "coverage_mode": "always",
            "source_mapping": {
                "class_name": "draftcombineplayeranthro",
                "result_set": "DraftCombinePlayerAnthro",
                "season_param": "season_year",
            },
        },
        # --- On-court stats (since 2007-08) ---
        "player_on_stats": {
            "min_season": "2007-08",
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "teamplayeronoffdetails",
                "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        # --- Opponent stats (MeasureType=Opponent) ---
        "player_opp_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "leaguedashplayerstats",
                "result_set": "LeagueDashPlayerStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
                "measure_type_detailed_defense": "Opponent",
            },
        },
        "team_opp_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_league",
            "source": "nba_api",
            "role": "stats_maintainer",
            "coverage_mode": "normal",
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
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "role": "profile_maintainer",
            "coverage_mode": "normal",
            "source_mapping": {
                "class_name": "teaminfocommon",
                "result_set": "TeamInfoCommon",
                "season_type_param": "season_type_all_star",
            },
        },
    },
}
