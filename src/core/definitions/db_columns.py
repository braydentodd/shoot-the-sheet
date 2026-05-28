"""

The Glass - Column Registry

Single source of truth for database column definitions and provider source
mappings.  Column names match the actual PostgreSQL schema exactly.

Each column entry carries a ``sources`` attribute using this shape:

    dataset_mapping[league_key][source_key][entity] -> source definition

Columns with no external source (system columns) have ``dataset_mapping: None``.

The synthetic identity column ``the_glass_id`` and per-source identity
columns (e.g. ``nba_api_id``) are emitted directly by the DDL generator
(see src/core/lib/ddl.py); they are intentionally not represented here.
"""

from typing import Dict, List, TypedDict, Union, Literal


class MultiSeasonConfig(TypedDict, total=False):
    start_year: int
    aggregation: str

class DatasetMapping(TypedDict, total=False):
    dataset: str
    column: str
    transform: Union[str, None]
    multi_season: MultiSeasonConfig

class ColumnDef(TypedDict):
    type: str
    scope: Union[str, List[str]]
    nullable: bool
    default: Union[str, int, None]
    entity_types: Union[List[str], None]
    manager: Literal['db', 'execution_context', 'in_season_source', 'perennial_source']
    domain: Union[str, None]
    comment: Union[str, None]
    dataset_mapping: Union[Dict[str, Dict[str, Dict[str, DatasetMapping]]], None]

