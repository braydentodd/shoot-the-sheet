"""
Shoot the Sheet - Column Registry

Single source of truth for database column definitions and provider source
mappings.  Column names match the actual PostgreSQL schema exactly.

Every column with an external source follows this shape:

    dataset_mapping[league_key][identity_key][target][dataset] -> DatasetMappingDef

Columns with no external source (system columns) have ``dataset_mapping: None``.
"""

from typing import Any, Dict, List, Literal, TypedDict, Union

# ============================================================================
# TYPE ALIASES
# ============================================================================

TransformT = Literal[
    "safe_int",
    "safe_str",
    "normalize_name",
    "parse_inches",
    "parse_birthdate",
    "match_country",
    "eq",
]


class DatasetMappingDef(TypedDict, total=False):
    """Mapping from a dataset to a column value.

    Attributes:
        field: Source field name in the API response.
        result_set: Result set name within the API response.
        transform: Transform function to apply.
        scale: Multiplier for numeric values.
        params: Additional parameters for the transform.
        derived: Specification for derived/computed fields.
    """

    field: Union[str, None]
    result_set: Union[str, None]
    transform: Union[TransformT, None]
    scale: Union[int, None]
    params: Union[Dict[str, Any], None]
    derived: Union[Dict[str, Any], None]


class ColumnDef(TypedDict, total=True):
    """Complete column definition including sources.

    Attributes:
        type: PostgreSQL data type.
        tables: Table name(s) where this column appears.
        nullable: Whether NULL values are allowed.
        default: Default value expression.
        dataset_mapping: Nested mapping: league -> identity -> entity -> dataset -> field mapping.
    """

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
            "core.teams",
            "core.players",
        ],
        "nullable": False,
        "default": "nextval('core.sts_id_seq')",
        "dataset_mapping": None,
    },
    "entity": {
        "type": "TEXT",
        "tables": [
            "core.coverage",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "identity": {
        "type": "TEXT",
        "tables": [
            "core.identities_players",
            "core.identities_teams",
            "core.identities_games",
            "core.coverage",
            "staging.teams",
            "staging.players",
            "staging.games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.leagues_teams",
            "staging.teams_players",
            "staging.countries_players",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "last_identity": {
        "type": "TEXT",
        "tables": [
            "ready.teams",
            "ready.players",
            "ready.leagues_teams",
            "ready.teams_players",
            "ready.countries_players",
            "ready.identities_players",
            "ready.identities_teams",
            "ready.identities_games",
            "ready.player_seasons",
            "ready.team_seasons",
            "ready.games",
            "ready.player_games",
            "ready.team_games",
            "ready.pbp_events",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_id": {
        "type": "TEXT",
        "tables": [
            "core.identities_players",
            "core.identities_teams",
            "core.identities_games",
            "staging.teams",
            "staging.players",
            "staging.games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "matched_sts_id": {
        "type": "BIGINT",
        "tables": [
            "staging.teams",
            "staging.players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "reviewed": {
        "type": "BOOLEAN",
        "tables": [
            "staging.teams",
            "staging.players",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "league_code": {
        "type": "TEXT",
        "tables": [
            "core.leagues_teams",
            "core.teams_players",
            "core.team_seasons",
            "core.player_seasons",
            "core.coverage",
            "staging.teams",
            "staging.players",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.leagues_teams",
            "staging.teams_players",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "season": {
        "type": "TEXT",
        "tables": [
            "core.games",
            "core.team_seasons",
            "core.player_seasons",
            "core.coverage",
            "core.coverage",
            "staging.games",
            "staging.player_seasons",
            "staging.team_seasons",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "season_type": {
        "type": "TEXT",
        "tables": [
            "core.games",
            "core.team_seasons",
            "core.player_seasons",
            "core.coverage",
            "core.coverage",
            "staging.games",
            "staging.player_seasons",
            "staging.team_seasons",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "date": {
        "type": "DATE",
        "tables": [
            "core.games",
            "staging.games",
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
            "core.games",
            "core.identities_games",
            "core.coverage",
        ],
        "nullable": False,
        "default": "nextval('core.game_id_seq')",
        "dataset_mapping": None,
    },
    "ext_game_id": {
        "type": "TEXT",
        "tables": [
            "staging.games",
            "staging.pbp_events",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "home_team_id": {
        "type": "BIGINT",
        "tables": [
            "core.games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "away_team_id": {
        "type": "BIGINT",
        "tables": [
            "core.games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_home_team_id": {
        "type": "TEXT",
        "tables": [
            "staging.games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_away_team_id": {
        "type": "TEXT",
        "tables": [
            "staging.games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "player_id": {
        "type": "BIGINT",
        "tables": [
            "core.player_seasons",
            "core.teams_players",
            "core.countries_players",
            "core.identities_players",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "team_id": {
        "type": "BIGINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.teams_players",
            "core.leagues_teams",
            "core.identities_teams",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_player_id": {
        "type": "TEXT",
        "tables": [
            "staging.player_seasons",
            "staging.teams_players",
            "staging.countries_players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── PBP event columns ──
    "event_id": {
        "type": "INTEGER",
        "tables": [
            "staging.pbp_events",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "secs": {
        "type": "INTEGER",
        "tables": [
            "staging.pbp_events",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "event_type": {
        "type": "TEXT",
        "tables": [
            "staging.pbp_events",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "pbp_ext_team_id": {
        "type": "TEXT",
        "tables": [
            "staging.pbp_events",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "pbp_ext_player_id": {
        "type": "TEXT",
        "tables": [
            "staging.pbp_events",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_team_id": {
        "type": "TEXT",
        "tables": [
            "staging.team_seasons",
            "staging.player_seasons",
            "staging.leagues_teams",
            "staging.teams_players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Game metadata ──
    "ot": {
        "type": "BOOLEAN",
        "tables": [
            "core.games",
            "staging.games",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "neutral_site": {
        "type": "BOOLEAN",
        "tables": [
            "core.games",
            "staging.games",
        ],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    # ── Profiles ──
    "name": {
        "type": "TEXT",
        "tables": [
            "core.leagues",
            "core.teams",
            "core.players",
            "core.countries",
            "staging.teams",
            "staging.players",
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
            "core.leagues",
            "core.countries",
            "core.teams",
            "staging.teams",
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
            "core.teams",
            "staging.teams",
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
            "core.teams",
            "staging.teams",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "conf": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
            "staging.leagues_teams",
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
            "core.teams",
            "core.countries_players",
            "staging.countries_players",
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
                            "result_set": "PlayerIndex",
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
            "core.players",
            "staging.players",
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
            "core.players",
            "staging.players",
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
            "core.players",
            "staging.players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "jersey_num": {
        "type": "TEXT",
        "tables": [
            "core.teams_players",
            "staging.teams_players",
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
            "core.players",
            "staging.players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "gender": {
        "type": "CHAR",
        "tables": [
            "core.leagues",
            "core.teams",
            "core.players",
            "staging.teams",
            "staging.players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "height_ins_no_shoes": {
        "type": "SMALLINT",
        "tables": [
            "core.players",
            "staging.players",
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
            "core.players",
            "staging.players",
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
            "core.players",
            "staging.players",
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
            "core.teams",
            "core.players",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "active": {
        "type": "BOOLEAN",
        "tables": [
            "core.players",
            "staging.players",
            "core.teams",
            "staging.teams",
            "core.leagues",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "win": {
        "type": "BOOLEAN",
        "tables": [
            "core.player_games",
            "core.team_games",
            "staging.player_games",
            "staging.team_games",
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
                    },
                    "team_games": {
                        "team_game_stats": {
                            "field": "WL",
                            "transform": "eq",
                            "params": {"threshold": "W"},
                            "result_set": "LeagueGameLog",
                        },
                    },
                }
            }
        },
    },
    "wins": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "fg2a": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "fg3m": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "fg3a": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "ftm": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "fta": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    # ── Stats — rebounding ──
    "o_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "d_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    # ── Stats — playmaking ──
    "assists": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                        },
                    },
                }
            }
        },
    },
    "assist_points": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "turnovers": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "pot_assists": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                        },
                    },
                }
            }
        },
    },
    "steals": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                        },
                    },
                }
            }
        },
    },
    "fouls": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                        },
                    },
                }
            }
        },
    },
    "o_fouls_drawn": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Stats — hustle ──
    "deflections": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                    },
                }
            }
        },
    },
    "o_poss_secs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "d_poss_secs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "secs_on_ball": {
        "type": "INTEGER",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "staging.player_seasons",
            "staging.team_seasons",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_fg2a": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_fg3m": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_fg3a": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_ftm": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_fta": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_o_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_d_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_turnovers": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
                }
            }
        },
    },
    "opp_blocks": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
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
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_poss": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "core.team_seasons",
            "core.player_seasons",
            "core.team_games",
            "core.player_games",
            "ready.team_seasons",
            "ready.player_seasons",
            "ready.team_games",
            "ready.player_games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Stats — on-court ──
    "on_fg2m": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_fg2a": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_fg3m": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_fg3a": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_ftm": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_fta": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_o_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_d_rebs": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_turnovers": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
                }
            }
        },
    },
    "on_blocks": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
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
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "on_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": [
            "core.player_seasons",
            "core.player_games",
            "ready.player_seasons",
            "ready.player_games",
            "staging.player_seasons",
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Stats — player PBP ──
    "player_fg2m": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_fg2a": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_fg3m": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_fg3a": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_ftm": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_fta": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_o_rebs": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_d_rebs": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_turnovers": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_poss_ending_ft_trips": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "player_secs": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ── Stats — opponent player PBP ──
    "opp_player_fg2m": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_fg2a": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_fg3m": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_fg3a": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_ftm": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_fta": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_o_rebs": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_d_rebs": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_turnovers": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "opp_player_poss_ending_ft_trips": {
        "type": "INTEGER",
        "tables": [
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
}
