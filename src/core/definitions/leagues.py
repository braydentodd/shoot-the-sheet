"""
The Glass - League Definitions

Per-league operational settings: calendar window, retention, season grammar,
and the authoritative source that owns external IDs.  Pure declarative data;
helpers live in :mod:`src.core.lib.leagues`.
"""

from typing import Any, Dict


# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({'same_year', 'split_year'})


# ============================================================================
# SCHEMA
# ============================================================================


LEAGUES_SCHEMA: Dict[str, Dict[str, Any]] = {
    'name':                   {'required': True, 'types': (str,)},
    'abbr':                   {'required': True, 'types': (str,)},
    'season_format':          {'required': True, 'types': (str,), 'allowed_values': VALID_LEAGUE_SEASON_FORMATS},
    'regular_season_types':   {'required': True, 'types': (list,)},
    'postseason_types':       {'required': True, 'types': (list,)},
    'calendar_flip_md':       {'required': True, 'types': (str,)},
    'retention_seasons':      {'required': True, 'types': (int,)},
    'primary_source':         {'required': True, 'types': (str,)},
    'roster_maintainer':       {'required': True, 'types': (str,)},
}

LEAGUES: Dict[str, Dict[str, Any]] = {
    'nba': {
        'name':                   'NBA',
        'abbr':                   'NBA',
        'season_format':          'split_year',
        'regular_season_types':   ['rs'],
        'postseason_types':       ['po', 'pi'],
        'calendar_flip_md':       '08-01',
        'retention_seasons':      8,
        'primary_source':         'nba_api',
        'roster_maintainer':      'nba_api'
    }
}
