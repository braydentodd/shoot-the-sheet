"""
Shoot the Sheet - Column Registry

Single source of truth for every database column and its identity source
mappings. Column names match the actual PostgreSQL schema exactly.

Table assignment convention
----------------------------
A column's ``tables`` list uses bare table names (e.g. ``"teams"``) when the
column belongs to that table in **every** schema where the table exists.
Schema-qualified names (``"core.teams"``) are used only when the column must
be restricted to a *subset* of schemas.

Example: ``"fg2m"`` is in ``core.player_games``, ``intermediate.player_games``, and
``staging.player_games`` → ``"tables": ["player_games"]``.
``"identity"`` is in ``staging.teams`` but NOT ``core.teams`` or
``intermediate.teams`` → ``"tables": ["staging.teams", ...]``.

This is resolved at schema-build time: ``schema_builder._column_in_table``
expands a bare name to ``{schema}.{name}`` for every schema that has a table
with that name, then compares against the (always-schema-qualified) keys from
``SCHEMAS``. See ``schema_builder.py`` for the resolution logic.

Every column with an external source follows this shape:

    dataset_mapping[league_key][identity_key][table] -> {dataset_name: DatasetMapping}

A column may be populated by more than one dataset for the same identity and
table (e.g. a box-score API and PBP accumulation both provide ``fg2m``);
first-write-wins staging semantics ensure only the first value written for a
run is kept.

Columns with no external source (system columns, or stats with no provider
yet) have ``dataset_mapping: None``.
"""

from typing import Any, Dict, FrozenSet, List, Literal, TypedDict, Union, get_args

# ============================================================================
# TYPE ALIASES
# ============================================================================

Transform = Literal[
    "safe_int",
    "safe_str",
    "null_if_zero",
    "parse_inches",
    "parse_birthdate",
    "parse_date",
    "format_season",
    "normalize_name",
    "match_country",
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
]


# ============================================================================
# DERIVED VALUE SETS
# ============================================================================

# Derived from the Transform Literal so it never drifts.
VALID_TRANSFORMS: FrozenSet[str] = frozenset(get_args(Transform))


class DatasetMapping(TypedDict, total=False):
    """Mapping from a dataset to a column value.

    Attributes:
        field: Source field name in the API response, or the accumulator
            output field name for PBP-derived stats.
        result_set: Result set name within the API response (or PBP result
            set: team, player, opp_team, opp_player, on_player).
        transform: Transform function to apply.
        scale: Multiplier for numeric values.
        params: Additional parameters for the transform.
        derived: Specification for derived/computed fields.
        cross_row: Cross-row derivation config.  When present, the value
            is not extracted per-row from the API result; instead all rows
            in the result set are grouped by ``group_by`` and the field is
            taken from the single row whose ``match_field`` contains
            ``match_contains``.  This enables values that require pairing
            two API rows (e.g. home/away team from a per-team game log)
            without storing the discriminator field in the database.

            Shape: ``{"group_by": "GAME_ID", "match_field": "MATCHUP",
                    "match_contains": "vs."}``
    """

    field: Union[str, None]
    result_set: Union[str, None]
    transform: Union[Transform, None]
    scale: Union[int, None]
    params: Union[Dict[str, Any], None]
    derived: Union[Dict[str, Any], None]
    cross_row: Union[Dict[str, Any], None]


class Column(TypedDict, total=True):
    """Complete column definition including sources.

    Attributes:
        type: PostgreSQL data type.
        tables: Table name(s) where this column appears. Bare names expand to
            all schemas that have that table; schema-qualified names
            (``"core.teams"``) restrict to that specific schema.table.
            The literal ``"all"`` wildcard applies to every table in every
            schema (reserved for ``created_at`` / ``updated_at``).
        nullable: Whether NULL values are allowed.
        default: Default value expression.
        dataset_mapping: Nested mapping: league -> identity -> table -> dataset -> field mapping.
    """

    type: str
    tables: Union[str, List[str]]
    nullable: bool
    default: Union[str, int, None]
    dataset_mapping: Union[
        Dict[str, Dict[str, Dict[str, Dict[str, DatasetMapping]]]],
        None,
    ]


