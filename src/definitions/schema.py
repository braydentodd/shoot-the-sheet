"""
Shoot the Sheet - Database Schema Registry

Unified registry of every table and shared sequence in the database across
three schemas:

  staging  — per-identity raw data from ETL ingestion (identity + ext_id keyed),
             first-write-wins within a single identity run.
  intermediate    — cross-identity merged data (first-write-wins with NULL fill),
                    preventing the production schema from flickering mid-run.
  core     — production tables (profiles, stats, rosters, ops, identities).

Tables are nested by schema so the registry reads as three parallel, directly
comparable groups. Look up a table with ``SCHEMAS[schema][table]`` or the
``get_table("schema.table")`` convenience helper.

Column definitions live in ``src.definitions.db_columns.DB_COLUMNS``. The DDL
generator looks up type, nullable, default, and other metadata from the
column registry.
"""

from typing import Dict, List, TypedDict, Union

# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

VALID_SCHEMAS = frozenset({"core", "staging", "intermediate"})

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
        ref_table: Referenced table's bare name (no schema prefix).
        ref_columns: Referenced column(s).
        strategy: FK strategy ('direct' for staging same-identity FKs,
            'profile_lookup' for core/intermediate FKs against surrogate keys).
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
    """Complete table schema definition (nested under its schema in SCHEMAS).

    Attributes:
        primary_key: Primary key column(s).
        foreign_keys: Foreign key constraints.
        unique_constraints: Unique constraint column combinations.
        indexes: Additional indexes.
    """

    primary_key: Union[List[str], None]
    foreign_keys: Union[List[FKDef], None]
    unique_constraints: Union[List[List[str]], None]
    indexes: Union[List[IndexDef], None]


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================
#
# SCHEMAS[schema_name][table_name] -> TableDef
#
# Intermediate holds only the tables that receive writes from more than one
# identity and therefore need cross-identity first-write-wins merging:
# profiles, rosters, seasons, games, and game stats. Pure mapping/reference
# tables (identities_*, countries_players) promote directly from staging to
# core with first-match-wins semantics, since they are not overwritten
# across identities.

