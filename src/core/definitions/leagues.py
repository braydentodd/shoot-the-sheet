"""
The Glass - League Definitions

Per-league operational settings: calendar window, retention, season grammar,
and source role ownership. Pure declarative data;
helpers live in :mod:`src.core.lib.leagues`.
"""

from typing import Any, Dict


# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({'same_year', 'split_year'})
VALID_LEAGUE_GENDERS = frozenset({'M', 'W'})
VALID_SOURCE_ROLE_KEYS = frozenset({'roster_maintainer', 'retained_discoverer'})


# ============================================================================
# SCHEMA
# ============================================================================


LEAGUES_SCHEMA: Dict[str, Dict[str, Any]] = {
    'name':                   {'required': True, 'types': (str,)},
    'abbr':                   {'required': True, 'types': (str,)},
    'gender':                 {'required': True, 'types': (str,), 'allowed_values': VALID_LEAGUE_GENDERS},
    'season_format':          {'required': True, 'types': (str,), 'allowed_values': VALID_LEAGUE_SEASON_FORMATS},
    'regular_season_types':   {'required': True, 'types': (list,)},
    'postseason_types':       {'required': True, 'types': (list,)},
    'calendar_flip_md':       {'required': True, 'types': (str,)},
    'retention_seasons':      {'required': True, 'types': (int,)},
    'source_roles':           {'required': True, 'types': (dict,)},
}

LEAGUES: Dict[str, Dict[str, Any]] = {
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
                    'jersey_field': 'JERSEY',
                    'params': {'is_only_current_season': '1'},
                },
            },
            'retained_discoverer': {
                'nba_api': {
                    'dataset': 'commonallplayers',
                    'params': {'is_only_current_season': '0'},
                    'team_id_field': 'TEAM_ID',
                    'player_id_field': 'PERSON_ID',
                    'jersey_field': 'JERSEY',
                }
            },
        },
    }
}
