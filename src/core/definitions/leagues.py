"""

The Glass - League Definitions

Per-league operational settings: calendar window, retention, season grammar,
and source role ownership. Pure declarative data;
helpers live in :mod:`src.core.lib.leagues`.
"""

from typing import Dict, List, TypedDict


# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({'same_year', 'split_year'})
VALID_LEAGUE_GENDERS = frozenset({'M', 'W'})
VALID_SOURCE_ROLE_KEYS = frozenset({'roster_maintainer', 'retained_discoverer'})

# ============================================================================
# SCHEMA
# ============================================================================

class SourceRoleParams(TypedDict):
    is_only_current_season: str

class SourceRoleDef(TypedDict):
    dataset: str
    team_id_field: str
    player_id_field: str
    params: SourceRoleParams

class LeagueRoles(TypedDict):
    roster_maintainer: Dict[str, SourceRoleDef]
    retained_discoverer: Dict[str, SourceRoleDef]

class LeagueDef(TypedDict):
    name: str
    abbr: str
    gender: str
    season_format: str
    regular_season_types: List[str]
    postseason_types: List[str]
    calendar_flip_md: str
    retention_seasons: int
    source_roles: LeagueRoles

LEAGUES: Dict[str, LeagueDef] = {

    'nba': {
        'name':                   'National Basketball Association',
        'abbr':                   'NBA',
        'gender':                 'M',
        'season_format':          'split_year',
        'regular_season_types':   ['rs'],
        'postseason_types':       ['po', 'pi'],
        'calendar_flip_md':       '08-01',
        'retention_seasons':      8,
        'source_roles': {
            'roster_maintainer': {
                'nba_api': {
                    'dataset': 'commonallplayers',
                    'team_id_field': 'TEAM_ID',
                    'player_id_field': 'PERSON_ID',
                    'params': {'is_only_current_season': '1'},
                },
            },
            'retained_discoverer': {
                'nba_api': {
                    'dataset': 'commonallplayers',
                    'params': {'is_only_current_season': '0'},
                    'team_id_field': 'TEAM_ID',
                    'player_id_field': 'PERSON_ID',
                }
            },
        },
    }
}
