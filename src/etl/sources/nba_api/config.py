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
    virtual: bool
    season_param: str

class SeasonTypeDef(TypedDict):
    name: str
    param: str
    min_season: Union[str, None]

SEASON_TYPES: Dict[str, SeasonTypeDef] = {

    'rs': {
        'name':       'Regular Season',
        'param':      'Regular Season',
        'min_season': None,
    },
    'po': {
        'name':       'Playoffs',
        'param':      'Playoffs',
        'min_season': None,
    },
    'pi': {
        'name':       'PlayIn',
        'param':      'PlayIn',
        'min_season': '2020-21',
    },
}


# ============================================================================
# API OPERATIONAL SETTINGS
# ============================================================================

# NBA-specific API parameters (not rate limiting)
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
    },
    'leaguedashteamstats': {
        'min_season': '2003-04',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashTeamStats',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['team'],
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
    },

    # --- Hustle stats (since 2015-16) ---

    'leaguehustlestatsplayer': {
        'min_season': '2015-16',
        'execution_tier': 'per_team',
        'default_result_set': 'HustleStatsPlayer',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_time',
        'entity_types': ['player'],
    },
    'leaguehustlestatsteam': {
        'min_season': '2015-16',
        'execution_tier': 'per_league',
        'default_result_set': 'HustleStatsTeam',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_time',
        'entity_types': ['team'],
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
    },
    'leaguedashptteamdefend': {
        'min_season': '2013-14',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashPtTeamDefend',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'requires_params': ['defense_category'],
        'entity_types': ['team'],
    },

    # --- Shot tracking league-wide (since 2013-14) ---

    'leaguedashplayerptshot': {
        'min_season': '2013-14',
        'execution_tier': 'per_team',
        'default_result_set': 'LeagueDashPTShots',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'entity_types': ['player'],
    },
    'leaguedashteamptshot': {
        'min_season': '2013-14',
        'execution_tier': 'per_league',
        'default_result_set': 'LeagueDashPTShots',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'entity_types': ['team'],
    },

    # --- Rebound tracking (since 2013-14) ---

    'playerdashptreb': {
        'min_season': '2013-14',
        'execution_tier': 'per_player',
        'default_result_set': 'OverallRebounding',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'entity_types': ['player'],
    },
    'teamdashptreb': {
        'min_season': '2013-14',
        'execution_tier': 'per_team',
        'default_result_set': 'OverallRebounding',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_simple',
        'entity_types': ['team'],
    },

    # --- Shooting splits (since 2012-13) ---

    'playerdashboardbyshootingsplits': {
        'min_season': '2012-13',
        'execution_tier': 'per_player',
        'default_result_set': 'ShotTypePlayerDashboard',
        'season_type_param': 'season_type_playoffs',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
    },
    'teamdashboardbyshootingsplits': {
        'min_season': '2012-13',
        'execution_tier': 'per_league',
        'default_result_set': 'ShotTypeTeamDashboard',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['team'],
    },

    # --- Player info (all time) ---

    'commonallplayers': {
        'min_season': None,
        'execution_tier': 'per_league',
        'default_result_set': 'CommonAllPlayers',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
    },

    'commonplayerinfo': {
        'min_season': None,
        'execution_tier': 'per_player',
        'default_result_set': 'CommonPlayerInfo',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
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
    },

    # --- On/Off court (since 2007-08) ---

    'teamplayeronoffsummary': {
        'min_season': '2007-08',
        'execution_tier': 'per_league',
        'default_result_set': 'PlayersOffCourtTeamPlayerOnOffSummary',
        'season_type_param': 'season_type_all_star',
        'per_mode_param': 'per_mode_detailed',
        'entity_types': ['player'],
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
        'virtual': True,
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


# ============================================================================
# VALIDATION SCHEMAS  (co-located with the config they describe)
# ============================================================================


