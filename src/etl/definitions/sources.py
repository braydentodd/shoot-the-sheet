"""
The Glass - Source Registry

Declarative registry of every external data source.

``leagues`` maps league keys to the source-specific league identifier
(e.g. NBA API league_id ``00`` for the NBA).

Helpers that resolve source assignments per league/entity live in
:mod:`src.core.lib.sources`.
"""

from typing import TypedDict, Dict, Union


class RateLimitsDef(TypedDict, total=False):
    requests_per_second: Union[float, int]
    max_retries: int
    backoff_base: Union[float, int]
    timeout_default: Union[float, int]
    timeout_bulk: Union[float, int]
    max_consecutive_failures: int

class SourceDef(TypedDict):
    leagues: Dict[str, str]
    external_id: Union[str, None]
    id_type: str
    rate_limits: RateLimitsDef

SOURCES: Dict[str, SourceDef] = {

    'nba_api': {
        'leagues':              {'NBA': '00'},
        'external_id':          'nba_id',
        'id_type':              'BIGINT',
        'rate_limits': {
            'requests_per_second': 0.8,
            'max_retries': 3,
            'backoff_base': 30,
            'timeout_default': 30,
            'timeout_bulk': 120,
        },
    },
    'pbp_stats': {
        'leagues':              {'NBA': 'nba'},
        'external_id':          'nba_id',
        'id_type':              'BIGINT',
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
        'leagues':              {'NBA': 'nba'},
        'external_id':          None,
        'id_type':              'BIGINT',
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
