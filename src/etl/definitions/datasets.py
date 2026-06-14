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

This mirrors the ``dataset_mapping`` pattern in ``db_columns.py``.
"""

from typing import Any, Dict, List, TypedDict, Union


class DomainDef(TypedDict, total=False):
    """Per-dataset stat domain configuration.

    ``name`` is the domain identifier (``"base"``, ``"tracking"``, etc.).
    ``minutes_present`` / ``possessions_present`` indicate which denominator
    columns this dataset provides beyond the base ``mins_x10`` / ``poss``.
    """

    name: str
    minutes_present: bool
    possessions_present: bool


class SourceMappingDef(TypedDict, total=False):
    """Source-specific wire parameters -- how to call the API endpoint."""

    class_name: str
    result_set: Union[str, None]
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    requires_params: Union[List[str], None]
    season_param: Union[str, None]
    endpoint: Union[str, None]


class DatasetDef(TypedDict):
    """Generic dataset metadata, uniform across every identity."""

    min_season: Union[str, None]
    execution_tier: str
    source: str
    domain: Union[DomainDef, None]
    source_mapping: SourceMappingDef


DATASETS: Dict[str, Dict[str, DatasetDef]] = {
    # ========================================================================
    # NBA API
    # ========================================================================
    "nba_id": {
        # --- Basic stats (since 2003-04) ---
        "player_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_team",
            "source": "nba_api",
            "domain": {"name": "base"},
            "source_mapping": {
                "class_name": "leaguedashplayerstats",
                "result_set": "LeagueDashPlayerStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "team_stats": {
            "min_season": "2003-04",
            "execution_tier": "per_league",
            "source": "nba_api",
            "domain": {"name": "base"},
            "source_mapping": {
                "class_name": "leaguedashteamstats",
                "result_set": "LeagueDashTeamStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        # --- Player tracking (since 2013-14) ---
        "player_tracking": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "domain": {"name": "tracking", "minutes_present": True, "possessions_present": False},
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "requires_params": ["pt_measure_type"],
            },
        },
        "team_tracking": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "domain": {"name": "tracking", "minutes_present": True, "possessions_present": False},
            "source_mapping": {
                "class_name": "leaguedashptstats",
                "result_set": "LeagueDashPtStats",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "requires_params": ["pt_measure_type"],
            },
        },
        # --- Hustle stats (since 2015-16) ---
        "player_hustle": {
            "min_season": "2015-16",
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "leaguehustlestatsplayer",
                "result_set": "HustleStatsPlayer",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_time",
            },
        },
        "team_hustle": {
            "min_season": "2015-16",
            "execution_tier": "per_league",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "leaguehustlestatsteam",
                "result_set": "HustleStatsTeam",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_time",
            },
        },
        # --- Defensive matchup (since 2013-14) ---
        "player_defense": {
            "min_season": "2013-14",
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "leaguedashptdefend",
                "result_set": "LeagueDashPtDefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "requires_params": ["defense_category"],
            },
        },
        "team_defense": {
            "min_season": "2013-14",
            "execution_tier": "per_league",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "leaguedashptteamdefend",
                "result_set": "LeagueDashPtTeamDefend",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_simple",
                "requires_params": ["defense_category"],
            },
        },
        # --- Player roster / profiles (per-team, current season) ---
        "team_roster": {
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "commonteamroster",
                "result_set": "CommonTeamRoster",
            },
        },
        # --- Team discovery (all active teams, 1 call) ---
        "team_years": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "commonteamyears",
                "result_set": "TeamYears",
            },
        },
        # --- Draft combine (since 2000-01) ---
        "combine_anthro": {
            "min_season": "2000-01",
            "execution_tier": "per_league",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "draftcombineplayeranthro",
                "result_set": "DraftCombinePlayerAnthro",
                "season_param": "season_year",
            },
        },
        # --- On/Off court (since 2007-08) ---
        "player_on_court": {
            "min_season": "2007-08",
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "teamplayeronoffdetails",
                "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        "player_off_court": {
            "min_season": "2007-08",
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "teamplayeronoffdetails",
                "result_set": "PlayersOffCourtTeamPlayerOnOffDetails",
                "season_type_param": "season_type_all_star",
                "per_mode_param": "per_mode_detailed",
            },
        },
        # --- Team info (all time) ---
        "team_info": {
            "min_season": None,
            "execution_tier": "per_team",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "teaminfocommon",
                "result_set": "TeamInfoCommon",
                "season_type_param": "season_type_all_star",
            },
        },
        "team_totals": {
            "min_season": "2000-01",
            "execution_tier": "per_league",
            "source": "pbp_stats",
            "source_mapping": {
                "result_set": "PbpTotals",
                "endpoint": "get-totals",
            },
        },
        "player_totals": {
            "min_season": "2000-01",
            "execution_tier": "per_team",
            "source": "pbp_stats",
            "source_mapping": {
                "result_set": "PbpTotals",
                "endpoint": "get-totals",
            },
        },
        # --- Activity / game detection (all seasons) ---
        "league_game_finder": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "nba_api",
            "source_mapping": {
                "class_name": "leaguegamefinder",
                "result_set": "LeagueGameFinderResults",
                "season_type_param": "season_type_all_star",
            },
        },
    },
    # ========================================================================
    # Shoot the Sheet
    # ========================================================================
    "sts_id": {
        "players": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "shoot_the_sheet",
            "source_mapping": {},
        },
        "teams": {
            "min_season": None,
            "execution_tier": "per_league",
            "source": "shoot_the_sheet",
            "source_mapping": {},
        },
    },
}