DB_COLUMNS: Dict[str, ColumnDef] = {

    # ------------------------------------------------------------------
    # SYSTEM COLUMNS  (managed by DB / ETL engine, no provider sources)
    # ------------------------------------------------------------------

    'process_id': {
        'type': 'BIGINT GENERATED ALWAYS AS IDENTITY',
        'scope': ['runs', 'tasks'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'db',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'run_id': {
        'type': 'BIGINT',
        'scope': ['tasks'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'the_glass_id': {
        'type': 'BIGINT GENERATED ALWAYS AS IDENTITY',
        'scope': ['profiles'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'db',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'entity_type': {
        'type': 'TEXT',
        'scope': ['runs', 'tasks', 'backfill'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'updated_at': {
        'type': 'TIMESTAMP',
        'scope': ['profiles', 'stats', 'rosters', 'staging', 'runs', 'tasks', 'backfill'],
        'nullable': False,
        'default': 'NOW()',
        'entity_types': ['league', 'player', 'team'],
        'manager': 'db',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'created_at': {
        'type': 'TIMESTAMP',
        'scope': ['profiles', 'stats', 'rosters', 'staging', 'runs', 'tasks', 'backfill'],
        'nullable': False,
        'default': 'NOW()',
        'entity_types': ['league', 'player', 'team'],
        'manager': 'db',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'season': {
        'type': 'TEXT',
        'scope': ['stats', 'tasks', 'backfill'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'season_type': {
        'type': 'TEXT',
        'scope': ['stats', 'tasks', 'backfill'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'notes': {
        'type': 'TEXT',
        'scope': ['profiles'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'the_glass_sheets': {
                    'player': {'dataset': 'players', 'field': 'Notes'},
                    'team': {'dataset': 'teams', 'field': 'Notes'},
                },
            },
        },
    },
    'source_id': {
        'type': 'TEXT',
        'scope': ['staging'],
        'nullable': False,
        'default': None,
        'entity_types': ['team', 'player'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'team_source_id': {
        'type': 'TEXT',
        'scope': ['staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'matched_glass_id': {
        'type': 'BIGINT',
        'scope': ['staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['team', 'player'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    # ------------------------------------------------------------------
    # ENTITY INFORMATION  (league / team / player profile data)
    # ------------------------------------------------------------------
    'name': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': False,
        'default': None,
        'entity_types': ['league', 'player', 'team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'field': 'PLAYER_NAME',
                        'transform': 'safe_str',
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'TEAM_NAME',
                        'transform': 'safe_str',
                    },
                },
            },
        },
    },
    'height_ins_no_shoes': {
        'type': 'SMALLINT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'HEIGHT'},
                },
            },
        },
    },
    'height_ins_with_shoes': {
        'type': 'SMALLINT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'weight_lbs': {
        'type': 'SMALLINT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'WEIGHT'},
                },
            },
        },
    },
    'wingspan_ins': {
        'type': 'SMALLINT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'draftcombineplayeranthro',
                        'field': 'WINGSPAN',
                        'transform': 'parse_height',
                        'multi_season': {
                            'start_year': 2003,
                            'aggregation': 'most_recent_non_null',
                        },
                    },
                },
                'the_glass_sheets': {
                    'player': {'dataset': 'players', 'field': 'Wingspan'},
                },
            },
        },
    },
    'hand': {
        'type': 'CHAR',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'the_glass_sheets': {
                    'player': {'dataset': 'players', 'field': 'Handedness'},
                },
            },
        },
    },
    'birthdate': {
        'type': 'DATE',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'commonallplayers',
                        'field': 'BIRTHDATE',
                        'transform': 'parse_birthdate',
                    },
                },
            },
        },
    },
    'seasons_exp': {
        'type': 'SMALLINT',
        'scope': ['rosters', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'SEASON_EXP'},
                },
            },
        },
    },
    'league_key': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': False,
        'default': None,
        'entity_types': ['league'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'abbr': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['league', 'team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_ABBREVIATION', 'transform': 'safe_str'},
                },
            },
        },
    },
    'conf': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_CONFERENCE', 'transform': 'safe_str'},
                },
            },
        },
    },
    'city': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_CITY', 'transform': 'safe_str'},
                },
            },
        },
    },
    'region': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_STATE', 'transform': 'safe_str'},
                },
            },
        },
    },
    'country': {
        'type': 'TEXT',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': None
    },
    'gender': {
        'type': 'CHAR',
        'scope': ['profiles', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['league', 'team', 'player'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    # ------------------------------------------------------------------
    # GAMES & MINUTES
    # ------------------------------------------------------------------
    'games': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': False,
        'default': 0,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'GP'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'GP'},
                },
            },
        },
    },
    'mins_x10': {
        'type': 'INTEGER',
        'scope': ['stats'],
        'nullable': False,
        'default': 0,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'MIN', 'scale': 10},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'MIN', 'scale': 10},
                },
            },
        },
    },
    'wins': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'W'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'W'},
                },
            },
        },
    },
    'tracking_mins_x10': {
        'type': 'INTEGER',
        'scope': ['stats'],
        'nullable': False,
        'default': 0,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'MIN',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'MIN',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    'off_mins_x10': {
        'type': 'INTEGER',
        'scope': ['stats'],
        'nullable': False,
        'default': 0,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffsummary',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffSummary',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'MIN',
                        'scale': 10
                    },
                },
            },
        },
    },
    'hustle_mins_x10': {
        'type': 'INTEGER',
        'scope': ['stats'],
        'nullable': False,
        'default': 0,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'MIN', 'scale': 10},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'MIN', 'scale': 10},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: 2-POINT
    # ------------------------------------------------------------------
    'fg2m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                },
            },
        },
    },
    'fg2a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: 3-POINT
    # ------------------------------------------------------------------
    'fg3m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FG3M'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FG3M'},
                },
            },
        },
    },
    'fg3a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FG3A'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FG3A'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: FREE THROWS
    # ------------------------------------------------------------------
    'ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FTM'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FTM'},
                },
            },
        },
    },
    'fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FTA'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FTA'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PUTBACKS & DUNKS  (pipeline: filter shooting splits -> aggregate)
    # ------------------------------------------------------------------
    'putbacks': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'tier': 'team_call',
                        'params': {'context_measure_simple': 'FGA'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'Shot_Chart_Detail',
                                'field': 'SHOT_MADE_FLAG',
                                'filter_field': 'ACTION_TYPE',
                                'filter_values': ['Putback Dunk Shot', 'Putback Layup Shot', 'Tip Dunk Shot', 'Tip Layup Shot'],
                            },
                            {'type': 'aggregate', 'method': 'sum'},
                        ],
                    },
                    'team': {
                        'dataset': 'leaguedashplayerstats',
                        'tier': 'team_call',
                        'params': {'context_measure_simple': 'FGA'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'Shot_Chart_Detail',
                                'field': 'SHOT_MADE_FLAG',
                                'filter_field': 'ACTION_TYPE',
                                'filter_values': ['Putback Dunk Shot', 'Putback Layup Shot', 'Tip Dunk Shot', 'Tip Layup Shot'],
                            },
                            {'type': 'aggregate', 'method': 'sum'},
                        ],
                    },
                },
            },
        },
    },
    'putbacks_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'tier': 'team_call',
                        'params': {'context_measure_simple': 'FGA'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'Shot_Chart_Detail',
                                'field': 'SHOT_ATTEMPTED_FLAG',
                                'filter_field': 'ACTION_TYPE',
                                'filter_values': ['Putback Dunk Shot', 'Putback Layup Shot', 'Tip Dunk Shot', 'Tip Layup Shot'],
                            },
                            {'type': 'aggregate', 'method': 'sum'},
                        ],
                    },
                    'team': {
                        'dataset': 'leaguedashplayerstats',
                        'tier': 'team_call',
                        'params': {'context_measure_simple': 'FGA'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'Shot_Chart_Detail',
                                'field': 'SHOT_ATTEMPTED_FLAG',
                                'filter_field': 'ACTION_TYPE',
                                'filter_values': ['Putback Dunk Shot', 'Putback Layup Shot', 'Tip Dunk Shot', 'Tip Layup Shot'],
                            },
                            {'type': 'aggregate', 'method': 'sum'},
                        ],
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # UNASSISTED FIELD GOALS  (per-player shooting splits)
    # ------------------------------------------------------------------
    'unassisted_rim_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'playerdashboardbyshootingsplits',
                        'tier': 'player',
                        'params': {'measure_type_detailed': 'Base', 'per_mode_detailed': 'Totals'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'ShotAreaPlayerDashboard',
                                'fields': {'FGM': 'FGM', 'rate': 'PCT_UAST_FGM'},
                                'filter_field': 'GROUP_VALUE',
                                'filter_values': ['Restricted Area'],
                            },
                            {'type': 'math', 'expression': 'FGM * rate'}
                        ]
                    },
                    'team': {
                        'dataset': 'teamdashboardbyshootingsplits',
                        'tier': 'team',
                        'params': {
                            'measure_type_detailed_defense': 'Base',
                            'per_mode_detailed': 'Totals',
                        },
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'ShotAreaTeamDashboard',
                                'fields': {'FGM': 'FGM', 'rate': 'PCT_UAST_FGM'},
                                'filter_field': 'GROUP_VALUE',
                                'filter_values': ['Restricted Area'],
                            },
                            {'type': 'math', 'expression': 'FGM * rate'}
                        ]
                    },
                },
            },
        },
    },
    'unassisted_fg2m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'playerdashboardbyshootingsplits',
                        'tier': 'player',
                        'params': {'measure_type_detailed': 'Base', 'per_mode_detailed': 'Totals'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'OverallPlayerDashboard',
                                'fields': {'FGM': 'FGM', 'FG3M': 'FG3M', 'rate': 'PCT_UAST_2PM'}
                            },
                            {'type': 'math', 'expression': '(FGM - FG3M) * rate'}
                        ]
                    },
                    'team': {
                        'dataset': 'teamdashboardbyshootingsplits',
                        'tier': 'team',
                        'params': {
                            'measure_type_detailed_defense': 'Base',
                            'per_mode_detailed': 'Totals',
                        },
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'OverallTeamDashboard',
                                'fields': {'FGM': 'FGM', 'FG3M': 'FG3M', 'rate': 'PCT_UAST_2PM'}
                            },
                            {'type': 'math', 'expression': '(FGM - FG3M) * rate'}
                        ]
                    }
                }
            }
        }
    },
    'unassisted_fg3m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'playerdashboardbyshootingsplits',
                        'tier': 'player',
                        'params': {'measure_type_detailed': 'Base', 'per_mode_detailed': 'Totals'},
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'OverallPlayerDashboard',
                                'fields': {'FG3M': 'FG3M', 'rate': 'PCT_UAST_3PM'}
                            },
                            {'type': 'math', 'expression': 'FG3M * rate'}
                        ]
                    },
                    'team': {
                        'dataset': 'teamdashboardbyshootingsplits',
                        'tier': 'team',
                        'params': {
                            'measure_type_detailed_defense': 'Base',
                            'per_mode_detailed': 'Totals',
                        },
                        'operations': [
                            {
                                'type': 'extract',
                                'result_set': 'OverallTeamDashboard',
                                'fields': {'FG3M': 'FG3M', 'rate': 'PCT_UAST_3PM'}
                            },
                            {'type': 'math', 'expression': 'FG3M * rate'}
                        ]
                    }
                }
            }
        }
    },
    # ------------------------------------------------------------------
    # REBOUNDS
    # ------------------------------------------------------------------
    'o_rebs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'OREB'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'OREB'},
                },
            },
        },
    },
    'd_rebs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'DREB'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'DREB'},
                },
            },
        },
    },
    'o_reb_pct_x1000': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'field': 'OREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                },
            },
        },
    },
    'd_reb_pct_x1000': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'field': 'DREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'DREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PLAYMAKING
    # ------------------------------------------------------------------
    'assists': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'AST'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'AST'},
                },
            },
        },
    },
    'pot_assists': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'POTENTIAL_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'POTENTIAL_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    'passes': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'PASSES_MADE',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'PASSES_MADE',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    'sec_assists': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'SECONDARY_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'SECONDARY_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # BALL HANDLING
    # ------------------------------------------------------------------
    'touches': {
        'type': 'INTEGER',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'TOUCHES',
                        'params': {'pt_measure_type': 'Possessions', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'TOUCHES',
                        'params': {'pt_measure_type': 'Possessions', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    'time_on_ball': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'TIME_OF_POSS',
                        'params': {'pt_measure_type': 'Possessions', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'TIME_OF_POSS',
                        'params': {'pt_measure_type': 'Possessions', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # TURNOVERS
    # ------------------------------------------------------------------
    'turnovers': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'TOV'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'TOV'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DISTANCE
    # ------------------------------------------------------------------
    'o_dist_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'DIST_MILES_OFF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'DIST_MILES_OFF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    'd_dist_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'DIST_MILES_DEF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'DIST_MILES_DEF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSE: STEALS / BLOCKS / FOULS
    # ------------------------------------------------------------------
    'steals': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'STL'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'STL'}
                },
            },
        },
    },
    'blocks': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'BLK'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'BLK'},
                },
            },
        },
    },
    'fouls': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'PF'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'PF'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # HUSTLE STATS
    # ------------------------------------------------------------------
    'deflections': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'hustle',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'DEFLECTIONS'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'DEFLECTIONS'},
                },
            },
        },
    },
    'charges_drawn': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'hustle',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'CHARGES_DRAWN'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'CHARGES_DRAWN'},
                },
            },
        },
    },
    'contests': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'hustle',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'CONTESTED_SHOTS'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'CONTESTED_SHOTS'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSIVE SHOT TRACKING  (leaguedashptdefend / leaguedashptteamdefend)
    # ------------------------------------------------------------------
    'd_close_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FGM_LT_06',
                        'params': {'defense_category': 'Less Than 6Ft'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FGM_LT_06',
                        'params': {'defense_category': 'Less Than 6Ft'},
                    },
                },
            },
        },
    },
    'd_close_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FGA_LT_06',
                        'params': {'defense_category': 'Less Than 6Ft'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FGA_LT_06',
                        'params': {'defense_category': 'Less Than 6Ft'},
                    },
                },
            },
        },
    },
    'd_fg2m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FG2M',
                        'params': {'defense_category': '2 Pointers'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FG2M',
                        'params': {'defense_category': '2 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg2a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FG2A',
                        'params': {'defense_category': '2 Pointers'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FG2A',
                        'params': {'defense_category': '2 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg3m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FG3M',
                        'params': {'defense_category': '3 Pointers'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FG3M',
                        'params': {'defense_category': '3 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg3a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptdefend',
                        'field': 'FG3A',
                        'params': {'defense_category': '3 Pointers'},
                    },
                    'team': {
                        'dataset': 'leaguedashptteamdefend',
                        'field': 'FG3A',
                        'params': {'defense_category': '3 Pointers'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # RATINGS
    # ------------------------------------------------------------------
    'o_rtg_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'field': 'OFF_RATING',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OFF_RATING',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                },
            },
        },
    },
    'd_rtg_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashplayerstats',
                        'field': 'DEF_RATING',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'DEF_RATING',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                },
            },
        },
    },
    'off_o_rtg_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffsummary',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffSummary',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OFF_RATING',
                        'scale': 10,
                        'aggregation': 'minute_weighted',
                    },
                },
            },
        },
    },
    'off_d_rtg_x10': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffsummary',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffSummary',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'DEF_RATING',
                        'scale': 10,
                        'aggregation': 'minute_weighted',
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # ON/OFF COUNTING STATS (TEAMPLAYERONOFFDETAILS)
    # ------------------------------------------------------------------
    'on_2fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_2fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_3fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FG3M',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_3fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FG3A',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FTA',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FTM',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_tovs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'TOV',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_blocks': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'BLK',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_2fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_2fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_3fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FG3M',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_3fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FG3A',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FTA',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'FTM',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_tovs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'TOV',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_blocks': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'BLK',
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_2fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'OPP_FGM - OPP_FG3M', 'fields': ['OPP_FGM', 'OPP_FG3M']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_2fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'OPP_FGA - OPP_FG3A', 'fields': ['OPP_FGA', 'OPP_FG3A']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_3fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_3fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_pts': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_PTS',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'on_opp_tovs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_2fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'OPP_FGM - OPP_FG3M', 'fields': ['OPP_FGM', 'OPP_FG3M']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_2fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'derived': {'math': 'OPP_FGA - OPP_FG3A', 'fields': ['OPP_FGA', 'OPP_FG3A']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_3fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_3fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_pts': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_PTS',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'off_opp_tovs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'tier': 'team_call',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'OPP_TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'aggregation': 'sum',
                    },
                },
            },
        },
    },
    'ft_assists': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {
                        'dataset': 'leaguedashptstats',
                        'field': 'FT_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Player'},
                    },
                    'team': {
                        'dataset': 'leaguedashptstats',
                        'field': 'FT_AST',
                        'params': {'pt_measure_type': 'Passing', 'player_or_team': 'Team'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PBP STATS (INITIAL INTEGRATION)
    # ------------------------------------------------------------------
    'heaves': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'HeaveAttempts',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'HeaveAttempts',
                    },
                },
            },
        },
    },
    'poss': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'OffPoss',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'OffPoss',
                    },
                },
            },
        },
    },
    'o_rtg': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'derived': {'math': '(Points / OffPoss) * 100', 'fields': ['Points', 'OffPoss']},
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'derived': {'math': '(Points / OffPoss) * 100', 'fields': ['Points', 'OffPoss']},
                    },
                },
            },
        },
    },
    'd_rtg': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'derived': {'math': '(OpponentPoints / DefPoss) * 100', 'fields': ['OpponentPoints', 'DefPoss']},
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'derived': {'math': '(OpponentPoints / DefPoss) * 100', 'fields': ['OpponentPoints', 'DefPoss']},
                    },
                },
            },
        },
    },
    'o_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'OffFGReboundPct',
                        'scale': 1000,
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'OffFGReboundPct',
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'd_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player', 'team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'DefFGReboundPct',
                        'scale': 1000,
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'DefFGReboundPct',
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'blocks_recovered': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'hustle',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'RecoveredBlocks',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'RecoveredBlocks',
                    },
                },
            },
        },
    },
    'o_fouls_drawn': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'hustle',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'Offensive Fouls Drawn',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'Offensive Fouls Drawn',
                    },
                },
            },
        },
    },
    'assist_points': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'AssistPoints',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'AssistPoints',
                    },
                },
            },
        },
    },
    'true_ft_trips': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'derived': {
                            'math': 'TwoPtShootingFoulsDrawn + ThreePtShootingFoulsDrawn + NonShootingFoulsDrawn',
                            'fields': ['TwoPtShootingFoulsDrawn', 'ThreePtShootingFoulsDrawn', 'NonShootingFoulsDrawn']
                        },
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'derived': {
                            'math': 'TwoPtShootingFoulsDrawn + ThreePtShootingFoulsDrawn + NonShootingFoulsDrawn',
                            'fields': ['TwoPtShootingFoulsDrawn', 'ThreePtShootingFoulsDrawn', 'NonShootingFoulsDrawn']
                        },
                    },
                },
            },
        },
    },
    'o_pace': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'SecondsPerPossOff',
                        'scale': 10,
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'SecondsPerPossOff',
                        'scale': 10,
                    },
                },
            },
        },
    },
    'd_pace': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'SecondsPerPossDef',
                        'scale': 10,
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'SecondsPerPossDef',
                        'scale': 10,
                    },
                },
            },
        },
    },
    'zbounds': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': 'tracking',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'pbp_team_totals',
                        'field': 'SelfOReb',
                    },
                    'player': {
                        'dataset': 'pbp_player_totals',
                        'result_set': 'PbpTotals',
                        'player_id_field': 'EntityId',
                        'field': 'SelfOReb',
                    },
                },
            },
        },
    },
    'on_d_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'DReb% - Missed FGs - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_o_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'OReb% - Missed FGs - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_blocks_recovered': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'Blocks Recovered % - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_rim_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim Shot Frequency - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_rim_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim FG% - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_d_rim_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim Shot Frequency - Defense - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'on_d_rim_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim FG% - Defense - On',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_d_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'DReb% - Missed FGs - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_o_reb_pct': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'OReb% - Missed FGs - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_blocks_recovered': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'Blocks Recovered % - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_rim_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim Shot Frequency - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_rim_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim FG% - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_d_rim_fga': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim Shot Frequency - Defense - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },
    'off_d_rim_fgm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'in_season_source',
        'domain': 'onoff',
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'pbp_stats': {
                    'player': {
                        'dataset': 'pbp_on_off',
                        'tier': 'team_call',
                        'result_set': 'OnOffStats',
                        'player_id_field': 'PlayerId',
                        'field': 'At Rim FG% - Defense - Off',
                        'scale': 10000,
                    },
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # OPERATIONAL COLUMNS - RUNS TABLE
    # ------------------------------------------------------------------
    'pipeline': {
        'type': 'TEXT',
        'scope': ['runs', 'tasks'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'status': {
        'type': 'TEXT',
        'scope': ['runs', 'tasks'],
        'nullable': False,
        'default': "'pending'",
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'completed_at': {
        'type': 'TIMESTAMP',
        'scope': ['runs', 'tasks', 'backfill'],
        'nullable': True,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'total_items': {
        'type': 'INTEGER',
        'scope': ['runs'],
        'nullable': False,
        'default': '0',
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'completed_items': {
        'type': 'INTEGER',
        'scope': ['runs'],
        'nullable': False,
        'default': '0',
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'total_rows': {
        'type': 'INTEGER',
        'scope': ['runs'],
        'nullable': False,
        'default': '0',
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'error_message': {
        'type': 'TEXT',
        'scope': ['runs', 'tasks'],
        'nullable': True,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },

    # ------------------------------------------------------------------
    # OPERATIONAL COLUMNS - TASKS TABLE
    # ------------------------------------------------------------------
    # run_id handled as an identity column in the SYSTEM COLUMNS section

    # ------------------------------------------------------------------
    # REFERENCE ID COLUMNS (foreign keys referencing core.*_profiles)
    # These are resolved by the ETL (execution context) prior to writes.
    # ------------------------------------------------------------------
    'player_id': {
        'type': 'BIGINT',
        'scope': ['stats', 'rosters'],
        'nullable': False,
        'default': None,
        'entity_types': ['player'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'team_id': {
        'type': 'BIGINT',
        'scope': ['stats', 'rosters'],
        'nullable': False,
        'default': None,
        'entity_types': ['team'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'league_id': {
        'type': 'BIGINT',
        'scope': ['rosters', 'runs', 'tasks', 'backfill', 'staging'],
        'nullable': False,
        'default': None,
        'entity_types': ['league'],
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'source_key': {
        'type': 'TEXT',
        'scope': ['backfill', 'staging'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'item_key': {
        'type': 'TEXT',
        'scope': ['tasks'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'rows_written': {
        'type': 'INTEGER',
        'scope': ['tasks'],
        'nullable': False,
        'default': '0',
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'retry_count': {
        'type': 'INTEGER',
        'scope': ['tasks'],
        'nullable': False,
        'default': '0',
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },
    'coverage_signature': {
        'type': 'TEXT',
        'scope': ['backfill'],
        'nullable': False,
        'default': None,
        'entity_types': None,
        'manager': 'execution_context',
        'domain': None,
        'comment': None,
        'dataset_mapping': None,
    },

    # ------------------------------------------------------------------
    # ROSTER COLUMNS (league_rosters, team_rosters)
    # Shared operational/data columns only.  FK columns (league_id, team_id,
    # player_id) are derived directly from ROSTER_TABLES.foreign_keys by
    # the DDL generator, so they do not belong here.
    # ------------------------------------------------------------------
    'jersey_num': {
        'type': 'TEXT',
        'scope': ['rosters', 'staging'],
        'nullable': True,
        'default': None,
        'entity_types': ['player'],
        'manager': 'perennial_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'JERSEY'},
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # OPPONENT STATS
    # ------------------------------------------------------------------
    'opp_fg2m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FGM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'derived': {'subtract': 'OPP_FG3M'}
                        }
                    }
                }
            }
        },
    'opp_fg2a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FGA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'derived': {'subtract': 'OPP_FG3A'}
                        }
                    }
                }
            }
        },
    'opp_fg3m': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                        }
                    }
                }
            }
        },
    'opp_fg3a': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_ftm': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_fta': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_o_rebs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_OREB',
                        'params': {'measure_type_detailed_defense': 'Opponent'}}}}}},
    'opp_d_rebs': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_DREB',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_assists': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_AST',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_turnovers': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_fouls': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'domain': None,
        'comment': None,
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_PF',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_steals': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_STL',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_blocks': {
        'type': 'SMALLINT',
        'scope': ['stats'],
        'nullable': True,
        'default': None,
        'entity_types': ['team'],
        'manager': 'in_season_source',
        'dataset_mapping': {
            'nba': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
                        'field': 'OPP_BLK',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        }
    }
}