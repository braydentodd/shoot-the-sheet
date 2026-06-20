"""
Shoot the Sheet - Column Registry

Single source of truth for database column definitions and provider source
mappings.  Column names match the actual PostgreSQL schema exactly.

Every column with an external source follows this shape:

    dataset_mapping[league_key][identity_key][entity_name][dataset_name] -> DatasetMapping

Columns with no external source (system columns) have ``dataset_mapping: None``.

The synthetic identity column ``sts_id`` and per-source identity
columns (e.g. ``nba_id_id``) are emitted directly by the DDL generator
(see src/core/lib/ddl.py); they are intentionally not represented here.
"""

from tkinter import Scale
from typing import Any, Dict, List, TypedDict, Union


class MultiSeasonConfig(TypedDict, total=False):
    start_year: int
    aggregation: str


class DatasetMapping(TypedDict, total=False):
    field: Union[str, None]
    transform: Union[str, None]
    scale: Union[int, None]
    params: Union[Dict[str, Any], None]
    derived: Union[Dict[str, Any], None]
    multi_season: Union[MultiSeasonConfig, None]


class ColumnDef(TypedDict):
    type: str
    tables: Union[str, List[str]]
    nullable: bool
    default: Union[str, int, None]
    rate: Union[str, None]
    scale: Union[int, None]
    dataset_mapping: Union[
        Dict[str, Dict[str, Dict[str, Dict[str, DatasetMapping]]]],
        None,
    ]


