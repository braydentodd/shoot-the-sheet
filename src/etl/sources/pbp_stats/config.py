"""
The Glass - PBP Stats Source Configuration

Pure data definitions for the ``pbp_stats`` source: dataset metadata,
season-type mapping, and field-name mappings.
"""

from typing import Any, Dict, List, TypedDict, Union


class ApiConfigDef(TypedDict):
    base_url: str
    league: str
    max_consecutive_failures: int


class DatasetDef(TypedDict):
    min_season: Union[str, None]
    execution_tier: str
    extraction_mode: str
    default_result_set: str
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    entity_types: List[str]
    endpoint: str
    url_suffix: Union[str, None]


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
    'league': 'nba',
    'max_consecutive_failures': 5,
}


# ==========================================================================
# DATASET DEFINITIONS
# ==========================================================================

DATASETS: Dict[str, DatasetDef] = {
    # Team and opponent aggregate totals from pbpstats API.
    'pbp_team_totals': {
        'min_season': '2000-01',
        'execution_tier': 'per_league',
        'extraction_mode': 'standard',
        'default_result_set': 'PbpTotals',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['team'],
        'endpoint': 'get-totals',
        'url_suffix': None,
    },
    'pbp_player_totals': {
        'min_season': '2000-01',
        'execution_tier': 'per_team',
        'extraction_mode': 'raw',
        'default_result_set': 'PbpTotals',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
        'endpoint': 'get-totals',
        'url_suffix': None,
    },
    'pbp_on_off': {
        'min_season': '2000-01',
        'execution_tier': 'per_team',
        'extraction_mode': 'raw',
        'default_result_set': 'OnOffStats',
        'season_type_param': None,
        'per_mode_param': None,
        'entity_types': ['player'],
        'endpoint': 'get-on-off',
        'url_suffix': '/team',
    },
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