SCHEMAS: Dict[str, Dict[str, TableDef]] = {
    # ========================================================================
    # CORE
    # ========================================================================
    "core": {
        "leagues": {
            "primary_key": ["code"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": None,
        },
        "countries": {
            "primary_key": ["code"],
            "foreign_keys": [
                {
                    "columns": ["sovereign_country"],
                    "ref_schema": "core",
                    "ref_table": "countries",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                }
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "teams": {
            "primary_key": ["sts_id"],
            "foreign_keys": [
                {
                    "columns": ["country_code"],
                    "ref_schema": "core",
                    "ref_table": "countries",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "players": {
            "primary_key": ["sts_id"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": None,
        },
        "leagues_teams": {
            "primary_key": ["league_code", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
        },
        "teams_players": {
            "primary_key": ["league_code", "team_id", "player_id"],
            "foreign_keys": [
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
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
        "countries_players": {
            "primary_key": ["country_code", "player_id"],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["country_code"],
                    "ref_schema": "core",
                    "ref_table": "countries",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "identities_players": {
            "primary_key": ["identity", "ext_id"],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": [{"name": "player_id_idx", "columns": ["player_id"]}],
        },
        "identities_teams": {
            "primary_key": ["identity", "ext_id"],
            "foreign_keys": [
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
        },
        "identities_games": {
            "primary_key": ["identity", "ext_id"],
            "foreign_keys": [
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
                    "ref_columns": ["game_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": [{"name": "game_id_idx", "columns": ["game_id"]}],
        },
        "player_seasons": {
            "primary_key": [
                "league_code",
                "player_id",
                "team_id",
                "season",
                "season_type",
            ],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "team_seasons": {
            "primary_key": ["league_code", "team_id", "season", "season_type"],
            "foreign_keys": [
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "games": {
            "primary_key": ["game_id"],
            "foreign_keys": [
                {
                    "columns": ["home_team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
                {
                    "columns": ["away_team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": [
                ["date", "home_team_id", "away_team_id"],
            ],
            "indexes": [
                {"name": "date_idx", "columns": ["date"]},
            ],
        },
        "player_games": {
            "primary_key": ["league_code", "game_id", "player_id", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
                    "ref_columns": ["game_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "team_games": {
            "primary_key": ["league_code", "game_id", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
                    "ref_columns": ["game_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "coverage": {
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
                    "ref_table": "leagues",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
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
        "errors": {
            "primary_key": ["error_id"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": [
                {"name": "idx_errors_timestamp", "columns": ["timestamp"]},
                {"name": "idx_errors_phase", "columns": ["phase"]},
                {"name": "idx_errors_identity", "columns": ["identity"]},
            ],
        },
    },
    # ========================================================================
    # STAGING — per-identity, first-write-wins within a run
    # ========================================================================
    "staging": {
        "teams": {
            "primary_key": ["identity", "ext_id"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": None,
        },
        "players": {
            "primary_key": ["identity", "ext_id"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": None,
        },
        "leagues_teams": {
            "primary_key": ["league_code", "identity", "ext_team_id"],
            "foreign_keys": [
                {
                    "columns": ["identity", "ext_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "teams_players": {
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
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_player_id"],
                    "ref_schema": "staging",
                    "ref_table": "players",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "countries_players": {
            "primary_key": ["identity", "country_code", "ext_player_id"],
            "foreign_keys": [
                {
                    "columns": ["identity", "ext_player_id"],
                    "ref_schema": "staging",
                    "ref_table": "players",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "player_seasons": {
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
                    "ref_table": "players",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "team_seasons": {
            "primary_key": ["identity", "ext_team_id", "season", "season_type"],
            "foreign_keys": [
                {
                    "columns": ["identity", "ext_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "games": {
            "primary_key": ["identity", "ext_game_id"],
            "foreign_keys": [
                {
                    "columns": ["identity", "ext_home_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_away_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "player_games": {
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
                    "ref_table": "players",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_game_id"],
                    "ref_schema": "staging",
                    "ref_table": "games",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "team_games": {
            "primary_key": [
                "identity",
                "ext_team_id",
                "ext_game_id",
            ],
            "foreign_keys": [
                {
                    "columns": ["identity", "ext_team_id"],
                    "ref_schema": "staging",
                    "ref_table": "teams",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["identity", "ext_game_id"],
                    "ref_schema": "staging",
                    "ref_table": "games",
                    "ref_columns": ["identity", "ext_id"],
                    "strategy": "direct",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
    },
    # ========================================================================
    # INTERMEDIATE — cross-identity, first-write-wins with NULL fill.
    # Only tables written by more than one identity live here; reference /
    # mapping tables promote straight from staging to core.
    # ========================================================================
    "intermediate": {
        "teams": {
            "primary_key": ["sts_id"],
            "foreign_keys": [
                {
                    "columns": ["country_code"],
                    "ref_schema": "core",
                    "ref_table": "countries",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": None,
            "indexes": None,
        },
        "players": {
            "primary_key": ["sts_id"],
            "foreign_keys": None,
            "unique_constraints": None,
            "indexes": None,
        },
        "leagues_teams": {
            "primary_key": ["league_code", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": None,
            "indexes": [{"name": "team_id_idx", "columns": ["team_id"]}],
        },
        "teams_players": {
            "primary_key": ["league_code", "team_id", "player_id"],
            "foreign_keys": [
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
                    "ref_columns": ["code"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
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
        "player_seasons": {
            "primary_key": [
                "league_code",
                "player_id",
                "team_id",
                "season",
                "season_type",
            ],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "team_seasons": {
            "primary_key": ["league_code", "team_id", "season", "season_type"],
            "foreign_keys": [
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "games": {
            "primary_key": ["game_id"],
            "foreign_keys": [
                {
                    "columns": ["home_team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
                {
                    "columns": ["away_team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": [
                ["date", "home_team_id", "away_team_id"],
            ],
            "indexes": [
                {"name": "date_idx", "columns": ["date"]},
            ],
        },
        "player_games": {
            "primary_key": ["league_code", "game_id", "player_id", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["player_id"],
                    "ref_schema": "core",
                    "ref_table": "players",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
                    "ref_columns": ["game_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
        "team_games": {
            "primary_key": ["league_code", "game_id", "team_id"],
            "foreign_keys": [
                {
                    "columns": ["team_id"],
                    "ref_schema": "core",
                    "ref_table": "teams",
                    "ref_columns": ["sts_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["game_id"],
                    "ref_schema": "core",
                    "ref_table": "games",
                    "ref_columns": ["game_id"],
                    "strategy": "profile_lookup",
                    "on_update": "CASCADE",
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["league_code"],
                    "ref_schema": "core",
                    "ref_table": "leagues",
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
    },
}


# ============================================================================
# ACCESS HELPERS
# ============================================================================


def get_table(qualified_name: str) -> TableDef:
    """Look up a table definition by ``'schema.table'`` qualified name.

    Raises ``KeyError`` if the schema or table is not registered.
    """
    schema, table = qualified_name.split(".", 1)
    return SCHEMAS[schema][table]


def iter_tables():
    """Yield ``(qualified_name, schema, table, TableDef)`` for every table."""
    for schema, tables in SCHEMAS.items():
        for table, meta in tables.items():
            yield f"{schema}.{table}", schema, table, meta
