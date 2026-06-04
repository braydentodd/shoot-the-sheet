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

from typing import Any, Dict, List, TypedDict, Union, Literal


class MultiSeasonConfig(TypedDict, total=False):
    start_year: int
    aggregation: str

class DatasetMapping(TypedDict, total=False):
    dataset: str
    field: str
    transform: Union[str, None]
    scale: int
    params: Dict[str, Any]
    derived: Dict[str, Any]
    multi_season: MultiSeasonConfig

class ColumnDef(TypedDict):
    type: str
    tables: Union[str, List[str]]
    nullable: bool
    default: Union[str, int, None]
    manager: Literal['db', 'execution_context', 'in_season_source', 'perennial_source']
    domain: Union[str, None]
    comment: Union[str, None]
    dataset_mapping: Union[Dict[str, Dict[str, Dict[str, DatasetMapping]]], None]

DB_COLUMNS: Dict[str, ColumnDef] = {

    # ------------------------------------------------------------------
    # SYSTEM COLUMNS  (managed by DB / ETL engine, no provider sources)
    # ------------------------------------------------------------------

    'process_id': {
        'type': 'BIGINT',
        'tables': ['runs', 'tasks'],
        'nullable': False,
        'default': "nextval('ops.process_id_seq')",
        'manager': 'db',
        'comment': None,
        'dataset_mapping': None,
    },
    'run_id': {
        'type': 'BIGINT',
        'tables': ['tasks'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'the_glass_id': {
        'type': 'BIGINT',
        'tables': ['leagues', 'teams', 'players', 'countries'],
        'nullable': False,
        'default': "nextval('profiles.the_glass_id_seq')",
        'manager': 'db',
        'comment': None,
        'dataset_mapping': None,
    },
    'entity_type': {
        'type': 'TEXT',
        'tables': ['tasks', 'coverages'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'updated_at': {
        'type': 'TIMESTAMP',
        'tables': ['all'],
        'nullable': False,
        'default': 'NOW()',
        'manager': 'db',
        'comment': None,
        'dataset_mapping': None,
    },
    'created_at': {
        'type': 'TIMESTAMP',
        'tables': ['all'],
        'nullable': False,
        'default': 'NOW()',
        'manager': 'db',
        'comment': None,
        'dataset_mapping': None,
    },
    'season': {
        'type': 'TEXT',
        'tables': ['team_seasons', 'player_seasons', 'tasks', 'coverages'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'season_type': {
        'type': 'TEXT',
        'tables': ['team_seasons', 'player_seasons', 'tasks', 'coverages'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'notes': {
        'type': 'TEXT',
        'tables': ['teams', 'players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'the_glass_sheets': {
                    'player': {'dataset': 'players', 'field': 'Notes'},
                    'team': {'dataset': 'teams', 'field': 'Notes'},
                },
            },
        },
    },
    'source_id': {
        'type': 'TEXT',
        'tables': ['unmatched_teams', 'unmatched_players'],
        'nullable': False,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': None,
    },
    'team_source_id': {
        'type': 'TEXT',
        'tables': ['unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': None,
    },
    'matched_glass_id': {
        'type': 'BIGINT',
        'tables': ['unmatched_teams', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    # ------------------------------------------------------------------
    # ENTITY INFORMATION  (league / team / player profile data)
    # ------------------------------------------------------------------
    'name': {
        'type': 'TEXT',
        'tables': ['leagues', 'teams', 'players', 'countries', 'unmatched_teams', 'unmatched_players'],
        'nullable': False,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'PLAYER_NAME',
                        'transform': 'safe_str',
                    },
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'TEAM_NAME',
                        'transform': 'safe_str',
                    },
                },
            },
        },
    },
    'height_ins_no_shoes': {
        'type': 'SMALLINT',
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_info', 'field': 'HEIGHT'},
                },
            },
        },
    },
    'height_ins_with_shoes': {
        'type': 'SMALLINT',
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': None,
    },
    'weight_lbs': {
        'type': 'SMALLINT',
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_info', 'field': 'WEIGHT'},
                },
            },
        },
    },
    'wingspan_ins': {
        'type': 'SMALLINT',
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'combine_anthro',
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
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'the_glass_sheets': {
                    'player': {'dataset': 'players', 'field': 'Handedness'},
                },
            },
        },
    },
    'birthdate': {
        'type': 'DATE',
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_info',
                        'field': 'BIRTHDATE',
                        'transform': 'parse_birthdate',
                    },
                },
            },
        },
    },
    'seasons_exp': {
        'type': 'SMALLINT',
        'tables': ['teams_players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_info', 'field': 'SEASON_EXP'},
                },
            },
        },
    },
    'code': {
        'type': 'TEXT',
        'tables': ['leagues', 'countries'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'country_id': {
        'type': 'BIGINT',
        'tables': ['teams', 'countries_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': None,
    },
    'abbr': {
        'type': 'TEXT',
        'tables': ['teams', 'unmatched_teams'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {'dataset': 'team_info', 'field': 'TEAM_ABBREVIATION', 'transform': 'safe_str'},
                },
            },
        },
    },
    'conf': {
        'type': 'TEXT',
        'tables': ['teams', 'unmatched_teams'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {'dataset': 'team_info', 'field': 'TEAM_CONFERENCE', 'transform': 'safe_str'},
                },
            },
        },
    },
    'city': {
        'type': 'TEXT',
        'tables': ['teams', 'unmatched_teams'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {'dataset': 'team_info', 'field': 'TEAM_CITY', 'transform': 'safe_str'},
                },
            },
        },
    },
    'source_country': {
        'type': 'TEXT',
        'tables': ['unmatched_teams', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': None
    },
    'gender': {
        'type': 'CHAR',
        'tables': ['leagues', 'teams', 'players', 'unmatched_teams', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    # ------------------------------------------------------------------
    # GAMES & MINUTES
    # ------------------------------------------------------------------
    'games': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'GP'},
                    'team': {'dataset': 'team_stats', 'field': 'GP'},
                },
            },
        },
    },
    'mins_x10': {
        'type': 'INTEGER',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'MIN', 'scale': 10},
                    'team': {'dataset': 'team_stats', 'field': 'MIN', 'scale': 10},
                },
            },
        },
    },
    'wins': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'W'},
                    'team': {'dataset': 'team_stats', 'field': 'W'},
                },
            },
        },
    },
    'tracking_mins_x10': {
        'type': 'INTEGER',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'MIN',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'MIN',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
                    },
                },
            },
        },
    },
    'off_mins_x10': {
        'type': 'INTEGER',
        'tables': ['player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'MIN',
                        'scale': 10
                    },
                },
            },
        },
    },
    'hustle_mins_x10': {
        'type': 'INTEGER',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_hustle', 'field': 'MIN', 'scale': 10},
                    'team': {'dataset': 'team_hustle', 'field': 'MIN', 'scale': 10},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: 2-POINT
    # ------------------------------------------------------------------
    'fg2m': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                    'team': {
                        'dataset': 'team_stats',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                },
            },
        },
    },
    'fg2a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                    },
                    'team': {
                        'dataset': 'team_stats',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'FG3M'},
                    'team': {'dataset': 'team_stats', 'field': 'FG3M'},
                },
            },
        },
    },
    'fg3a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'FG3A'},
                    'team': {'dataset': 'team_stats', 'field': 'FG3A'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: FREE THROWS
    # ------------------------------------------------------------------
    'ftm': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'FTM'},
                    'team': {'dataset': 'team_stats', 'field': 'FTM'},
                },
            },
        },
    },
    'fta': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'FTA'},
                    'team': {'dataset': 'team_stats', 'field': 'FTA'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # UNASSISTED FIELD GOALS  (per-player shooting splits)
    # ------------------------------------------------------------------
    'unassisted_fg2m_pct_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'PCT_UAST_2PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'PCT_UAST_2PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                },
            },
        },
    },
    'unassisted_fg3m_pct_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'PCT_UAST_3PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'PCT_UAST_3PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # REBOUNDS
    # ------------------------------------------------------------------
    'o_reb_pct_x1000': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'OREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'team_stats',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'DREB_PCT',
                        'scale': 1000,
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'team': {
                        'dataset': 'team_stats',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'AST'},
                    'team': {'dataset': 'team_stats', 'field': 'AST'},
                },
            },
        },
    },
    'pot_assists': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'POTENTIAL_AST',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'POTENTIAL_AST',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                },
            },
        },
    },
    'passes': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'PASSES_MADE',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'PASSES_MADE',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                },
            },
        },
    },
    'sec_assists': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'SECONDARY_AST',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'SECONDARY_AST',
                        'params': {'pt_measure_type': 'Passing'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'TOUCHES',
                        'params': {'pt_measure_type': 'Possessions'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'TOUCHES',
                        'params': {'pt_measure_type': 'Possessions'},
                    },
                },
            },
        },
    },
    'time_on_ball': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'TIME_OF_POSS',
                        'params': {'pt_measure_type': 'Possessions'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'TIME_OF_POSS',
                        'params': {'pt_measure_type': 'Possessions'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'TOV'},
                    'team': {'dataset': 'team_stats', 'field': 'TOV'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DISTANCE
    # ------------------------------------------------------------------
    'o_dist_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'DIST_MILES_OFF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'DIST_MILES_OFF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
                    },
                },
            },
        },
    },
    'd_dist_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'DIST_MILES_DEF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'DIST_MILES_DEF',
                        'scale': 10,
                        'params': {'pt_measure_type': 'SpeedDistance'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'STL'},
                    'team': {'dataset': 'team_stats', 'field': 'STL'}
                },
            },
        },
    },
    'blocks': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'BLK'},
                    'team': {'dataset': 'team_stats', 'field': 'BLK'},
                },
            },
        },
    },
    'fouls': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_stats', 'field': 'PF'},
                    'team': {'dataset': 'team_stats', 'field': 'PF'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # HUSTLE STATS
    # ------------------------------------------------------------------
    'deflections': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_hustle', 'field': 'DEFLECTIONS'},
                    'team': {'dataset': 'team_hustle', 'field': 'DEFLECTIONS'},
                },
            },
        },
    },
    'cont_d_fg2a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_hustle', 'field': 'CONTESTED_SHOTS_2PT'},
                    'team': {'dataset': 'team_hustle', 'field': 'CONTESTED_SHOTS_2PT'},
                },
            },
        },
    },
    'cont_d_fg3a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_hustle', 'field': 'CONTESTED_SHOTS_3PT'},
                    'team': {'dataset': 'team_hustle', 'field': 'CONTESTED_SHOTS_3PT'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSIVE SHOT TRACKING  (player_defense / team_defense)
    # ------------------------------------------------------------------
    'd_fg2m': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_defense',
                        'field': 'FG2M',
                        'params': {'defense_category': '2 Pointers'},
                    },
                    'team': {
                        'dataset': 'team_defense',
                        'field': 'FG2M',
                        'params': {'defense_category': '2 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg2a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_defense',
                        'field': 'FG2A',
                        'params': {'defense_category': '2 Pointers'},
                    },
                    'team': {
                        'dataset': 'team_defense',
                        'field': 'FG2A',
                        'params': {'defense_category': '2 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg3m': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_defense',
                        'field': 'FG3M',
                        'params': {'defense_category': '3 Pointers'},
                    },
                    'team': {
                        'dataset': 'team_defense',
                        'field': 'FG3M',
                        'params': {'defense_category': '3 Pointers'},
                    },
                },
            },
        },
    },
    'd_fg3a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_defense',
                        'field': 'FG3A',
                        'params': {'defense_category': '3 Pointers'},
                    },
                    'team': {
                        'dataset': 'team_defense',
                        'field': 'FG3A',
                        'params': {'defense_category': '3 Pointers'},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # ON/OFF COUNTING STATS
    # ------------------------------------------------------------------
    'on_2fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                },
            },
        },
    },
    'on_2fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                    },
                },
            },
        },
    },
    'on_3fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FG3M',
                    },
                },
            },
        },
    },
    'on_3fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FG3A',
                    },
                },
            },
        },
    },
    'on_fta': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FTA',
                    },
                },
            },
        },
    },
    'on_ftm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FTM',
                    },
                },
            },
        },
    },
    'on_tovs': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'TOV',
                    },
                },
            },
        },
    },
    'on_blocks': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'BLK',
                    },
                },
            },
        },
    },
    'off_2fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                    },
                },
            },
        },
    },
    'off_2fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                    },
                },
            },
        },
    },
    'off_3fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FG3M',
                    },
                },
            },
        },
    },
    'off_3fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FG3A',
                    },
                },
            },
        },
    },
    'off_fta': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FTA',
                    },
                },
            },
        },
    },
    'off_ftm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FTM',
                    },
                },
            },
        },
    },
    'off_tovs': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'TOV',
                    },
                },
            },
        },
    },
    'off_blocks': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'BLK',
                    },
                },
            },
        },
    },
    'on_opp_2fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_2fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_3fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_3fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_fta': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_ftm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'on_opp_tovs': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_2fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_2fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']},
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_3fgm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_3fga': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_fta': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_ftm': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    'off_opp_tovs': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # ON/OFF REBOUND PCT (player_on_court / player_off_court — Advanced)
    # ------------------------------------------------------------------
    'on_o_reb_pct_x1000': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'OREB_PCT',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'on_d_reb_pct_x1000': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_on_court',
                        'field': 'DREB_PCT',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'off_o_reb_pct_x1000': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'OREB_PCT',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'off_d_reb_pct_x1000': {
        'type': 'SMALLINT',
        'tables': ['player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'domain': 'off',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_off_court',
                        'field': 'DREB_PCT',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                        'scale': 1000,
                    },
                },
            },
        },
    },
    'ft_assists': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'player_tracking',
                        'field': 'FT_AST',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                    'team': {
                        'dataset': 'team_tracking',
                        'field': 'FT_AST',
                        'params': {'pt_measure_type': 'Passing'},
                    },
                },
            },
        },
    },
    'poss': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'POSS',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'player': {
                        'dataset': 'player_stats',
                        'field': 'POSS',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                },
            },
        },
    },
    'o_fouls_drawn': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'team_totals',
                        'field': 'Offensive Fouls Drawn',
                    },
                    'player': {
                        'dataset': 'player_totals',
                        'field': 'Offensive Fouls Drawn',
                    },
                },
            },
        },
    },
    'assist_points': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'team_totals',
                        'field': 'AssistPoints',
                    },
                    'player': {
                        'dataset': 'player_totals',
                        'field': 'AssistPoints',
                    },
                },
            },
        },
    },
    'true_ft_trips': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'team_totals',
                        'derived': {
                            'math': 'TwoPtShootingFoulsDrawn + ThreePtShootingFoulsDrawn + NonShootingFoulsDrawn',
                            'fields': ['TwoPtShootingFoulsDrawn', 'ThreePtShootingFoulsDrawn', 'NonShootingFoulsDrawn']
                        },
                    },
                    'player': {
                        'dataset': 'player_totals',
                        'derived': {
                            'math': 'TwoPtShootingFoulsDrawn + ThreePtShootingFoulsDrawn + NonShootingFoulsDrawn',
                            'fields': ['TwoPtShootingFoulsDrawn', 'ThreePtShootingFoulsDrawn', 'NonShootingFoulsDrawn']
                        },
                    },
                },
            },
        },
    },
    'o_pace_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'team_totals',
                        'field': 'SecondsPerPossOff',
                        'scale': 10,
                    },
                    'player': {
                        'dataset': 'player_totals',
                        'field': 'SecondsPerPossOff',
                        'scale': 10,
                    },
                },
            },
        },
    },
    'd_pace_x10': {
        'type': 'SMALLINT',
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'pbp_stats': {
                    'team': {
                        'dataset': 'team_totals',
                        'field': 'SecondsPerPossDef',
                        'scale': 10,
                    },
                    'player': {
                        'dataset': 'player_totals',
                        'field': 'SecondsPerPossDef',
                        'scale': 10,
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
        'tables': ['runs', 'tasks'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'status': {
        'type': 'TEXT',
        'tables': ['runs', 'tasks'],
        'nullable': False,
        'default': "'pending'",
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'completed_at': {
        'type': 'TIMESTAMP',
        'tables': ['runs', 'tasks', 'coverages'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'total_tasks': {
        'type': 'INTEGER',
        'tables': ['runs'],
        'nullable': False,
        'default': '0',
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'completed_tasks': {
        'type': 'INTEGER',
        'tables': ['runs'],
        'nullable': False,
        'default': '0',
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'error_message': {
        'type': 'TEXT',
        'tables': ['runs', 'tasks'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },

    # ------------------------------------------------------------------
    # REFERENCE ID COLUMNS (foreign keys referencing core.*_profiles)
    # These are resolved by the ETL (execution context) prior to writes.
    # ------------------------------------------------------------------
    'player_id': {
        'type': 'BIGINT',
        'tables': ['player_seasons', 'teams_players', 'countries_players'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'team_id': {
        'type': 'BIGINT',
        'tables': ['team_seasons', 'player_seasons', 'teams_players', 'leagues_teams'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'league_id': {
        'type': 'BIGINT',
        'tables': ['leagues_teams', 'team_seasons', 'player_seasons', 'tasks', 'coverages', 'unmatched_teams', 'unmatched_players'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'sovereign_id': {
        'type': 'BIGINT',
        'tables': ['countries'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'source': {
        'type': 'TEXT',
        'tables': ['tasks', 'coverages', 'unmatched_teams', 'unmatched_players'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'task_name': {
        'type': 'TEXT',
        'tables': ['tasks'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'dataset': {
        'type': 'TEXT',
        'tables': ['tasks', 'coverages'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'tier': {
        'type': 'TEXT',
        'tables': ['tasks'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'field': {
        'type': 'TEXT',
        'tables': ['coverages'],
        'nullable': False,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'params': {
        'type': 'TEXT',
        'tables': ['tasks', 'coverages'],
        'nullable': True,
        'default': None,
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'rows_written': {
        'type': 'INTEGER',
        'tables': ['tasks'],
        'nullable': False,
        'default': '0',
        'manager': 'execution_context',
        'comment': None,
        'dataset_mapping': None,
    },
    'retry_count': {
        'type': 'INTEGER',
        'tables': ['tasks'],
        'nullable': False,
        'default': '0',
        'manager': 'execution_context',
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
        'tables': ['teams_players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'player_info', 'field': 'JERSEY'},
                },
            },
        },
    },

    # ------------------------------------------------------------------
    # OPPONENT STATS
    # ------------------------------------------------------------------
    'opp_fg2m': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FGM',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'derived': {'math': 'FGM - FG3M', 'fields': ['FGM', 'FG3M']}
                        }
                    }
                }
            }
        },
    'opp_fg2a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FGA',
                        'params': {'measure_type_detailed_defense': 'Opponent'},
                        'derived': {'math': 'FGA - FG3A', 'fields': ['FGA', 'FG3A']}
                        }
                    }
                }
            }
        },
    'opp_fg3m': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FG3M',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                        }
                    }
                }
            }
        },
    'opp_fg3a': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FG3A',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_ftm': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FTM',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_fta': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'FTA',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_assists': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'AST',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_turnovers': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_fouls': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'PF',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_steals': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'STL',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        },
    },
    'opp_blocks': {
        'type': 'SMALLINT',
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'team_stats',
                        'field': 'BLK',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        }
    }
}