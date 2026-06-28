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
    domain: Union[str, None]
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {"field": "GAME_DATE"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "GAME_DATE"},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "GAME_DATE"},
                    },
                },
            },
        },
    },
    "ext_home_team_id": {
        "type": "TEXT",
        "tables": ["games_staging"],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {"field": "TEAM_ID"},
                    },
                },
            },
        },
    },
    "ext_away_team_id": {
        "type": "TEXT",
        "tables": ["games_staging"],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {"field": "TEAM_ID"},
                    },
                },
            },
        },
    },
    "home_team_id": {
        "type": "BIGINT",
        "tables": ["games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "away_team_id": {
        "type": "BIGINT",
        "tables": ["games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "home_team_points": {
        "type": "SMALLINT",
        "tables": ["games", "games_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {"field": "PTS"},
                    },
                },
            },
        },
    },
    "away_team_points": {
        "type": "SMALLINT",
        "tables": ["games", "games_staging"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {"field": "PTS"},
                    },
                },
            },
        },
    },
    "ot": {
        "type": "BOOLEAN",
        "tables": ["games", "games_staging"],
        "nullable": False,
        "default": False,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {
                            "field": "MIN",
                            "transform": "gt",
                            "params": {"threshold": 240},
                        },
                    },
                },
            },
        },
    },
    "neutral_site": {
        "type": "BOOLEAN",
        "tables": ["games", "games_staging"],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
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
    "notes": {
        "type": "TEXT",
        "tables": ["teams", "players"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
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
    "sovereign_country": {
        "type": "TEXT",
        "tables": ["countries"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "gender": {
        "type": "CHAR",
        "tables": ["leagues", "teams", "players", "teams_staging", "players_staging"],
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
    "secs": {  # Support PBP (players: add up all seconds stints; build lineups using starting lineups + substitutions; teams: add up all minutes in game)
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
                        "player_basic_stats": {"field": "MIN", "scale": 60},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "MIN", "scale": 60},
                        "pbp_stats": {"field": "SECS", "domain": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {"field": "MIN", "scale": 60},
                    },
                    "team_games": {
                        "team_game_stats": {"field": "MIN", "scale": 60},
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "player_game_stats": {
                            "field": "WL",
                            "transform": "eq",
                            "params": {"threshold": "W"},
                        },
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "WL",
                            "transform": "eq",
                            "params": {"threshold": "W"},
                        },
                    },
                },
            },
        },
    },  # Support PBP (compare final score)
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
    "fg2m": {
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
                        "pbp_stats": {"field": "FG2M", "domain": "player"},
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
    },  # Support PBP (add up all 2pt field goal makes)
    "fg2a": {
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
                        "pbp_stats": {"field": "FG2A", "domain": "player"},
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
    },  # Support PBP (add up all 2pt field goal attempts)
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
                        "pbp_stats": {"field": "FG3M", "domain": "player"},
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
    },  # Support PBP (add up all 3pt field goal makes)
    "fg3a": {
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
                        "player_basic_stats": {"field": "FG3A"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FG3A"},
                        "pbp_stats": {"field": "FG3A", "domain": "player"},
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
    },  # Support PBP (add up all 3pt field goal attempts)
    "ftm": {
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
                        "player_basic_stats": {"field": "FTM"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FTM"},
                        "pbp_stats": {"field": "FTM", "domain": "player"},
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
    },  # Support PBP (add up all free throw makes)
    "fta": {
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
                        "player_basic_stats": {"field": "FTA"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "FTA"},
                        "pbp_stats": {"field": "FTA", "domain": "player"},
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
    },  # Support PBP (add up all free throw attempts)
    "o_rebs": {
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
                        "player_basic_stats": {"field": "OREB"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "OREB"},
                        "pbp_stats": {"field": "OREB", "domain": "player"},
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
    },  # Support PBP (add up all offensive rebounds)
    "d_rebs": {
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
                        "player_basic_stats": {"field": "DREB"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "DREB"},
                        "pbp_stats": {"field": "DREB", "domain": "player"},
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
    },  # Support PBP (add up all defensive rebounds)
    "assists": {
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
                        "player_basic_stats": {"field": "AST"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "AST"},
                        "pbp_stats": {"field": "AST", "domain": "player"},
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
    },  # Support PBP (add up all assists)
    "pot_assists": {
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
                        "player_passing_stats": {
                            "field": "POTENTIAL_AST",
                        },
                    },
                    "player_games": {
                        "pbp_stats": {"field": "POT_AST", "domain": "player"},
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
    "turnovers": {
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
                        "player_basic_stats": {"field": "TOV"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "TOV"},
                        "pbp_stats": {"field": "TOV", "domain": "player"},
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
    },  # Support PBP (add up all turnovers)
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
                        "pbp_stats": {"field": "STL", "domain": "player"},
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
    },  # Support PBP (add up all steals)
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
                        "pbp_stats": {"field": "BLK", "domain": "player"},
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
    },  # Support PBP (add up all blocks)
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
                        "pbp_stats": {"field": "PF", "domain": "player"},
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
    },  # Support PBP (add up all PF)
    "deflections": {
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
                        "player_hustle_stats": {"field": "DEFLECTIONS"},
                    },
                    "player_games": {
                        "player_game_stats": {"field": "DEFLECTIONS"},
                        "pbp_stats": {"field": "DEFL", "domain": "player"},
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
    "poss": {
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
                        "pbp_stats": {"field": "POSS", "domain": "team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all events where team had ball; follows a won tip off, defensive rebound, opposing team turnover, start of half/quarter with ball, etc... we can discuss this one further)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "OFD", "domain": "player"},
                    },
                },
            },
        },
    },  # Support PBP (players: add up all events where offense committed foul on you (charge, illegal screen, etc); teams: add up all events where opposing offense committed foul... is this supported? does pbp track which players the fouls are committed against?)
    "assist_points": {
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
                    "player_games": {
                        "pbp_stats": {"field": "AST_PTS", "domain": "player"},
                    },
                },
            },
        },
    },  # Support PBP (add up point value of all assists)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "PEFTT", "domain": "player"},
                    },
                },
            },
        },
    },  # Support PBP (add up all non-and-one free throw trips that are followed by live possession or a change of possession... if that makes sense... we can disuss this one futher)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "O_POSS_SECS", "domain": "player"},
                    },
                },
            },
        },
    },  # Support PBP (add up all secs of offensive possessions)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "O_POSS_SECS", "domain": "opp_player"},
                    },
                    "team_games": {
                        "pbp_stats": {"field": "O_POSS_SECS", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (mirrored from o_poss_secs via opponent domain)
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
                        "pbp_stats": {"field": "FG3M", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FG3M)
    "opp_fg3a": {
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
                        "team_opp_stats": {"field": "OPP_FG3A"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FG3A"},
                        "pbp_stats": {"field": "FG3A", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FG3A)
    "opp_ftm": {
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
                        "team_opp_stats": {"field": "OPP_FTM"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FTM"},
                        "pbp_stats": {"field": "FTM", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FTM)
    "opp_fta": {
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
                        "team_opp_stats": {"field": "OPP_FTA"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_FTA"},
                        "pbp_stats": {"field": "FTA", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FTA)
    "opp_o_rebs": {
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
                        "team_opp_stats": {"field": "OPP_OREB"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_OREB"},
                        "pbp_stats": {"field": "OREB", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent OREB)
    "opp_d_rebs": {
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
                        "team_opp_stats": {"field": "OPP_DREB"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_DREB"},
                        "pbp_stats": {"field": "DREB", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent DREB)
    "opp_turnovers": {
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
                        "team_opp_stats": {"field": "OPP_TOV"},
                    },
                    "team_games": {
                        "team_opp_stats": {"field": "OPP_TOV"},
                        "pbp_stats": {"field": "TOV", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent TOV)
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
                        "pbp_stats": {"field": "STL", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent STL)
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
                        "pbp_stats": {"field": "BLK", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent BLK)
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
                        "pbp_stats": {"field": "PF", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent PF)
    "opp_fg2m": {
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
                        "pbp_stats": {"field": "FG2M", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FG2A)
    "opp_fg2a": {
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
                        "pbp_stats": {"field": "FG2A", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent FG3A)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_games": {
                        "pbp_stats": {"field": "POSS", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent possessions)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_games": {
                        "pbp_stats": {"field": "OFD", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent offensivefouls drawn)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_games": {
                        "pbp_stats": {"field": "PEFTT", "domain": "opp_team"},
                    },
                },
            },
        },
    },  # Support PBP (add up all opponent possession ending FT trips)
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
                        "pbp_stats": {"field": "FG3M", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FG3M while player on the floor)
    "on_fg3a": {
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
                        "player_on_stats": {"field": "FG3A"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FG3A"},
                        "pbp_stats": {"field": "FG3A", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FG3A while player on the floor)
    "on_ftm": {
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
                        "player_on_stats": {"field": "FTM"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FTM"},
                        "pbp_stats": {"field": "FTM", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FTM while player on the floor)
    "on_fta": {
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
                        "player_on_stats": {"field": "FTA"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "FTA"},
                        "pbp_stats": {"field": "FTA", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FTA while player on the floor)
    "on_o_rebs": {
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
                        "player_on_stats": {"field": "OREB"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "OREB"},
                        "pbp_stats": {"field": "OREB", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team OREB while player on the floor)
    "on_d_rebs": {
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
                        "player_on_stats": {"field": "DREB"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "DREB"},
                        "pbp_stats": {"field": "DREB", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team DREB while player on the floor)
    "on_turnovers": {
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
                        "player_on_stats": {"field": "TOV"},
                    },
                    "player_games": {
                        "player_on_stats": {"field": "TOV"},
                        "pbp_stats": {"field": "TOV", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team TOV)
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
                        "pbp_stats": {"field": "STL", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team STL while player on the floor)
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
                        "pbp_stats": {"field": "BLK", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team BLK while player on the floor)
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
                        "pbp_stats": {"field": "PF", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team PF while player on the floor)
    "on_fg2m": {
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
                        "pbp_stats": {"field": "FG2M", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FG2M while player on the floor)
    "on_fg2a": {
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
                        "pbp_stats": {"field": "FG2A", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team FG2A while player on the floor)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "OFD", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team offensive fouls drawn while player on the floor)
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "PEFTT", "domain": "on"},
                    },
                },
            },
        },
    },  # Support PBP (add up all team possession ending FT trips while player on the floor)
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
}