DB_COLUMNS: Dict[str, ColumnDef] = {
    # ------------------------------------------------------------------
    # SYSTEM COLUMNS  (managed by DB / ETL engine, no provider sources)
    # ------------------------------------------------------------------
    "process_id": {
        "type": "BIGINT",
        "tables": ["runs", "tasks"],
        "nullable": False,
        "default": "nextval('ops.process_id_seq')",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "run_id": {
        "type": "BIGINT",
        "tables": ["tasks"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "sts_id": {
        "type": "BIGINT",
        "tables": ["teams", "players"],
        "nullable": False,
        "default": "nextval('profiles.sts_id_seq')",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "entity": {
        "type": "TEXT",
        "tables": ["tasks", "coverages", "identities_entities"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "updated_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "created_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "season": {
        "type": "TEXT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "tasks",
            "coverages",
            "player_seasons_staging",
            "team_seasons_staging",
        ],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "season_type": {
        "type": "TEXT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "tasks",
            "coverages",
            "player_seasons_staging",
            "team_seasons_staging",
        ],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "notes": {
        "type": "TEXT",
        "tables": ["teams", "players"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "identity": {
        "type": "TEXT",
        "tables": [
            "identities_entities",
            "tasks",
            "coverages",
            "teams_staging",
            "players_staging",
            "player_seasons_staging",
            "team_seasons_staging",
            "leagues_teams_staging",
            "teams_players_staging",
        ],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "entity_id": {
        "type": "BIGINT",
        "tables": ["identities_entities"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "identity_code": {
        "type": "TEXT",
        "tables": [
            "teams_staging",
            "players_staging",
            "player_seasons_staging",
            "team_seasons_staging",
            "leagues_teams_staging",
            "teams_players_staging",
        ],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "team_identity_code": {
        "type": "TEXT",
        "tables": ["players_staging", "leagues_teams_staging", "teams_players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "player_identity_code": {
        "type": "TEXT",
        "tables": ["teams_players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "matched_sts_id": {
        "type": "BIGINT",
        "tables": ["teams_staging", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "reviewed": {
        "type": "BOOLEAN",
        "tables": ["teams_staging", "players_staging"],
        "nullable": False,
        "default": False,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # ENTITY INFORMATION  (league / team / player profile data)
    # ------------------------------------------------------------------
    "name": {
        "type": "TEXT",
        "tables": [
            "leagues",
            "teams",
            "players",
            "countries",
            "teams_staging",
            "players_staging",
        ],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {
                            "field": "PLAYER",
                            "transform": "normalize_name",
                        },
                        "player_index": {
                            "derived": {
                                "concat": ["PLAYER_FIRST_NAME", "PLAYER_LAST_NAME"],
                                "separator": " ",
                            },
                            "transform": "normalize_name",
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "TEAM_NAME",
                            "transform": "normalize_name",
                        },
                    },
                },
            },
        },
    },
    "height_ins_no_shoes": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {
                            "field": "HEIGHT",
                            "transform": "parse_height",
                        },
                        "player_index": {
                            "field": "HEIGHT",
                            "transform": "parse_height",
                        },
                    },
                },
            },
        },
    },
    "height_ins_with_shoes": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "weight_lbs": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {"field": "WEIGHT"},
                        "player_index": {"field": "WEIGHT"},
                    },
                },
            },
        },
    },
    "wingspan_ins": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "combine_measurements": {
                            "field": "WINGSPAN",
                            "transform": "parse_height",
                            "multi_season": {
                                "start_year": 2003,
                                "aggregation": "most_recent_non_null",
                            },
                        },
                    },
                },
            },
        },
    },
    "hand": {
        "type": "CHAR",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "birthdate": {
        "type": "DATE",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {
                            "field": "BIRTHDATE",
                            "transform": "parse_birthdate",
                        },
                        "player_index": {
                            "field": "BIRTHDATE",
                            "transform": "parse_birthdate",
                        },
                    },
                },
            },
        },
    },
    "seasons_exp": {
        "type": "SMALLINT",
        "tables": ["teams_players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {"field": "EXP"},
                    },
                },
            },
        },
    },
    "code": {
        "type": "TEXT",
        "tables": ["leagues", "countries", "teams", "identities_entities"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "country_code": {
        "type": "TEXT",
        "tables": ["teams", "countries_players"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_index": {
                            "field": "COUNTRY",
                            "transform": "match_country",
                        },
                    },
                    "team": {
                        "team_profiles": {
                            "field": "TEAM_COUNTRY",
                            "transform": "match_country",
                        },
                    },
                },
            },
        },
    },
    "abbr": {
        "type": "TEXT",
        "tables": ["teams", "teams_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_profiles": {
                            "field": "TEAM_ABBREVIATION",
                            "transform": "safe_str",
                        },
                    },
                },
            },
        },
    },
    "conf": {
        "type": "TEXT",
        "tables": ["leagues_teams", "leagues_teams_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_profiles": {
                            "field": "TEAM_CONFERENCE",
                            "transform": "safe_str",
                        },
                    },
                },
            },
        },
    },
    "city": {
        "type": "TEXT",
        "tables": ["teams", "teams_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_profiles": {
                            "field": "TEAM_CITY",
                            "transform": "safe_str",
                        },
                    },
                },
            },
        },
    },
    "region": {
        "type": "TEXT",
        "tables": ["teams", "teams_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "identity_country": {
        "type": "TEXT",
        "tables": ["teams_staging", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "gender": {
        "type": "CHAR",
        "tables": ["leagues", "teams", "players", "teams_staging", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # GAMES & MINUTES
    # ------------------------------------------------------------------
    "games": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": False,
        "default": 0,
        "rate": "ratio",
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "GP"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "GP"},
                    },
                },
            },
        },
    },
    "mins_x10": {
        "type": "INTEGER",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": False,
        "default": 0,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "MIN"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "MIN"},
                    },
                },
            },
        },
    },
    "wins": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "W"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "W"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: 2-POINT
    # ------------------------------------------------------------------
    "fg2m_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                },
            },
        },
    },
    "fg3m_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "FG3M"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "FG3M"},
                    },
                },
            },
        },
    },
    "fg3a_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "FG3A"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "FG3A"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING: FREE THROWS
    # ------------------------------------------------------------------
    "ftm_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "FTM"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "FTM"},
                    },
                },
            },
        },
    },
    "fta_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "FTA"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "FTA"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # REBOUNDS
    # ------------------------------------------------------------------
    "o_reb_pct_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "field": "OREB_PCT",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                            "scale": 100,
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "OREB_PCT",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                            "scale": 100,
                        },
                    },
                },
            },
        },
    },
    "d_reb_pct_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "field": "DREB_PCT",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                            "scale": 100,
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "DREB_PCT",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                            "scale": 100,
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PLAYMAKING
    # ------------------------------------------------------------------
    "assists_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "AST"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "AST"},
                    },
                },
            },
        },
    },
    "pot_assists_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_tracking_stats": {
                            "field": "POTENTIAL_AST",
                            "params": {"pt_measure_type": "Passing"},
                        },
                    },
                    "team": {
                        "team_tracking_stats": {
                            "field": "POTENTIAL_AST",
                            "params": {"pt_measure_type": "Passing"},
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # BALL HANDLING
    # ------------------------------------------------------------------
    "touches_x10": {
        "type": "INTEGER",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_tracking_stats": {
                            "field": "TOUCHES",
                            "params": {"pt_measure_type": "Possessions"},
                        },
                    },
                    "team": {
                        "team_tracking_stats": {
                            "field": "TOUCHES",
                            "params": {"pt_measure_type": "Possessions"},
                        },
                    },
                },
            },
        },
    },
    "seconds_on_ball": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_tracking_stats": {
                            "field": "TIME_OF_POSS",
                            "params": {"pt_measure_type": "Possessions"},
                            "scale": 60,
                        },
                    },
                    "team": {
                        "team_tracking_stats": {
                            "field": "TIME_OF_POSS",
                            "params": {"pt_measure_type": "Possessions"},
                            "scale": 60,
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # TURNOVERS
    # ------------------------------------------------------------------
    "turnovers_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "TOV"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "TOV"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSE: STEALS / BLOCKS / FOULS
    # ------------------------------------------------------------------
    "steals_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "STL"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "STL"},
                    },
                },
            },
        },
    },
    "blocks_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "BLK"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "BLK"},
                    },
                },
            },
        },
    },
    "fouls_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {"field": "PF"},
                    },
                    "team": {
                        "team_basic_stats": {"field": "PF"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # HUSTLE STATS
    # ------------------------------------------------------------------
    "deflections_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_hustle_stats": {"field": "DEFLECTIONS"},
                    },
                    "team": {
                        "team_hustle_stats": {"field": "DEFLECTIONS"},
                    },
                },
            },
        },
    },
    "cont_d_fga_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_hustle_stats": {"field": "CONTESTED_SHOTS"},
                    },
                    "team": {
                        "team_hustle_stats": {"field": "CONTESTED_SHOTS"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # POSSESSIONS
    # ------------------------------------------------------------------
    "poss": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "field": "POSS",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "POSS",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                },
            },
        },
    },
    "o_rtg_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "field": "OFF_RTG",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "OFF_RTG",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                },
            },
        },
    },
    "d_rtg_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_basic_stats": {
                            "field": "DEF_RTG",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                    "team": {
                        "team_basic_stats": {
                            "field": "DEF_RTG",
                            "params": {"measure_type_detailed_defense": "Advanced"},
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PBP STATS
    # ------------------------------------------------------------------
    "o_fouls_drawn_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_pbp_stats": {"field": "Offensive Fouls Drawn"},
                    },
                    "team": {
                        "team_pbp_stats": {"field": "Offensive Fouls Drawn"},
                    },
                },
            },
        },
    },
    "assist_points_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_pbp_stats": {"field": "AssistPoints"},
                    },
                    "team": {
                        "team_pbp_stats": {"field": "AssistPoints"},
                    },
                },
            },
        },
    },
    "true_ft_trips_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_pbp_stats": {
                            "derived": {
                                "math": (
                                    "TwoPtShootingFoulsDrawn"
                                    " + ThreePtShootingFoulsDrawn"
                                    " + NonShootingFoulsDrawn"
                                ),
                                "fields": [
                                    "TwoPtShootingFoulsDrawn",
                                    "ThreePtShootingFoulsDrawn",
                                    "NonShootingFoulsDrawn",
                                ],
                            },
                        },
                    },
                    "team": {
                        "team_pbp_stats": {
                            "derived": {
                                "math": (
                                    "TwoPtShootingFoulsDrawn"
                                    " + ThreePtShootingFoulsDrawn"
                                    " + NonShootingFoulsDrawn"
                                ),
                                "fields": [
                                    "TwoPtShootingFoulsDrawn",
                                    "ThreePtShootingFoulsDrawn",
                                    "NonShootingFoulsDrawn",
                                ],
                            },
                        },
                    },
                },
            },
        },
    },
    "o_pace_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_pbp_stats": {"field": "SecondsPerPossOff"},
                    },
                    "team": {
                        "team_pbp_stats": {"field": "SecondsPerPossOff"},
                    },
                },
            },
        },
    },
    "d_pace_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_pbp_stats": {"field": "SecondsPerPossDef"},
                    },
                    "team": {
                        "team_pbp_stats": {"field": "SecondsPerPossDef"},
                    },
                },
            },
        },
    },
    "off_d_rtg_x10": {
        "type": "SMALLINT",
        "tables": ["player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_off_team_stats": {"field": "DEF_RTG"},
                    },
                },
            },
        },
    },
    "off_o_rtg_x10": {
        "type": "SMALLINT",
        "tables": ["player_seasons"],
        "nullable": True,
        "default": None,
        "rate": "ratio",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "player_off_team_stats": {"field": "OFF_RTG"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # ROSTER COLUMNS
    # ------------------------------------------------------------------
    "jersey_num": {
        "type": "TEXT",
        "tables": ["teams_players", "players_staging"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player": {
                        "team_player_rosters": {"field": "NUM"},
                        "player_index": {"field": "JERSEY_NUMBER"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # OPERATIONAL COLUMNS - RUNS TABLE
    # ------------------------------------------------------------------
    "pipeline": {
        "type": "TEXT",
        "tables": ["runs", "tasks"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "status": {
        "type": "TEXT",
        "tables": ["runs", "tasks"],
        "nullable": False,
        "default": "'pending'",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "completed_at": {
        "type": "TIMESTAMP",
        "tables": ["runs", "tasks", "coverages"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "total_tasks": {
        "type": "INTEGER",
        "tables": ["runs"],
        "nullable": False,
        "default": "0",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "completed_tasks": {
        "type": "INTEGER",
        "tables": ["runs"],
        "nullable": False,
        "default": "0",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "error_message": {
        "type": "TEXT",
        "tables": ["runs", "tasks"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "task_name": {
        "type": "TEXT",
        "tables": ["tasks"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "dataset": {
        "type": "TEXT",
        "tables": ["tasks", "coverages"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "tier": {
        "type": "TEXT",
        "tables": ["tasks"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "field": {
        "type": "TEXT",
        "tables": ["coverages"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "source_params": {
        "type": "TEXT",
        "tables": ["tasks", "coverages"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "dataset_params": {
        "type": "TEXT",
        "tables": ["tasks", "coverages"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "col_name": {
        "type": "TEXT",
        "tables": ["coverages"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "rows_written": {
        "type": "INTEGER",
        "tables": ["tasks"],
        "nullable": False,
        "default": "0",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "retry_count": {
        "type": "INTEGER",
        "tables": ["tasks"],
        "nullable": False,
        "default": "0",
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # REFERENCE ID COLUMNS
    # ------------------------------------------------------------------
    "player_id": {
        "type": "BIGINT",
        "tables": ["player_seasons", "teams_players", "countries_players"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "team_id": {
        "type": "BIGINT",
        "tables": ["team_seasons", "player_seasons", "teams_players", "leagues_teams"],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "league_code": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
            "teams_players",
            "team_seasons",
            "player_seasons",
            "tasks",
            "coverages",
            "teams_staging",
            "players_staging",
            "leagues_teams_staging",
            "teams_players_staging",
        ],
        "nullable": False,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    "sovereign_code": {
        "type": "TEXT",
        "tables": ["countries"],
        "nullable": True,
        "default": None,
        "rate": None,
        "scale": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # OPPONENT STATS  (team_seasons only)
    # ------------------------------------------------------------------
    "opp_fg2m_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FGM",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                },
            },
        },
    },
    "opp_fg2a_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FGA",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                        },
                    },
                },
            },
        },
    },
    "opp_fg3m_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FG3M",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_fg3a_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FG3A",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_ftm_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FTM",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_fta_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "FTA",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_assists_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "AST",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_turnovers_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "TOV",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_fouls_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "PF",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_steals_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "STL",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
    "opp_blocks_x10": {
        "type": "SMALLINT",
        "tables": ["team_seasons"],
        "nullable": True,
        "default": None,
        "rate": "counting",
        "scale": 10,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team": {
                        "team_basic_stats": {
                            "field": "BLK",
                            "params": {"measure_type_detailed_defense": "Opponent"},
                        },
                    },
                },
            },
        },
    },
}
