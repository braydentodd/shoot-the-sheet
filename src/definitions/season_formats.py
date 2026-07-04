"""
Shoot the Sheet - Season Format Configuration

Constants and mappings for season label formatting across different leagues
and data sources.
"""

from typing import Dict, Tuple, Union

# ============================================================================
# VALID VALUE SETS
# ============================================================================

VALID_SHAPES = frozenset(
    {
        "YYYY",
        "YY",
        "YYYY-YY",
        "YY-YY",
        "YYYY-YYYY",
        "YYYY/YY",
        "YY/YY",
        "YYYY/YYYY",
    }
)

VALID_ANCHORS = frozenset({"start", "end", None})

# ============================================================================
# LEAGUE FORMAT MAPPING
# ============================================================================

LEAGUE_FORMAT_TO_SHAPE: Dict[str, Tuple[str, Union[str, None]]] = {
    "same_year": ("YYYY", "end"),
    "split_year": ("YYYY-YY", None),
}

# ============================================================================
# PARSING CONFIGURATION
# ============================================================================

TWO_DIGIT_PIVOT = 80
