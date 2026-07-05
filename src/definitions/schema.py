"""
Shoot the Sheet - Database Schema Registry

Unified registry of every table and shared sequence in the database across
three schemas:

  staging  — raw source data from ETL ingestion (ext_id keyed)
  ready    — cleaned, validated data ready for promotion (source_priority tracked)
  core     — production tables (profiles, stats, rosters, ops, identities)

Column definitions live in ``src.core.definitions.db_columns.DB_COLUMNS``.
The DDL generator looks up type, nullable, default, and other metadata from
the column registry.
"""

from typing import Dict, List, TypedDict, Union

# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

VALID_PG_TYPES = frozenset(
    {
        "SERIAL",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "VARCHAR",
        "TEXT",
        "CHAR",
        "BOOLEAN",
        "TIMESTAMP",
        "DATE",
        "NUMERIC",
        "REAL",
        "DOUBLE PRECISION",
    }
)
VALID_FK_ACTIONS = frozenset({"CASCADE", "RESTRICT", "SET NULL", "NO ACTION"})
VALID_FK_STRATEGIES = frozenset({"direct", "profile_lookup"})

# Default transform per PostgreSQL base type, applied when a source does not
# declare its own ``transform`` and is not a pipeline / multi-call shape.
DEFAULT_TYPE_TRANSFORMS: Dict[str, str] = {
    "SMALLINT": "safe_int",
    "INTEGER": "safe_int",
    "BIGINT": "safe_int",
    "VARCHAR": "safe_str",
    "TEXT": "safe_str",
    "CHAR": "safe_str",
}


# ============================================================================
# SEQUENCE REGISTRY
# ============================================================================


class SequenceDef(TypedDict):
    """PostgreSQL sequence definition.

    Attributes:
        schema: Schema where sequence lives (e.g., 'core').
        owner_columns: Columns that use this sequence as default.
    """

    schema: str
    owner_columns: List[str]


SEQUENCES: Dict[str, SequenceDef] = {
    "core.sts_id_seq": {
        "schema": "core",
        "owner_columns": ["sts_id"],
    },
    "core.game_id_seq": {
        "schema": "core",
        "owner_columns": ["game_id"],
    },
    "core.error_id_seq": {
        "schema": "core",
        "owner_columns": ["error_id"],
    },
}


# ============================================================================
# TABLE DEFINITION TYPES
# ============================================================================


class FKDef(TypedDict):
    """Foreign key constraint definition.

    Attributes:
        columns: Column(s) in this table.
        ref_schema: Referenced table's schema.
        ref_table: Referenced table name.
        ref_columns: Referenced column(s).
        strategy: FK strategy ('simple' for direct FK).
        on_update: Action on referenced row update.
        on_delete: Action on referenced row delete.
    """

    columns: List[str]
    ref_schema: str
    ref_table: str
    ref_columns: List[str]
    strategy: str
    on_update: str
    on_delete: str


class IndexDef(TypedDict):
    """Database index definition.

    Attributes:
        name: Index name.
        columns: Column(s) to index.
    """

    name: str
    columns: List[str]


class TableDef(TypedDict, total=False):
    """Complete table schema definition.

    Attributes:
        schema: Schema name (e.g., 'core', 'staging', 'ready').
        name: Table name override (defaults to dict key if omitted).
        primary_key: Primary key column(s).
        foreign_keys: Foreign key constraints.
        unique_constraints: Unique constraint column combinations.
        indexes: Additional indexes.
    """

    schema: Union[str, None]
    name: Union[str, None]
    primary_key: Union[List[str], None]
    foreign_keys: Union[List[FKDef], None]
    unique_constraints: Union[List[List[str]], None]
    indexes: Union[List[IndexDef], None]


# ============================================================================
# TABLE REGISTRY
# ============================================================================

