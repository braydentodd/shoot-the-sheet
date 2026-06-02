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
        'tables': ['players', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'HEIGHT'},
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
                    'player': {'dataset': 'commonallplayers', 'field': 'WEIGHT'},
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
        'tables': ['rosters', 'unmatched_players'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'commonallplayers', 'field': 'SEASON_EXP'},
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
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_ABBREVIATION', 'transform': 'safe_str'},
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
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_CONFERENCE', 'transform': 'safe_str'},
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
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_CITY', 'transform': 'safe_str'},
                },
            },
        },
    },
    'region': {
        'type': 'TEXT',
        'tables': ['teams', 'unmatched_teams'],
        'nullable': True,
        'default': None,
        'manager': 'perennial_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {'dataset': 'team_metadata', 'field': 'TEAM_STATE', 'transform': 'safe_str'},
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
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'GP'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'GP'},
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
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'MIN', 'scale': 10},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'MIN', 'scale': 10},
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
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'W'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'W'},
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
        'tables': ['player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': False,
        'default': 0,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FG3M'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FG3M'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FTM'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FTM'},
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
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'FTA'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'FTA'},
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
                        'dataset': 'leaguedashplayerstats',
                        'field': 'PCT_UAST_2PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashplayerstats',
                        'field': 'PCT_UAST_3PM',
                        'scale': 10,
                        'params': {'measure_type_detailed_defense': 'Scoring'},
                    },
                    'team': {
                        'dataset': 'leaguedashteamstats',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'AST'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'AST'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'STL'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'STL'}
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
                    'player': {'dataset': 'leaguedashplayerstats', 'field': 'BLK'},
                    'team': {'dataset': 'leaguedashteamstats', 'field': 'BLK'},
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'DEFLECTIONS'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'DEFLECTIONS'},
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
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'CONTESTED_SHOTS_2PT'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'CONTESTED_SHOTS_2PT'},
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
                    'player': {'dataset': 'leaguehustlestatsplayer', 'field': 'CONTESTED_SHOTS_3PT'},
                    'team': {'dataset': 'leaguehustlestatsteam', 'field': 'CONTESTED_SHOTS_3PT'},
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSIVE SHOT TRACKING  (leaguedashptdefend / leaguedashptteamdefend)
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
    # ON/OFF COUNTING STATS (TEAMPLAYERONOFFDETAILS)
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
                        'field': 'TOV',
                        'params': {'measure_type_detailed_defense': 'Opponent'},

                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # ON/OFF REBOUND PCT (TEAMPLAYERONOFFDETAILS — ADVANCED)
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOnCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'teamplayeronoffdetails',
                        'result_set': 'PlayersOffCourtTeamPlayerOnOffDetails',
                        'player_id_field': 'VS_PLAYER_ID',
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
                        'dataset': 'leaguedashteamstats',
                        'field': 'POSS',
                        'params': {'measure_type_detailed_defense': 'Advanced'},
                    },
                    'player': {
                        'dataset': 'leaguedashplayerstats',
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons', 'player_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
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
        'tables': ['team_seasons'],
        'nullable': True,
        'default': None,
        'manager': 'in_season_source',
        'comment': None,
        'dataset_mapping': {
            'NBA': {
                'nba_api': {
                    'team': {
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
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
                        'dataset': 'leaguedashteamstats',
                        'field': 'BLK',
                        'params': {'measure_type_detailed_defense': 'Opponent'}
                    }
                }
            }
        }
    }
}