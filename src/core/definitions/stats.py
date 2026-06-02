"""
The Glass - Stat Domain & Season-Type Definitions

Cross-cutting stats constants used by both ETL cleanup and Publish scaling.

A *domain* groups counter columns that share a common minutes/games denominator
and a common 0-vs-NULL coherency rule.  Cleanup uses ``minutes_col`` to decide
whether to NULL out a domain's stats; publish uses ``minutes_col`` for per-minute / per-possession rates.

A domain is "primary" when its denominator covers the entire stats row (base minutes).  Non-primary domains apply only to the subset of stats
they cover, so cleanup and publish must use the domain's own denominator
instead of the row-level one.
"""

from typing import Any, Dict


STAT_DOMAINS: Dict[str, Dict[str, Any]] = {
    'base': {
        'minutes_col': 'mins_x10',
        'possessions_col': 'poss',
        'primary':     True
    },
    'tracking': {
        'minutes_col': 'tracking_mins_x10',
        'possessions_col': None,
        'primary':     False
    },
    'hustle': {
        'minutes_col': 'hustle_mins_x10',
        'possessions_col': None,
        'primary':     False
    },
    'off': {
        'minutes_col': 'off_mins_x10',
        'possessions_col': None,
        'primary':     False
    }
}


# Codes are grouped into "regular_season" vs "postseason"; queries use the
# groups to decide which season_type values to aggregate.
SEASON_TYPE_GROUPS: Dict[str, tuple] = {
    'regular_season': ('rs',),
    'postseason':     ('po', 'pi', 'ct')
}


# Global pipeline data-retention policy (seasons).
RETENTION_SEASONS: int = 6