DB_COLUMNS: Dict[str, Column] = {
    # ==================================================================
    # SYSTEM / IDENTITY
    # ==================================================================
    #
    # Tables involved: core.teams, core.players, intermediate.teams, intermediate.players,
    # staging.teams, staging.players.
    #
    # sts_id:        core + intermediate only (staging uses ext_id PKs)
    # identity:      staging profiles/stats + core identities/ops;
    #                NOT in core/intermediate profile tables
    # ext_id:        staging profiles + core identity mappings
    # matched_sts_id, reviewed: staging profiles only
    # ==================================================================
    "sts_id": {
        "type": "BIGINT",
        "tables": [
            "core.teams",
            "core.players",
            "intermediate.teams",
            "intermediate.players",
        ],
        "nullable": False,
        "default": "nextval('core.sts_id_seq')",
        "dataset_mapping": None,
    },
    "identity": {
        "type": "TEXT",
        "tables": [
            "identities_players",
            "identities_teams",
            "identities_games",
            "season_coverages",
            "game_coverages",
            "staging.teams",
            "staging.players",
            "staging.games",
            "staging.player_seasons",
            "staging.team_seasons",
            "staging.leagues_teams",
            "staging.teams_players",
            "staging.countries_players",
            "staging.player_games",
            "staging.team_games",
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
            "leagues_teams",
            "teams_players",
            "team_seasons",
            "player_seasons",
            "team_games",
            "player_games",
            "season_coverages",
            "game_coverages",
            "staging.teams",
            "staging.players",
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
            "season_coverages",
            "game_coverages",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "field": "seasonYear",
                            "transform": "safe_str",
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "season_type": {
        "type": "TEXT",
        "tables": [
            "games",
            "team_seasons",
            "player_seasons",
            "season_coverages",
            "game_coverages",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "derived": {
                                "field": "gameLabel",
                                "map": {
                                    "East First Round": "playoffs",
                                    "West First Round": "playoffs",
                                    "East Conf. Semifinals": "playoffs",
                                    "West Conf. Semifinals": "playoffs",
                                    "East Conf. Finals": "playoffs",
                                    "West Conf. Finals": "playoffs",
                                    "NBA Finals": "playoffs",
                                    "SoFi Play-In Tournament": "play_in",
                                },
                                "default": "regular_season",
                            },
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "date": {
        "type": "DATE",
        "tables": [
            "games",
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
                        },
                        "league_schedule": {
                            "field": "gameDateEst",
                            "transform": "parse_date",
                            "result_set": "SeasonGames",
                        },
                    }
                }
            }
        },
    },
    "game_id": {
        "type": "BIGINT",
        "tables": [
            "core.games",
            "intermediate.games",
            "identities_games",
            "game_coverages",
        ],
        "nullable": False,
        "default": "nextval('core.game_id_seq')",
        "dataset_mapping": None,
    },
    "ext_game_id": {
        "type": "TEXT",
        "tables": [
            "staging.games",
            "staging.player_games",
            "staging.team_games",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "field": "gameId",
                            "transform": "safe_str",
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "home_team_id": {
        "type": "BIGINT",
        "tables": ["core.games", "intermediate.games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "away_team_id": {
        "type": "BIGINT",
        "tables": ["core.games", "intermediate.games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "ext_home_team_id": {
        "type": "TEXT",
        "tables": ["staging.games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "field": "homeTeam_teamId",
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "ext_away_team_id": {
        "type": "TEXT",
        "tables": ["staging.games"],
        "nullable": False,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "field": "awayTeam_teamId",
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "player_id": {
        "type": "BIGINT",
        "tables": [
            "core.player_seasons",
            "intermediate.player_seasons",
            "core.player_games",
            "intermediate.player_games",
            "core.teams_players",
            "intermediate.teams_players",
            "core.countries_players",
            "identities_players",
        ],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "team_id": {
        "type": "BIGINT",
        "tables": [
            "core.team_seasons",
            "intermediate.team_seasons",
            "core.player_seasons",
            "intermediate.player_seasons",
            "core.team_games",
            "intermediate.team_games",
            "core.player_games",
            "intermediate.player_games",
            "core.teams_players",
            "intermediate.teams_players",
            "core.leagues_teams",
            "intermediate.leagues_teams",
            "identities_teams",
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
            "staging.player_games",
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
            "staging.team_games",
            "staging.player_games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ==================================================================
    # GAME METADATA
    # ==================================================================
    "ot": {
        "type": "BOOLEAN",
        "tables": [
            "games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "neutral_site": {
        "type": "BOOLEAN",
        "tables": [
            "games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "field": "isNeutral",
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    "completed": {
        "type": "BOOLEAN",
        "tables": [
            "games",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "games": {
                        "league_schedule": {
                            "derived": {
                                "field": "gameStatus",
                                "equals": 3,
                            },
                            "result_set": "SeasonGames",
                        }
                    }
                }
            }
        },
    },
    # ==================================================================
    # PROFILES
    # ==================================================================
    "name": {
        "type": "TEXT",
        "tables": [
            "leagues",
            "teams",
            "players",
            "countries",
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
                        },
                        "team_profiles": {
                            "field": "TEAM_NAME",
                            "transform": "normalize_name",
                            "result_set": "TeamInfoCommon",
                        },
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
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "conf": {
        "type": "TEXT",
        "tables": [
            "leagues_teams",
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
        "tables": ["countries"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "birthdate": {
        "type": "DATE",
        "tables": [
            "players",
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
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "jersey_num": {
        "type": "TEXT",
        "tables": [
            "teams_players",
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
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "height_ins_no_shoes": {
        "type": "SMALLINT",
        "tables": [
            "players",
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
    # ==================================================================
    # METADATA / STATUS
    # ==================================================================
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
            "leagues",
            "teams",
            "players",
        ],
        "nullable": False,
        "default": True,
        "dataset_mapping": None,
    },
    "created_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    "updated_at": {
        "type": "TIMESTAMP",
        "tables": ["all"],
        "nullable": False,
        "default": "NOW()",
        "dataset_mapping": None,
    },
    # ==================================================================
    # COVERAGE TRACKING
    # ==================================================================
    # (coverage_level removed -- split into season + game coverage)
    "target": {
        "type": "TEXT",
        "tables": ["season_coverages", "game_coverages"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "col_name": {
        "type": "TEXT",
        "tables": ["season_coverages", "game_coverages"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "covered": {
        "type": "BOOLEAN",
        "tables": ["season_coverages", "game_coverages"],
        "nullable": False,
        "default": False,
        "dataset_mapping": None,
    },
    "dataset": {
        "type": "TEXT",
        "tables": [
            "season_coverages",
            "game_coverages",
        ],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ==================================================================
    # STATS — BASIC
    # ==================================================================
    "games": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                        },
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
            "player_seasons",
            "team_seasons",
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
    # ==================================================================
    # STATS — SHOOTING
    # ==================================================================
    "fg2m": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                        }
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
                        }
                    },
                }
            }
        },
    },
    "fg2a": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
    # ==================================================================
    # STATS — REBOUNDING
    # ==================================================================
    "o_rebs": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
    # ==================================================================
    # STATS — PLAYMAKING
    # ==================================================================
    "assists": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "turnovers": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
            "player_seasons",
            "team_seasons",
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
    # ==================================================================
    # STATS — DEFENSE
    # ==================================================================
    "blocks": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
    "o_fouls_draws": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    # ==================================================================
    # STATS — HUSTLE
    # ==================================================================
    "deflections": {
        "type": "SMALLINT",
        "tables": [
            "player_seasons",
            "team_seasons",
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
            "player_seasons",
            "team_seasons",
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
    # ==================================================================
    # STATS — POSSESSION
    # ==================================================================
    "poss": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "d_poss_secs": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
    "poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_data": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "team",
                        },
                    },
                }
            }
        },
    },
    "secs_on_ball": {
        "type": "INTEGER",
        "tables": [
            "player_seasons",
            "team_seasons",
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
            "player_seasons",
            "team_seasons",
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
    # ==================================================================
    # STATS — OPPONENT
    # ==================================================================
    "opp_fg2m": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "fg2m",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "fg2m",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_fg2a": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "fg2a",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "fg2a",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_fg3m": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "fg3m",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "fg3m",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_fg3a": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "fg3a",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "fg3a",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_ftm": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "ftm",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "ftm",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_fta": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "fta",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "fta",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_o_rebs": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "o_rebs",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "o_rebs",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_d_rebs": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "d_rebs",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "d_rebs",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_turnovers": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
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
                    "player_games": {
                        "pbp_data": {
                            "field": "turnovers",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "turnovers",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_poss": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_data": {
                            "field": "poss",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "poss",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    "opp_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": ["team_seasons", "player_seasons", "team_games", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_data": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "opp_player",
                        },
                    },
                    "team_games": {
                        "pbp_data": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "opp_team",
                        },
                    },
                }
            }
        },
    },
    # ==================================================================
    # STATS — ON-COURT (player tables only)
    # ==================================================================
    "on_fg2m": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "fg2m",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_fg2a": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "fg2a",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_fg3m": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "fg3m",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_fg3a": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "fg3a",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_ftm": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "ftm",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_fta": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "fta",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_o_rebs": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "o_rebs",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_d_rebs": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "d_rebs",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_turnovers": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
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
                        "pbp_data": {
                            "field": "turnovers",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    "on_poss_ending_ft_trips": {
        "type": "SMALLINT",
        "tables": ["player_seasons", "player_games"],
        "nullable": True,
        "default": None,
        "dataset_mapping": {
            "NBA": {
                "nba_id": {
                    "player_games": {
                        "pbp_data": {
                            "field": "poss_ending_ft_trips",
                            "result_set": "on_player",
                        },
                    },
                }
            }
        },
    },
    # ==================================================================
    # ERRORS TABLE
    # ==================================================================
    "error_id": {
        "type": "BIGINT",
        "tables": ["errors"],
        "nullable": False,
        "default": "nextval('core.error_id_seq')",
        "dataset_mapping": None,
    },
    "phase": {
        "type": "VARCHAR(100)",
        "tables": ["errors"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "message": {
        "type": "TEXT",
        "tables": ["errors"],
        "nullable": False,
        "default": None,
        "dataset_mapping": None,
    },
    "traceback": {
        "type": "TEXT",
        "tables": ["errors"],
        "nullable": True,
        "default": None,
        "dataset_mapping": None,
    },
}
