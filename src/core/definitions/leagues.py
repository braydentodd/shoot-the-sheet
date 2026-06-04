"""
The Glass - League Definitions

Per-league operational settings: calendar window, retention, season grammar.
Dataset-level role assignments and source wiring have moved to
:data:`src.etl.definitions.datasets.DATASETS`.

Pure declarative data; helpers live in :mod:`src.core.lib.leagues`.
"""

from typing import Dict, List, TypedDict


# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_LEAGUE_SEASON_FORMATS = frozenset({'same_year', 'split_year'})
VALID_LEAGUE_GENDERS = frozenset({'M', 'W'})

# ============================================================================
# SCHEMA
# ============================================================================

class LeagueDef(TypedDict):
    name: str
    gender: str
    season_format: str
    regular_season_types: List[str]
    postseason_types: List[str]
    calendar_flip: str

LEAGUES: Dict[str, LeagueDef] = {
    'NBA': {
        'name':                   'National Basketball Association',
        'gender':                 'M',
        'season_format':          'split_year',
        'regular_season_types':   ['rs'],
        'postseason_types':       ['po', 'pi'],
        'calendar_flip':          '08/01',
    },
}
