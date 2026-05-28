"""
The Glass - NBA API Source Configuration

Pure data definitions for the ``nba_api`` source: dataset metadata,
rate limits, season-type mapping, and field-name mappings.

League-level concerns (current season, retention window, calendar flip)
live in :mod:`src.core.definitions.leagues.LEAGUES` -- this module is
purely about how to talk to the source itself.

Validation is folded into :func:`src.etl.config_validation._validate_nba_api`.
"""

from typing import Any, Dict, TypedDict, List, Union

class ApiConfigDef(TypedDict):
    league_id: str
    per_mode_simple: str
    per_mode_time: str
    per_mode_detailed: str
    last_n_games: str
    month: str
    opponent_team_id: str
    period: str
    
class DatasetDef(TypedDict):
    min_season: Union[str, None]
    execution_tier: str
    default_result_set: str
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    entity_types: List[str]
    requires_params: List[str]
    dataset_type: str
    season_param: str

class SeasonTypeDef(TypedDict):
    name: str
    min_season: Union[str, None]

SEASON_TYPES: Dict[str, SeasonTypeDef] = {

    'rs': {
        'name':       'Regular Season',
        'min_season': None,
    },
    'po': {
        'name':       'Playoffs',
        'min_season': None,
    },
    'pi': {
        'name':       'PlayIn',
        'min_season': '2020-21',
    },
}


# ============================================================================
# API OPERATIONAL SETTINGS
# ============================================================================

REQUEST_HEADERS: Dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Host": "stats.nba.com",
    "Origin": "https://www.nba.com",
    "Pragma": "no-cache",
    "Referer": "https://stats.nba.com/",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# NBA-specific API parameters
API_CONFIG: ApiConfigDef = {
    'league_id': '00',
    'per_mode_simple': 'Totals',
    'per_mode_time': 'Totals',
    'per_mode_detailed': 'Totals',
    'last_n_games': '0',
    'month': '0',
    'opponent_team_id': '0',
    'period': '0',
}


# ============================================================================
# DATASET DEFINITIONS
# ============================================================================

DATASETS: Dict[str, DatasetDef] = {

    # --- Basic stats (since 2003-04) ---

    'leaguedashplayerstats': {
        'min_season': '2003-04',
        'execution_tier': 'per_team',
        'default_result_set': 'LeagueDashPlayerStats',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },
    'leaguedashteamstats': {
        'min_season': '2003-04',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashTeamStats',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['team'],
        'dataset_type': 'api_endpoint',
    },

    # --- Player tracking (since 2013-14) ---

    'leaguedashptstats': {
        'min_season': '2013-14',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashPtStats',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'requires_params': ['pt_measure_type'],
        'entity_types': ['player', 'team'],
        'dataset_type': 'api_endpoint',
    },

    # --- Hustle stats (since 2015-16) ---

    'leaguehustlestatsplayer': {
        'min_season': '2015-16',
        'execution_tier': 'per_team',
        'default_result_set': 'HustleStatsPlayer',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_time',
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },
    'leaguehustlestatsteam': {
        'min_season': '2015-16',
        'execution_tier': 'per_league',
        'default_result_set': 'HustleStatsTeam',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_time',
        'entity_types': ['team'],
        'dataset_type': 'api_endpoint',
    },

    # --- Defensive matchup (since 2013-14) ---

    'leaguedashptdefend': {
        'min_season': '2013-14',
        'execution_tier': 'per_team',
        'default_result_set': 'LeagueDashPtDefend',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'requires_params': ['defense_category'],
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },
    'leaguedashptteamdefend': {
        'min_season': '2013-14',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashPtTeamDefend',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'requires_params': ['defense_category'],
        'entity_types': ['team'],
        'dataset_type': 'api_endpoint',
    },

    # --- Shooting splits (since 2012-13) ---

    'playerdashboardbyshootingsplits': {
        'min_season': '2012-13',
        'execution_tier': 'per_player',
        'default_result_set': 'ShotTypePlayerDashboard',
        'season_type_param': 'season_type_playoffs',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },
    'teamdashboardbyshootingsplits': {
        'min_season': '2012-13',
        'execution_tier': 'per_league',
        'default_result_set': 'ShotTypeTeamDashboard',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['team'],
        'dataset_type': 'api_endpoint',
    },

    # --- Player info (all time) ---

    'commonallplayers': {
        'min_season': None,
        'execution_tier': 'per_league',
        'default_result_set': 'CommonAllPlayers',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },

    # --- Draft combine (since 2000-01) ---

    'draftcombineplayeranthro': {
        'min_season': '2000-01',
        'execution_tier': 'per_league',
        'default_result_set': 'DraftCombinePlayerAnthro',
        'season_param': 'season_year',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },

    # --- On/Off court (since 2007-08) ---

    'teamplayeronoffsummary': {
        'min_season': '2007-08',
        'execution_tier': 'per_league',
        'default_result_set': 'PlayersOffCourtTeamPlayerOnOffSummary',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },
    'teamplayeronoffdetails': {
        'min_season': '2007-08',
        'execution_tier': 'per_league',
        'default_result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
        'dataset_type': 'api_endpoint',
    },

    # --- Virtual: team metadata (abbreviation + conference) ---
    # Combines nba_api static teams data with LeagueStandings.
    # No real NBA API class — handled by fetch_team_metadata() in client.py.

    'team_metadata': {
        'min_season': None,
        'execution_tier': 'per_league',
        'default_result_set': 'TeamMetadata',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['team'],
        'dataset_type': 'virtual',
    },
}


# ============================================================================
# API FIELD NAME MAPPINGS
# ============================================================================

API_FIELD_NAMES: Dict[str, Dict[str, Any]] = {
    'entity_id':   {'player': 'PLAYER_ID', 'team': 'TEAM_ID'},
    'entity_name': {'player': 'PLAYER_NAME', 'team': 'TEAM_NAME'},
    'special_ids': {'person': 'PERSON_ID'},
    'id_aliases':  {'PLAYER_ID': ['PERSON_ID']},
}