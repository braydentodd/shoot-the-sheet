"""
Shoot the Sheet - Stat Rate Definitions

Rate modes used by the publish layer for per-possession and per-minute
scaling when rendering spreadsheet columns.

The ``STAT_RATES`` dict defines the available rate modes.  Each league
declares which rates to use via its ``stat_rates`` list in
:data:`src.core.definitions.leagues.LEAGUES`.
"""

from typing import Dict

STAT_RATES: Dict[str, dict] = {
    "per_poss": {"short_label": "Poss", "rate": 100},
    "per_min": {"short_label": "Min", "rate": 40},
}
