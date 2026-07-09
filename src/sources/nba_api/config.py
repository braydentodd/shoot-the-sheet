"""
Shoot the Sheet - NBA API Source Configuration

Pure data definitions for the ``nba_api`` source: season-type mapping,
rate limits, and field-name mappings.

Season types use canonical keys (e.g. ``regular_season``, ``playoffs``,
``play_in``) that are shared across sources.  Each entry carries a
``wire_name`` (what the API expects as the parameter value) and an
optional ``min_season`` (earliest season this type is valid for).

Dataset metadata lives in the unified registry
(:mod:`src.definitions.datasets`).  This module is purely about
how to talk to the source itself.
"""

from typing import Any, Dict, TypedDict


class ApiConfigDef(TypedDict):
    per_mode_simple: str
    per_mode_time: str
    per_mode_detailed: str
    last_n_games: str
    month: str
    opponent_team_id: str
    period: str


# ============================================================================
# API CONFIGURATION
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
    "per_mode_simple": "Totals",
    "per_mode_time": "Totals",
    "per_mode_detailed": "Totals",
    "last_n_games": "0",
    "month": "0",
    "opponent_team_id": "0",
    "period": "0",
}


# ============================================================================
# API FIELD NAME MAPPINGS
# ============================================================================

API_FIELD_NAMES: Dict[str, Dict[str, Any]] = {
    "target_id": {
        "players": "PLAYER_ID",
        "player_seasons": "PLAYER_ID",
        "player_games": "PLAYER_ID",
        "teams_players": "PLAYER_ID",
        "countries_players": "PLAYER_ID",
        "teams": "TEAM_ID",
        "team_seasons": "TEAM_ID",
        "team_games": "TEAM_ID",
        "leagues_teams": "TEAM_ID",
        "games": "GAME_ID",
    },
    "id_aliases": {
        "PLAYER_ID": ["PERSON_ID", "VS_PLAYER_ID", "personId"],
        "TEAM_ID": ["teamId"],
    },
}
