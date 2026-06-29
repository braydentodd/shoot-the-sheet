"""
Shoot the Sheet - Column Registry

Single source of truth for database column definitions and provider source
mappings.  Column names match the actual PostgreSQL schema exactly.

Every column with an external source follows this shape:

    dataset_mapping[league_key][identity_key][target][dataset] -> DatasetMappingDef

Columns with no external source (system columns) have ``dataset_mapping: None``.
"""

from typing import Any, Dict, List, TypedDict, Union


class DatasetMappingDef(TypedDict, total=False):
    field: Union[str, None]
    result_set: Union[str, None]
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
    # ── System / identity ──
    "sts_id": {
        "type": "BIGINT",
        "tables": [
            "teams",
            "players",
        ],
        "nullable": False,
        "default": "nextval('core.sts_id_seq')",
        "dataset_mapping": None,
    },
    "entity": {
        "type": "TEXT",
        "tables": [
            "coverage",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "identity": {
        "type": "TEXT",
        "tables": [
            "identities_players",
            "identities_teams",
            "identities_games",
            "coverage",
            "teams_staging",
            "players_staging",
            "games_staging",
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
            "identities_games",
            "teams_staging",
            "players_staging",
            "games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "matched_sts_id": {
        "type": "BIGINT",
        "tables": [
            "teams_staging",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "reviewed": {
        "type": "BOOLEAN",
        "tables": [
            "teams_staging",
            "players_staging",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "league_code": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
            "teams_players",
            "team_seasons",
            "player_seasons",
            "coverage",
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
    "season": {
        "type": "TEXT",
        "tables": [
            "games",
            "team_seasons",
            "player_seasons",
            "coverage",
            "coverage",
            "games_staging",
            "player_seasons_staging",
            "team_seasons_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "season_type": {
        "type": "TEXT",
        "tables": [
            "games",
            "team_seasons",
            "player_seasons",
            "coverage",
            "coverage",
            "games_staging",
            "player_seasons_staging",
            "team_seasons_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "date": {
        "type": "DATE",
        "tables": [
            "games",
            "games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "team_game_stats": {
                            "field": "GAME_DATE",
                            "result_set": "LeagueGameLog",
                        }
                    }
                }
            }
        },
    },
    "game_id": {
        "type": "BIGINT",
        "tables": [
            "games",
            "identities_games",
            "coverage",
        ],
        "nullable": False,
        "default": "nextval('core.game_id_seq')",
        "dataset_mapping": None,
    },
    "ext_game_id": {
        "type": "TEXT",
        "tables": [
            "games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "home_team_id": {
        "type": "BIGINT",
        "tables": [
            "games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "away_team_id": {
        "type": "BIGINT",
        "tables": [
            "games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_home_team_id": {
        "type": "TEXT",
        "tables": [
            "games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "pbp_stats": {"field": "home_team_id", "result_set": "game"}
                    }
                }
            }
        },
    },
    "ext_away_team_id": {
        "type": "TEXT",
        "tables": [
            "games_staging",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "pbp_stats": {"field": "away_team_id", "result_set": "game"}
                    }
                }
            }
        },
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
    # ── Game metadata ──
    "ot": {
        "type": "BOOLEAN",
        "tables": [
            "games",
            "games_staging",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "neutral_site": {
        "type": "BOOLEAN",
        "tables": [
            "games",
            "games_staging",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "home_team_points": {
        "type": "SMALLINT",
        "tables": [
            "games",
            "games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "away_team_points": {
        "type": "SMALLINT",
        "tables": [
            "games",
            "games_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Profiles ──
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
                            "result_set": "CommonTeamRoster",
                        },
                        "player_profiles": {
                            "derived": {
                                "concat": ["PLAYER_FIRST_NAME", "PLAYER_LAST_NAME"],
                                "separator": " ",
                            },
                            "transform": "normalize_name",
                            "result_set": "PlayerIndex",
                        },
                    },
                    "teams": {
                        "team_basic_stats": {
                            "field": "TEAM_NAME",
                            "transform": "normalize_name",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                }
            }
        },
    },
    "code": {
        "type": "TEXT",
        "tables": [
            "leagues",
            "countries",
            "teams",
            "teams_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_ABBREVIATION",
                            "transform": "safe_str",
                            "result_set": "TeamInfoCommon",
                        }
                    }
                }
            }
        },
    },
    "city": {
        "type": "TEXT",
        "tables": [
            "teams",
            "teams_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_CITY",
                            "transform": "normalize_name",
                            "result_set": "TeamInfoCommon",
                        }
                    }
                }
            }
        },
    },
    "region": {
        "type": "TEXT",
        "tables": [
            "teams",
            "teams_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "conf": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
            "leagues_teams_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "leagues_teams": {
                        "team_profiles": {
                            "field": "TEAM_CONFERENCE",
                            "transform": "safe_str",
                            "result_set": "TeamInfoCommon",
                        }
                    }
                }
            }
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
                        "player_profiles": {
                            "field": "COUNTRY",
                            "transform": "match_country",
                        }
                    },
                    "teams": {
                        "team_profiles": {
                            "field": "TEAM_COUNTRY",
                            "transform": "match_country",
                            "result_set": "TeamInfoCommon",
                        }
                    },
                }
            }
        },
    },
    "sovereign_country": {
        "type": "TEXT",
        "tables": [
            "countries",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "birthdate": {
        "type": "DATE",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "teams_players_rosters": {
                            "field": "BIRTH_DATE",
                            "transform": "parse_birthdate",
                            "result_set": "CommonTeamRoster",
                        },
                        "draft_years": {
                            "field": "BIRTHDATE",
                            "transform": "parse_birthdate",
                            "result_set": "DraftBoard",
                        },
                    }
                }
            }
        },
    },
    "draft_year": {
        "type": "SMALLINT",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "player_profiles": {
                            "field": "DRAFT_YEAR",
                            "result_set": "PlayerIndex",
                        },
                        "draft_years": {"field": "SEASON", "result_set": "DraftBoard"},
                    }
                }
            }
        },
    },
    "draft_year_auto": {
        "type": "SMALLINT",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "jersey_num": {
        "type": "TEXT",
        "tables": [
            "teams_players",
            "teams_players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "teams_players": {
                        "teams_players_rosters": {
                            "field": "NUM",
                            "result_set": "CommonTeamRoster",
                        },
                        "player_profiles": {
                            "field": "JERSEY_NUMBER",
                            "result_set": "PlayerIndex",
                        },
                    }
                }
            }
        },
    },
    "hand": {
        "type": "CHAR",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "gender": {
        "type": "CHAR",
        "tables": [
            "leagues",
            "teams",
            "players",
            "teams_staging",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "height_ins_no_shoes": {
        "type": "SMALLINT",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "teams_players_rosters": {
                            "field": "HEIGHT",
                            "transform": "parse_inches",
                            "result_set": "CommonTeamRoster",
                        },
                        "player_profiles": {
                            "field": "HEIGHT",
                            "transform": "parse_inches",
                            "result_set": "PlayerIndex",
                        },
                        "combine_anthros": {
                            "field": "HEIGHT_WO_SHOES",
                            "transform": "parse_inches",
                            "result_set": "DraftCombineStats",
                        },
                    }
                }
            }
        },
    },
    "height_ins_with_shoes": {
        "type": "SMALLINT",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "combine_anthros": {
                            "field": "HEIGHT_W_SHOES",
                            "transform": "parse_inches",
                            "result_set": "DraftCombineStats",
                        }
                    }
                }
            }
        },
    },
    "wingspan_ins": {
        "type": "SMALLINT",
        "tables": [
            "players",
            "players_staging",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "players": {
                        "combine_anthros": {
                            "field": "WINGSPAN",
                            "transform": "parse_inches",
                            "result_set": "DraftCombineStats",
                        }
                    }
                }
            }
        },
    },
    # ── Metadata / status ──
    "notes": {
        "type": "TEXT",
        "tables": [
            "teams",
            "players",
        ],
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
    "created_at": {
        "type": "TIMESTAMP",
        "tables": [
            "all",
        ],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    "updated_at": {
        "type": "TIMESTAMP",
        "tables": [
            "all",
        ],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    # ── Coverage tracking ──
    "coverage_level": {
        "type": "TEXT",
        "tables": [
            "coverage",
        ],
        "nullable": False,
        "default": "season",
        "dataset_mapping": None,
    },
    "col_name": {
        "type": "TEXT",
        "tables": [
            "coverage",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "covered": {
        "type": "BOOLEAN",
        "tables": [
            "coverage",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "dataset": {
        "type": "TEXT",
        "tables": [
            "coverage",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Stats — basic ──
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
                        "player_basic_stats": {
                            "field": "GP",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "GP",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                }
            }
        },
    },
    "secs": {
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
                        "player_basic_stats": {
                            "field": "MIN",
                            "scale": 60,
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "MIN",
                            "scale": 60,
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "secs", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "MIN",
                            "scale": 60,
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "MIN",
                            "scale": 60,
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "secs", "result_set": "team"},
                    },
                }
            }
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
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "win", "result_set": "player"},
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "WL",
                            "transform": "eq",
                            "params": {"threshold": "W"},
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "win", "result_set": "team"},
                    },
                }
            }
        },
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
                        "player_basic_stats": {
                            "field": "W",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "W",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                }
            }
        },
    },
    # ── Stats — shooting ──
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
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg2m", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "derived": {
                                "math": "FGM - FG3M",
                                "fields": ["FGM", "FG3M"],
                            },
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg2m", "result_set": "team"},
                    },
                }
            }
        },
    },
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
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg2a", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "derived": {
                                "math": "FGA - FG3A",
                                "fields": ["FGA", "FG3A"],
                            },
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg2a", "result_set": "team"},
                    },
                }
            }
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
                        "player_basic_stats": {
                            "field": "FG3M",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "FG3M",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg3m", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "FG3M",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "FG3M",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg3m", "result_set": "team"},
                    },
                }
            }
        },
    },
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
                        "player_basic_stats": {
                            "field": "FG3A",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "FG3A",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg3a", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "FG3A",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "FG3A",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fg3a", "result_set": "team"},
                    },
                }
            }
        },
    },
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
                        "player_basic_stats": {
                            "field": "FTM",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "FTM",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "ftm", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "FTM",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "FTM",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "ftm", "result_set": "team"},
                    },
                }
            }
        },
    },
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
                        "player_basic_stats": {
                            "field": "FTA",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "FTA",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fta", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "FTA",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "FTA",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fta", "result_set": "team"},
                    },
                }
            }
        },
    },
    # ── Stats — rebounding ──
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
                        "player_basic_stats": {
                            "field": "OREB",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "OREB",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "o_rebs", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "OREB",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "OREB",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "o_rebs", "result_set": "team"},
                    },
                }
            }
        },
    },
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
                        "player_basic_stats": {
                            "field": "DREB",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "DREB",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "d_rebs", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "DREB",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "DREB",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "d_rebs", "result_set": "team"},
                    },
                }
            }
        },
    },
    # ── Stats — playmaking ──
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
                        "player_basic_stats": {
                            "field": "AST",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "AST",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "assists", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "AST",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "AST",
                            "result_set": "LeagueGameLog",
                        }
                    },
                }
            }
        },
    },
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
                        "pbp_stats": {"field": "assist_points", "result_set": "player"}
                    }
                }
            }
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
                        "player_basic_stats": {
                            "field": "TOV",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "TOV",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "turnovers", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "TOV",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "TOV",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "turnovers", "result_set": "team"},
                    },
                }
            }
        },
    },
    "pot_assists": {
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
                        "player_passing_stats": {
                            "field": "POTENTIAL_AST",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                    "team_seasons": {
                        "team_passing_stats": {
                            "field": "POTENTIAL_AST",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                }
            }
        },
    },
    # ── Stats — defense ──
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
                        "player_basic_stats": {
                            "field": "BLK",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "BLK",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "blocks", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "BLK",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "BLK",
                            "result_set": "LeagueGameLog",
                        }
                    },
                }
            }
        },
    },
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
                        "player_basic_stats": {
                            "field": "STL",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "STL",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "steals", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "STL",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "STL",
                            "result_set": "LeagueGameLog",
                        }
                    },
                }
            }
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
                        "player_basic_stats": {
                            "field": "PF",
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "PF",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "fouls", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_basic_stats": {
                            "field": "PF",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "PF",
                            "result_set": "LeagueGameLog",
                        }
                    },
                }
            }
        },
    },
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
                        "pbp_stats": {"field": "o_fouls_drawn", "result_set": "player"}
                    }
                }
            }
        },
    },
    # ── Stats — hustle ──
    "deflections": {
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
                        "player_hustle_stats": {
                            "field": "DEFLECTIONS",
                            "result_set": "HustleStatsPlayer",
                        }
                    },
                    "team_seasons": {
                        "team_hustle_stats": {
                            "field": "DEFLECTIONS",
                            "result_set": "HustleStatsTeam",
                        }
                    },
                }
            }
        },
    },
    "cont_d_fga": {
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
                        "player_hustle_stats": {
                            "field": "CONTESTED_SHOTS",
                            "result_set": "HustleStatsPlayer",
                        }
                    },
                    "team_seasons": {
                        "team_hustle_stats": {
                            "field": "CONTESTED_SHOTS",
                            "result_set": "HustleStatsTeam",
                        }
                    },
                }
            }
        },
    },
    # ── Stats — possession ──
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
                            "result_set": "LeagueDashPlayerStats",
                        }
                    },
                    "player_games": {
                        "player_game_stats": {
                            "field": "POSS",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "poss", "result_set": "player"},
                    },
                    "team_seasons": {
                        "team_advanced_stats": {
                            "field": "POSS",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "POSS",
                            "result_set": "LeagueGameLog",
                        },
                        "pbp_stats": {"field": "poss", "result_set": "team"},
                    },
                }
            }
        },
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {"field": "o_poss_secs", "result_set": "player"}
                    },
                    "team_games": {
                        "pbp_stats": {"field": "o_poss_secs", "result_set": "team"}
                    },
                }
            }
        },
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {
                            "field": "o_poss_secs",
                            "result_set": "opp_player",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "o_poss_secs", "result_set": "opp_team"}
                    },
                }
            }
        },
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "player",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "team",
                        }
                    },
                }
            }
        },
    },
    "secs_on_ball": {
        "type": "INTEGER",
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
                        "player_possession_stats": {
                            "field": "TIME_OF_POSS",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                    "team_seasons": {
                        "team_possession_stats": {
                            "field": "TIME_OF_POSS",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                }
            }
        },
    },
    "touches": {
        "type": "INTEGER",
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
                        "player_possession_stats": {
                            "field": "TOUCHES",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                    "team_seasons": {
                        "team_possession_stats": {
                            "field": "TOUCHES",
                            "result_set": "LeagueDashPtStats",
                        }
                    },
                }
            }
        },
    },
    # ── Stats — opponent ──
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
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "fg2m", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg2m", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "fg2a", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg2a", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_FG3M",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "fg3m", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg3m", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_FG3A",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "fg3a", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg3a", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_FTM",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "ftm", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "ftm", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_FTA",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "fta", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fta", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_OREB",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "o_rebs", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "o_rebs", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_DREB",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "d_rebs", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "d_rebs", "result_set": "opp_player"}
                    },
                }
            }
        },
    },
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
                        "team_opp_stats": {
                            "field": "OPP_TOV",
                            "result_set": "LeagueDashTeamStats",
                        }
                    },
                    "team_games": {
                        "pbp_stats": {"field": "turnovers", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "turnovers", "result_set": "opp_player"}
                    },
                }
            }
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
                        "team_opp_stats": {
                            "field": "OPP_BLK",
                            "result_set": "LeagueDashTeamStats",
                        }
                    }
                }
            }
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
                        "team_opp_stats": {
                            "field": "OPP_STL",
                            "result_set": "LeagueDashTeamStats",
                        }
                    }
                }
            }
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
                        "team_opp_stats": {
                            "field": "OPP_PF",
                            "result_set": "LeagueDashTeamStats",
                        }
                    }
                }
            }
        },
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
                        "pbp_stats": {"field": "poss", "result_set": "opp_team"}
                    },
                    "player_games": {
                        "pbp_stats": {"field": "poss", "result_set": "opp_player"}
                    },
                }
            }
        },
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "team_games": {
                        "pbp_stats": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "opp_team",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "opp_player",
                        }
                    },
                }
            }
        },
    },
    # ── Stats — on-court ──
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
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg2m", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg2a", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "FG3M",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg3m", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "FG3A",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fg3a", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "FTM",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "ftm", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "FTA",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "fta", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "OREB",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "o_rebs", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "DREB",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "d_rebs", "result_set": "on_player"}
                    },
                }
            }
        },
    },
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
                        "player_on_stats": {
                            "field": "TOV",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    },
                    "player_games": {
                        "pbp_stats": {"field": "turnovers", "result_set": "on_player"}
                    },
                }
            }
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
                        "player_on_stats": {
                            "field": "BLK",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    }
                }
            }
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
                        "player_on_stats": {
                            "field": "STL",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    }
                }
            }
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
                        "player_on_stats": {
                            "field": "PF",
                            "result_set": "PlayersOnCourtTeamPlayerOnOffDetails",
                        }
                    }
                }
            }
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
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_stats": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "on_player",
                        }
                    }
                }
            }
        },
    },
}
