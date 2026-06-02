"""
The Glass - Source Registry

Declarative registry of every external data source.  The ``external``
field describes whether a source brings its own external IDs.

  - ``external=True``: source brings its own IDs (e.g. nba_api_id for player/team/league)
  - ``external=False``: source uses the_glass_id only (e.g. user-edited overlays)

``season_format`` describes the source's *wire* format -- how it expects /
emits season labels in API requests and responses.  ``shape`` is one of
:data:`VALID_SHAPES`; ``anchor`` is required for single-segment shapes
(``YYYY`` / ``YY``) and ignored for two-segment shapes (set to ``None``).

Helpers that resolve source assignments per league/entity live in
:mod:`src.core.lib.sources`.
"""

from typing import TypedDict, Dict, List, Union



# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

VALID_SHAPES = frozenset({
    'YYYY', 'YY',
    'YYYY-YY', 'YY-YY', 'YYYY-YYYY',
    'YYYY/YY', 'YY/YY', 'YYYY/YYYY',
})
VALID_ANCHORS = frozenset({'start', 'end', None})


class SeasonFormatDef(TypedDict):
    shape: str
    anchor: Union[str, None]

class RateLimitsDef(TypedDict):
    proxy_name_mask: Union[str, None]

class SourceDef(TypedDict):
    leagues: List[str]
    external: bool
    entity_id_type: str
    id_column: str
    applies_to: List[str]
    season_format: SeasonFormatDef
    rate_limits: RateLimitsDef

SOURCES: Dict[str, SourceDef] = {

    'nba_api': {
        'leagues':        ['NBA'],
        'external':       True,
        'entity_id_type': 'BIGINT',
        'id_column':      'nba_id',
        'applies_to':     ['team', 'player', 'league'],
        'season_format':  {'shape': 'YYYY-YY', 'anchor': None},
        'rate_limits': {
            'requests_per_second': 0.8,
            'max_retries': 3,
            'backoff_base': 30,
            'timeout_default': 30,
            'timeout_bulk': 120,
        },
    },
    'pbp_stats': {
        'leagues':        ['NBA'],
        'external':       True,
        'entity_id_type': 'BIGINT',
        'id_column':      'nba_id',
        'applies_to':     ['team', 'player'],
        'season_format':  {'shape': 'YYYY-YY', 'anchor': None},
        'rate_limits': {
            'requests_per_second': 0.5,
            'max_retries': 3,
            'backoff_base': 30,
            'timeout_default': 30,
                'timeout_bulk': 120,
                'max_consecutive_failures': 5,
            },
        },
    'the_glass_sheets': {
        'leagues':        ['NBA'],
        'external':       False,
        'entity_id_type': 'BIGINT',
        'id_column':      'the_glass_id',
        'applies_to':     ['team', 'player'],
        'season_format':  None,
        'rate_limits': {
            'requests_per_second': 1.0,
            'max_retries': 3,
            'backoff_base': 30,
            'timeout_default': 30,
            'timeout_bulk': 120,
            'max_consecutive_failures': 5,
        },
    },
}