TABLES: Dict[str, TableDef] = {
    # ------------------------------------------------------------------
    # CORE — profile tables
    # ------------------------------------------------------------------
    "core.leagues": {
        "schema": "core",
        "primary_key": ["code"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    "core.countries": {
        "schema": "core",
        "primary_key": ["code"],
        "foreign_keys": [
            {
                "columns": ["sovereign_country"],
                "ref_schema": "core",
                "ref_table": "core.countries",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            }
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "core.teams": {
        "schema": "core",
        "primary_key": ["sts_id"],
        "foreign_keys": [
            {
                "columns": ["country_code"],
                "ref_schema": "core",
                "ref_table": "core.countries",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "core.players": {
        "schema": "core",
        "primary_key": ["sts_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # CORE — roster tables
    # ------------------------------------------------------------------
    "core.leagues_teams": {
        "schema": "core",
        "primary_key": ["league_code", "team_id"],
        "foreign_keys": [
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
    },
    "core.teams_players": {
        "schema": "core",
        "primary_key": ["league_code", "team_id", "player_id"],
        "foreign_keys": [
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "team_id_idx", "columns": ["team_id"]},
            {"name": "player_id_idx", "columns": ["player_id"]},
        ],
    },
    "core.countries_players": {
        "schema": "core",
        "primary_key": ["country_code", "player_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["country_code"],
                "ref_schema": "core",
                "ref_table": "core.countries",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "core.identities_players": {
        "schema": "core",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "player_id_idx", "columns": ["player_id"]}],
    },
    "core.identities_teams": {
        "schema": "core",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
    },
    "core.identities_games": {
        "schema": "core",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "game_id_idx", "columns": ["game_id"]}],
    },
    # ------------------------------------------------------------------
    # CORE — stats tables
    # ------------------------------------------------------------------
    "core.player_seasons": {
        "schema": "core",
        "primary_key": ["league_code", "player_id", "team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "season_type_season", "columns": ["season_type", "season"]},
        ],
    },
    "core.team_seasons": {
        "schema": "core",
        "primary_key": ["league_code", "team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "season_type_season", "columns": ["season_type", "season"]},
        ],
    },
    # ------------------------------------------------------------------
    # CORE — operational tables
    # ------------------------------------------------------------------
    "core.games": {
        "schema": "core",
        "primary_key": ["game_id"],
        "foreign_keys": [
            {
                "columns": ["home_team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
            {
                "columns": ["away_team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
        ],
        "unique_constraints": [
            [
                "date",
                "home_team_id",
                "away_team_id",
            ],
        ],
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    # ------------------------------------------------------------------
    # CORE — game stats tables
    # ------------------------------------------------------------------
    "core.player_games": {
        "schema": "core",
        "primary_key": ["league_code", "game_id", "player_id", "team_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    "core.team_games": {
        "schema": "core",
        "primary_key": ["league_code", "game_id", "team_id"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    "core.coverage": {
        "schema": "core",
        "primary_key": [
            "identity",
            "league_code",
            "coverage_level",
            "game_id",
            "target",
            "season",
            "season_type",
            "dataset",
            "col_name",
        ],
        "foreign_keys": [
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "covered_idx", "columns": ["covered"]},
        ],
    },
    # ------------------------------------------------------------------
    # STAGING — profile staging tables
    # ------------------------------------------------------------------
    "staging.teams": {
        "schema": "staging",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.players": {
        "schema": "staging",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — stats staging tables
    # ------------------------------------------------------------------
    "staging.player_seasons": {
        "schema": "staging",
        "primary_key": [
            "identity",
            "ext_player_id",
            "ext_team_id",
            "season",
            "season_type",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "staging",
                "ref_table": "core.players",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.team_seasons": {
        "schema": "staging",
        "primary_key": ["identity", "ext_team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — roster staging tables
    # ------------------------------------------------------------------
    "staging.leagues_teams": {
        "schema": "staging",
        "primary_key": ["league_code", "identity", "ext_team_id"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.teams_players": {
        "schema": "staging",
        "primary_key": [
            "league_code",
            "identity",
            "ext_team_id",
            "ext_player_id",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "staging",
                "ref_table": "core.players",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.countries_players": {
        "schema": "staging",
        "primary_key": ["identity", "country_code", "ext_player_id"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "staging",
                "ref_table": "core.players",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — game staging
    # ------------------------------------------------------------------
    "staging.games": {
        "schema": "staging",
        "primary_key": ["identity", "ext_game_id"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_home_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_away_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — game stats staging
    # ------------------------------------------------------------------
    "staging.player_games": {
        "schema": "staging",
        "primary_key": [
            "identity",
            "ext_player_id",
            "ext_team_id",
            "ext_game_id",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "staging",
                "ref_table": "core.players",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_game_id"],
                "ref_schema": "staging",
                "ref_table": "core.games",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.team_games": {
        "schema": "staging",
        "primary_key": [
            "identity",
            "ext_team_id",
            "ext_game_id",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "staging",
                "ref_table": "core.teams",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_game_id"],
                "ref_schema": "staging",
                "ref_table": "core.games",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "staging.pbp_events": {
        "schema": "staging",
        "primary_key": [
            "identity",
            "ext_game_id",
            "event_num",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_game_id"],
                "ref_schema": "staging",
                "ref_table": "core.games",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # READY — profile ready tables
    # ------------------------------------------------------------------
    "ready.teams": {
        "schema": "ready",
        "primary_key": ["sts_id"],
        "foreign_keys": [
            {
                "columns": ["country_code"],
                "ref_schema": "core",
                "ref_table": "core.countries",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "ready.players": {
        "schema": "ready",
        "primary_key": ["sts_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # READY — roster ready tables
    # ------------------------------------------------------------------
    "ready.leagues_teams": {
        "schema": "ready",
        "primary_key": ["league_code", "team_id"],
        "foreign_keys": [
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
    },
    "ready.teams_players": {
        "schema": "ready",
        "primary_key": ["league_code", "team_id", "player_id"],
        "foreign_keys": [
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "team_id_idx", "columns": ["team_id"]},
            {"name": "player_id_idx", "columns": ["player_id"]},
        ],
    },
    "ready.countries_players": {
        "schema": "ready",
        "primary_key": ["country_code", "player_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["country_code"],
                "ref_schema": "core",
                "ref_table": "core.countries",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "ready.identities_players": {
        "schema": "ready",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "player_id_idx", "columns": ["player_id"]}],
    },
    "ready.identities_teams": {
        "schema": "ready",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
    },
    "ready.identities_games": {
        "schema": "ready",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": [
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [{"name": "game_id_idx", "columns": ["game_id"]}],
    },
    # ------------------------------------------------------------------
    # READY — stats ready tables
    # ------------------------------------------------------------------
    "ready.player_seasons": {
        "schema": "ready",
        "primary_key": ["league_code", "player_id", "team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "season_type_season", "columns": ["season_type", "season"]},
        ],
    },
    "ready.team_seasons": {
        "schema": "ready",
        "primary_key": ["league_code", "team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "season_type_season", "columns": ["season_type", "season"]},
        ],
    },
    # ------------------------------------------------------------------
    # READY — operational ready tables
    # ------------------------------------------------------------------
    "ready.games": {
        "schema": "ready",
        "primary_key": ["game_id"],
        "foreign_keys": [
            {
                "columns": ["home_team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
            {
                "columns": ["away_team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "SET NULL",
            },
        ],
        "unique_constraints": [
            [
                "date",
                "home_team_id",
                "away_team_id",
            ],
        ],
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    # ------------------------------------------------------------------
    # READY — game stats ready tables
    # ------------------------------------------------------------------
    "ready.player_games": {
        "schema": "ready",
        "primary_key": ["league_code", "game_id", "player_id", "team_id"],
        "foreign_keys": [
            {
                "columns": ["player_id"],
                "ref_schema": "core",
                "ref_table": "core.players",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    "ready.team_games": {
        "schema": "ready",
        "primary_key": ["league_code", "game_id", "team_id"],
        "foreign_keys": [
            {
                "columns": ["team_id"],
                "ref_schema": "core",
                "ref_table": "core.teams",
                "ref_columns": ["sts_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["league_code"],
                "ref_schema": "core",
                "ref_table": "core.leagues",
                "ref_columns": ["code"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": [
            {"name": "date_idx", "columns": ["date"]},
        ],
    },
    "ready.pbp_events": {
        "schema": "ready",
        "primary_key": [
            "identity",
            "ext_game_id",
            "event_num",
        ],
        "foreign_keys": [
            {
                "columns": ["game_id"],
                "ref_schema": "core",
                "ref_table": "core.games",
                "ref_columns": ["game_id"],
                "strategy": "profile_lookup",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # CORE — operational tables
    # ------------------------------------------------------------------
    "core.errors": {
        "schema": "core",
        "primary_key": ["error_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": [
            {"name": "idx_errors_timestamp", "columns": ["timestamp"]},
            {"name": "idx_errors_phase", "columns": ["phase"]},
            {"name": "idx_errors_identity", "columns": ["identity"]},
        ],
    },
}
