"""
The Glass - NBA API Source Configuration

Pure data definitions for the ``nba_api`` source: season-type mapping,
rate limits, and field-name mappings.

Dataset metadata lives in the unified registry
(:mod:`src.etl.definitions.datasets`).  This module is purely about
how to talk to the source itself.
"""

from typing import Any, Dict, TypedDict, Union

class ApiConfigDef(TypedDict):
    per_mode_simple: str
    per_mode_time: str
    per_mode_detailed: str
    last_n_games: str
    month: str
    opponent_team_id: str
    period: str

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
# API FIELD NAME MAPPINGS
# ============================================================================

API_FIELD_NAMES: Dict[str, Dict[str, Any]] = {
    'entity_id':   {'player': 'PLAYER_ID', 'team': 'TEAM_ID'},
    'entity_name': {'player': 'PLAYER_NAME', 'team': 'TEAM_NAME'},
    'special_ids': {'person': 'PERSON_ID'},
    'id_aliases':  {'PLAYER_ID': ['PERSON_ID', 'VS_PLAYER_ID']},
}