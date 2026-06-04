"""
The Glass - Unified Dataset Registry

Single source of truth for all dataset definitions across every source.

Each source has its own namespace so dataset names only need to be unique
within a source.  Every entry carries the same generic orchestrator-level
fields plus a ``source_mapping`` dict that holds source-specific wire
parameters (endpoint names, result-set names, per-mode parameters, etc.).

Shape:

    DATASETS[source_key][dataset_name] -> DatasetDef
    DatasetDef['source_mapping'] -> SourceMappingDef

This mirrors the ``dataset_mapping`` pattern in ``db_columns.py``.
"""

from typing import Dict, List, TypedDict, Union


class SourceMappingDef(TypedDict, total=False):
    """Source-specific wire parameters.  Optional fields vary by source type."""
    class_name: str
    result_set: Union[str, None]
    season_param_format: Union[str, None]
    season_type_param: Union[str, None]
    per_mode_param: Union[str, None]
    requires_params: Union[List[str], None]
    season_param: Union[str, None]
    endpoint: Union[str, None]
    url_suffix: Union[str, None]


class DatasetDef(TypedDict):
    """Generic dataset metadata, uniform across every source."""
    entity: str
    min_season: Union[str, None]
    execution_tier: str
    role: str
    leagues: List[str]
    source_mapping: SourceMappingDef


DATASETS: Dict[str, Dict[str, DatasetDef]] = {

    # ========================================================================
    # NBA API
    # ========================================================================

    'nba_api': {

        # --- Basic stats (since 2003-04) ---

        'player_stats': {
            'entity': 'player',
            'min_season': '2003-04',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashplayerstats',
                'result_set': 'LeagueDashPlayerStats',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_detailed',
            },
        },
        'team_stats': {
            'entity': 'team',
            'min_season': '2003-04',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashteamstats',
                'result_set': 'LeagueDashTeamStats',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_detailed',
            },
        },

        # --- Player tracking (since 2013-14) ---

        'player_tracking': {
            'entity': 'player',
            'min_season': '2013-14',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashptstats',
                'result_set': 'LeagueDashPtStats',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_simple',
                'requires_params': ['pt_measure_type'],
            },
        },
        'team_tracking': {
            'entity': 'team',
            'min_season': '2013-14',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashptstats',
                'result_set': 'LeagueDashPtStats',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_simple',
                'requires_params': ['pt_measure_type'],
            },
        },

        # --- Hustle stats (since 2015-16) ---

        'player_hustle': {
            'entity': 'player',
            'min_season': '2015-16',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguehustlestatsplayer',
                'result_set': 'HustleStatsPlayer',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_time',
            },
        },
        'team_hustle': {
            'entity': 'team',
            'min_season': '2015-16',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguehustlestatsteam',
                'result_set': 'HustleStatsTeam',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_time',
            },
        },

        # --- Defensive matchup (since 2013-14) ---

        'player_defense': {
            'entity': 'player',
            'min_season': '2013-14',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashptdefend',
                'result_set': 'LeagueDashPtDefend',
                'season_param_format': 'SSSS-EE',
                'season_type_param':  'season_type_all_star',
                'per_mode_param': 'per_mode_simple',
                'requires_params': ['defense_category'],
            },
        },
        'team_defense': {
            'entity': 'team',
            'min_season': '2013-14',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'leaguedashptteamdefend',
                'result_set': 'LeagueDashPtTeamDefend',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_simple',
                'requires_params': ['defense_category'],
            },
        },

        # --- Player info (all time) ---

        'player_info': {
            'entity': 'player',
            'min_season': None,
            'execution_tier': 'per_league',
            'role': 'roster_maintainer',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'commonallplayers',
                'result_set': 'CommonAllPlayers',
                'season_param_format': 'SSSS-EE',
            },
        },

        # --- Draft combine (since 2000-01) ---

        'combine_anthro': {
            'entity': 'player',
            'min_season': '2000-01',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'draftcombineplayeranthro',
                'result_set': 'DraftCombinePlayerAnthro',
                'season_param_format': 'SSSS-EE',
                'season_param': 'season_year',
            },
        },

        # --- On/Off court (since 2007-08) ---

        'player_on_court': {
            'entity': 'player',
            'min_season': '2007-08',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'teamplayeronoffdetails',
                'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_detailed',
            },
        },
        'player_off_court': {
            'entity': 'player',
            'min_season': '2007-08',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'teamplayeronoffdetails',
                'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
                'per_mode_param': 'per_mode_detailed',
            },
        },

        # --- Team info (all time) ---

        'team_info': {
            'entity': 'team',
            'min_season': None,
            'execution_tier': 'per_team',
            'role': 'roster_maintainer',
            'leagues': ['NBA'],
            'source_mapping': {
                'class_name': 'teaminfocommon',
                'result_set': 'TeamInfoCommon',
                'season_param_format': 'SSSS-EE',
                'season_type_param': 'season_type_all_star',
            },
        },
    },

    # ========================================================================
    # PBP Stats
    # ========================================================================

    'pbp_stats': {

        'team_totals': {
            'entity': 'team',
            'min_season': '2000-01',
            'execution_tier': 'per_league',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'result_set': 'PbpTotals',
                'season_param_format': 'SSSS-EE',
                'endpoint': 'get-totals',
                'url_suffix': None,
            },
        },
        'player_totals': {
            'entity': 'player',
            'min_season': '2000-01',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'result_set': 'PbpTotals',
                'season_param_format': 'SSSS-EE',
                'endpoint': 'get-totals',
                'url_suffix': None,
            },
        },
        'on_off': {
            'entity': 'player',
            'min_season': '2000-01',
            'execution_tier': 'per_team',
            'role': 'stats_updater',
            'leagues': ['NBA'],
            'source_mapping': {
                'result_set': 'OnOffStats',
                'season_param_format': 'SSSS-EE',
                'endpoint': 'get-on-off',
                'url_suffix': '/team',
            },
        },
    },

    # ========================================================================
    # The Glass Sheets
    # ========================================================================

    'the_glass_sheets': {

        'players': {
            'entity': 'player',
            'min_season': None,
            'execution_tier': 'per_league',
            'role': 'roster_maintainer',
            'leagues': ['NBA'],
            'source_mapping': {},
        },
        'teams': {
            'entity': 'team',
            'min_season': None,
            'execution_tier': 'per_league',
            'role': 'roster_maintainer',
            'leagues': ['NBA'],
            'source_mapping': {},
        },
    },
}


def get_source_entities(source_key: str) -> set:
    """Return the set of entities supported by a source, derived from its datasets."""
    return {ds.get('entity') for ds in DATASETS.get(source_key, {}).values() if ds.get('entity')}
