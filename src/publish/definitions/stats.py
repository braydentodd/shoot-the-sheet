"""
The Glass - Stat Rate & Timeframe Definitions

Rate-mode definitions (per-100, per-40) and the historical
timeframes offered to the publish UI.
"""

from typing import Dict


STAT_RATES = {
    'per_possession': {
        'short_label': 'Poss',
        'rate':        100,
        'default':     True,
    },
    'per_minute': {
        'short_label': 'Min',
        'rate':        40,
        'default':     False,
    },
}


HISTORICAL_TIMEFRAMES: Dict[int, str] = {
    1: '(Previous Season)',
    3: '(Previous 3 Seasons)',
    5: '(Previous 5 Seasons)',
    7: '(Previous 7 Seasons)',
}


# ============================================================================
# DERIVED CONSTANTS
# ============================================================================

DEFAULT_STAT_RATE: str = 'per_possession'