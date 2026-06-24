"""
Shoot the Sheet - Column Registry

Single source of truth for database column definitions and provider source
mappings.  Column names match the actual PostgreSQL schema exactly.

Every column with an external source follows this shape:

    dataset_mapping[league_key][identity_key][entity_name][dataset_name] -> DatasetMappingDef

Columns with no external source (system columns) have ``dataset_mapping: None``.

The synthetic identity column ``sts_id`` and per-source identity
columns (e.g. ``nba_id_id``) are emitted directly by the DDL generator
(see src/core/lib/ddl.py); they are intentionally not represented here.
"""

from typing import Any, Dict, List, TypedDict, Union


class DatasetMappingDef(TypedDict, total=False):
    field: Union[str, None]
    transform: Union[str, None]
    scale: Union[int, None]
    params: Union[Dict[str, Any], None]
    derived: Union[Dict[str, Any], None]


class ColumnDef(TypedDict, total=True):
    type: str
    tables: Union[str, List[str]]
    nullable: bool
    default: Union[str, int, None]
    dataset_mapping: Union[
        Dict[str, Dict[str, Dict[str, Dict[str, DatasetMappingDef]]]],
        None,
    ]


DB_COLUMNS: Dict[str, ColumnDef] = {
    # ------------------------------------------------------------------
    # SYSTEM COLUMNS  (managed by DB / ETL engine, no provider sources)
    # ------------------------------------------------------------------
    "sts_id": {
        "type": "BIGINT",
        "tables": ["teams", "players"],
        "nullable": False,
        "default": "nextval('core.sts_id_seq')",
        "dataset_mapping": None,
    },
    "entity": {
        "type": "TEXT",
        "tables": ["season_coverages"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "updated_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    "created_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    "season": {
        "type": "TEXT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "season_coverages",
            "game_coverages",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "season_type": {
        "type": "TEXT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "season_coverages",
            "game_coverages",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "notes": {
        "type": "TEXT",
        "tables": ["teams", "players"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # STAGING IDENTITY & FK COLUMNS  (external identity / namespace / FK codes)
    # ------------------------------------------------------------------
    "identity": {
        "type": "TEXT",
        "tables": [
            "identities_players",
            "identities_teams",
            "season_coverages",
            "teams_staging",
            "players_staging",
            "player_seasons_staging",
            "team_seasons_staging",
            "leagues_teams_staging",
            "teams_players_staging",
            "countries_players_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_id": {
        "type": "TEXT",
        "tables": [
            "identities_players",
            "identities_teams",
            "teams_staging",
            "players_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "matched_sts_id": {
        "type": "BIGINT",
        "tables": ["teams_staging", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "reviewed": {
        "type": "BOOLEAN",
        "tables": ["teams_staging", "players_staging"],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "ext_team_id": {
        "type": "TEXT",
        "tables": [
            "team_seasons_staging",
            "player_seasons_staging",
            "leagues_teams_staging",
            "teams_players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_player_id": {
        "type": "TEXT",
        "tables": [
            "player_seasons_staging",
            "teams_players_staging",
            "countries_players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # REFERENCE ID COLUMNS  (core FK references)
    # ------------------------------------------------------------------
    "player_id": {
        "type": "BIGINT",
        "tables": [
            "player_seasons",
            "teams_players",
            "countries_players",
            "identities_players",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "team_id": {
        "type": "BIGINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "teams_players",
            "leagues_teams",
            "identities_teams",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "league_code": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
            "teams_players",
            "team_seasons",
            "player_seasons",
            "season_coverages",
            "teams_staging",
            "players_staging",
            "player_seasons_staging",
            "team_seasons_staging",
            "leagues_teams_staging",
            "teams_players_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "game_id": {
        "type": "BIGINT",
        "tables": ["games"],
        "nullable": False,
        "default": "nextval('core.game_id_seq')",
        "dataset_mapping": None,
    },
    "ext_game_id": {
        "type": "TEXT",
        "tables": ["games_staging"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # ENTITY INFORMATION  (league / team / player / country profile data)
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
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "teams_players_rosters": {
                            "field": "PLAYER",
                            "transform": "normalize_name",
                        },
                        "player_profiles": {
                            "derived": {
                                "concat": ["PLAYER_FIRST_NAME", "PLAYER_LAST_NAME"],
                                "separator": " ",
                            },
                            "transform": "normalize_name",
                        },
                    },
                    "teams": {
                        "team_basic_stats": {
                            "field": "TEAM_NAME",
                            "transform": "normalize_name",
                        },
                    },
                },
            },
        },
    },
    "code": {
        "type": "TEXT",
        "tables": ["leagues", "countries", "teams", "teams_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_ABBREVIATION",
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_CITY",
                            "transform": "normalize_name",
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
        "dataset_mapping": None,
    },
    "conf": {
        "type": "TEXT",
        "tables": ["leagues_teams", "leagues_teams_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "leagues_teams": {
                        "team_profiles": {
                            "field": "TEAM_CONFERENCE",
                            "transform": "safe_str",
                        },
                    },
                },
            },
        },
    },
    "country_code": {
        "type": "TEXT",
        "tables": [
            "teams",
            "countries_players",
            "countries_players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "countries_players": {
                        "countries_players": {
                            "field": "COUNTRY",
                            "transform": "match_country",
                        },
                    },
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_COUNTRY",
                            "transform": "match_country",
                        },
                    },
                },
            },
        },
    },
    "gender": {
        "type": "CHAR",
        "tables": ["leagues", "teams", "players", "teams_staging", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # PLAYER MEASUREMENTS
    # ------------------------------------------------------------------
    "height_ins_no_shoes": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "teams_players_rosters": {
                            "field": "HEIGHT",
                            "transform": "parse_inches",
                        },
                        "player_profiles": {
                            "field": "HEIGHT",
                            "transform": "parse_inches",
                        },
                        "combine_anthros": {
                            "field": "HEIGHT_WO_SHOES",
                            "transform": "parse_inches",
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "combine_anthros": {
                            "field": "HEIGHT_W_SHOES",
                            "transform": "parse_inches",
                        },
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "combine_anthros": {
                            "field": "WINGSPAN",
                            "transform": "parse_inches",
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
        "dataset_mapping": None,
    },
    "birthdate": {
        "type": "DATE",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "teams_players_rosters": {
                            "field": "BIRTH_DATE",
                            "transform": "parse_birthdate",
                        },
                        "draft_years": {
                            "field": "BIRTHDATE",
                            "transform": "parse_birthdate",
                        },
                    },
                },
            },
        },
    },
    "draft_year": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "player_profiles": {"field": "DRAFT_YEAR"},
                        "draft_years": {"field": "SEASON"},
                    },
                },
            },
        },
    },
    "draft_year_auto": {
        "type": "SMALLINT",
        "tables": ["players", "players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "active": {
        "type": "BOOLEAN",
        "tables": [
            "players",
            "players_staging",
            "teams",
            "teams_staging",
            "leagues",
            "leagues_staging",
        ],
        "nullable": False,
        "default": True,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # GAMES & MINUTES
    # ------------------------------------------------------------------
    "date": {
        "type": "DATE",
        "tables": [
            "games",
            "games_staging",
            "player_games",
            "team_games",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "games": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": False,
        "default": 0,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "GP"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "GP"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "GP"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "GP"},
                    },
                },
            },
        },
    },
    "mins": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": False,
        "default": 0,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "MIN"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "MIN"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "MIN"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "MIN"},
                    },
                },
            },
        },
    },
    "win": {
        "type": "BOOLEAN",
        "tables": [
            "player_games",
            "team_games",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "wins": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "player_seasons_staging",
            "team_seasons_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "W"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "W"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # SCORING
    # ------------------------------------------------------------------
    "fg2m": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                    "player_games": {
                        "player_game_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                    "team_games": {
                        "team_game_stats": {
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
    "fg2a": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                        },
                    },
                    "player_games": {
                        "player_game_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                        },
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                        },
                    },
                    "team_games": {
                        "team_game_stats": {
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
    "fg3m": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "FG3M"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FG3M"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "FG3M"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "FG3M"},
                    },
                },
            },
        },
    },
    "fg3a": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "FG3A"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FG3A"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "FG3A"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "FG3A"},
                    },
                },
            },
        },
    },
    "ftm": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "FTM"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FTM"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "FTM"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "FTM"},
                    },
                },
            },
        },
    },
    "fta": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "FTA"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FTA"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "FTA"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "FTA"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # REBOUNDS
    # ------------------------------------------------------------------
    "o_rebs": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "OREB"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "OREB"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "OREB"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "OREB"},
                    },
                },
            },
        },
    },
    "d_rebs": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "DREB"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "DREB"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "DREB"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "DREB"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PLAYMAKING
    # ------------------------------------------------------------------
    "assists": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "AST"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "AST"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "AST"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "AST"},
                    },
                },
            },
        },
    },
    "pot_assists": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_passing_stats": {
                            "field": "POTENTIAL_AST",
                        },
                    },
                    "team_seasons": {
                        "team_passing_stats": {
                            "field": "POTENTIAL_AST",
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # BALL HANDLING
    # ------------------------------------------------------------------
    "touches": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_possession_stats": {
                            "field": "TOUCHES",
                        },
                    },
                    "team_seasons": {
                        "team_possession_stats": {
                            "field": "TOUCHES",
                        },
                    },
                },
            },
        },
    },
    "secs_on_ball": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_possession_stats": {
                            "field": "TIME_OF_POSS",
                        },
                    },
                    "team_seasons": {
                        "team_possession_stats": {
                            "field": "TIME_OF_POSS",
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # TURNOVERS
    # ------------------------------------------------------------------
    "turnovers": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "TOV"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "TOV"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "TOV"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "TOV"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # DEFENSE
    # ------------------------------------------------------------------
    "steals": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "STL"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "STL"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "STL"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "STL"},
                    },
                },
            },
        },
    },
    "blocks": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "BLK"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "BLK"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "BLK"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "BLK"},
                    },
                },
            },
        },
    },
    "fouls": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_basic_stats": {"field": "PF"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "PF"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "PF"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "PF"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # HUSTLE
    # ------------------------------------------------------------------
    "deflections": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_hustle_stats": {"field": "DEFLECTIONS"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "DEFLECTIONS"},
                    },
                    "team_seasons": {
                        "team_hustle_stats": {"field": "DEFLECTIONS"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "DEFLECTIONS"},
                    },
                },
            },
        },
    },
    "cont_d_fga": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_hustle_stats": {"field": "CONTESTED_SHOTS"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "CONTESTED_SHOTS"},
                    },
                    "team_seasons": {
                        "team_hustle_stats": {"field": "CONTESTED_SHOTS"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "CONTESTED_SHOTS"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # POSSESSIONS
    # ------------------------------------------------------------------
    "poss": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_advanced_stats": {
                            "field": "POSS",
                        },
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "POSS",
                        },
                    },
                    "team_seasons": {
                        "team_advanced_stats": {
                            "field": "POSS",
                        },
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "POSS",
                        },
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # PBP STATS  (play-by-play — sources TBD)
    # ------------------------------------------------------------------
    "o_fouls_drawn": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "assist_points": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "o_poss_secs": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "d_poss_secs": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # OPPONENT STATS  (team)
    # ------------------------------------------------------------------
    "opp_fg3m": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_FG3M"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FG3M"},
                    },
                },
            },
        },
    },
    "opp_fg3a": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_FG3A"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FG3A"},
                    },
                },
            },
        },
    },
    "opp_ftm": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_FTM"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FTM"},
                    },
                },
            },
        },
    },
    "opp_fta": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_FTA"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FTA"},
                    },
                },
            },
        },
    },
    "opp_o_rebs": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_OREB"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_OREB"},
                    },
                },
            },
        },
    },
    "opp_d_rebs": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_DREB"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_DREB"},
                    },
                },
            },
        },
    },
    "opp_turnovers": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_TOV"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_TOV"},
                    },
                },
            },
        },
    },
    "opp_steals": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_STL"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_STL"},
                    },
                },
            },
        },
    },
    "opp_blocks": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_BLK"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_BLK"},
                    },
                },
            },
        },
    },
    "opp_fouls": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {"field": "OPP_PF"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_PF"},
                    },
                },
            },
        },
    },
    "opp_fg2m": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["OPP_FGM", "OPP_FG3M"],
                            },
                        },
                    },
                    "team_games": {
                        "team_opp_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["OPP_FGM", "OPP_FG3M"],
                            },
                        },
                    },
                },
            },
        },
    },
    "opp_fg2a": {
        "type": "INTEGER",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_seasons": {
                        "team_opp_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["OPP_FGA", "OPP_FG3A"],
                            },
                        },
                    },
                    "team_games": {
                        "team_opp_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["OPP_FGA", "OPP_FG3A"],
                            },
                        },
                    },
                },
            },
        },
    },
    "opp_poss": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_o_fouls_drawn": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "player_seasons_staging",
            "team_seasons_staging",
            "player_games_staging",
            "team_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # ON-COURT STATS  (player)
    # ------------------------------------------------------------------
    "on_fg3m": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "FG3M"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FG3M"},
                    },
                },
            },
        },
    },
    "on_fg3a": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "FG3A"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FG3A"},
                    },
                },
            },
        },
    },
    "on_ftm": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "FTM"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FTM"},
                    },
                },
            },
        },
    },
    "on_fta": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "FTA"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FTA"},
                    },
                },
            },
        },
    },
    "on_o_rebs": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "OREB"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "OREB"},
                    },
                },
            },
        },
    },
    "on_d_rebs": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "DREB"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "DREB"},
                    },
                },
            },
        },
    },
    "on_turnovers": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "TOV"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "TOV"},
                    },
                },
            },
        },
    },
    "on_steals": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "STL"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "STL"},
                    },
                },
            },
        },
    },
    "on_blocks": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "BLK"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "BLK"},
                    },
                },
            },
        },
    },
    "on_fouls": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {"field": "PF"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "PF"},
                    },
                },
            },
        },
    },
    "on_fg2m": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                        },
                    },
                    "player_games": {
                        "player_on_stats": {
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
    "on_fg2a": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_seasons": {
                        "player_on_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                        },
                    },
                    "player_games": {
                        "player_on_stats": {
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
    "on_o_fouls_drawn": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "on_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "player_games",
            "player_seasons_staging",
            "player_games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ------------------------------------------------------------------
    # ROSTER COLUMNS
    # ------------------------------------------------------------------
    "jersey_num": {
        "type": "TEXT",
        "tables": ["teams_players", "teams_players_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams_players": {
                        "teams_players_rosters": {"field": "NUM"},
                        "player_profiles": {"field": "JERSEY_NUMBER"},
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # OPERATIONAL  (coverage / tracking)
    # ------------------------------------------------------------------
    "dataset": {
        "type": "TEXT",
        "tables": ["season_coverages"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "col_name": {
        "type": "TEXT",
        "tables": ["season_coverages"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "completed_at": {
        "type": "TIMESTAMP",
        "tables": ["season_coverages"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "sovereign_country": {
        "type": "TEXT",
        "tables": ["countries"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
}
