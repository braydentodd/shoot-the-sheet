"""
The Glass - PBP Stats Source Configuration

Pure data definitions for the ``pbp_stats`` source: season-type mapping,
rate limits, and field-name mappings.

Dataset metadata lives in the unified registry
(:mod:`src.etl.definitions.datasets`).  This module is purely about
how to talk to the source itself.
"""

from typing import Any, Dict, TypedDict, Union


class ApiConfigDef(TypedDict):
    base_url: str
    max_consecutive_failures: int


class SeasonTypeDef(TypedDict):
    name: str
    min_season: Union[str, None]


SEASON_TYPES: Dict[str, SeasonTypeDef] = {
    'rs': {
        'name': 'Regular Season',
        'min_season': None,
    },
    'po': {
        'name': 'Playoffs',
        'min_season': None,
    },
    'pi': {
        'name': 'PlayIn',
        'min_season': '2020-21',
    },
}


# ==========================================================================
# API OPERATIONAL SETTINGS
# ==========================================================================

API_CONFIG: ApiConfigDef = {
    'base_url': 'https://api.pbpstats.com',
    'max_consecutive_failures': 5,
}


# ==========================================================================
# API FIELD NAME MAPPINGS
# ==========================================================================

API_FIELD_NAMES: Dict[str, Dict[str, Any]] = {
    'entity_id': {'player': 'EntityId', 'team': 'TeamId'},
    'entity_name': {'player': 'Name', 'team': 'Name'},
    'special_ids': {},
    'id_aliases': {'TeamId': ['EntityId'], 'EntityId': ['TeamId']},
}
