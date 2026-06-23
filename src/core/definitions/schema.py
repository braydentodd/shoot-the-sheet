"""
Shoot the Sheet - Database Schema Registry

Unified registry of every table and shared sequence in the database across
two schemas:

  core     — production tables (profiles, stats, rosters, ops, identities)
  staging  — temporary tables populated by ETL before promotion to core

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
    schema: str
    owner_columns: List[str]


SEQUENCES: Dict[str, SequenceDef] = {
    "core.sts_id_seq": {
        "schema": "core",
        "owner_columns": ["sts_id"],
    },
}


# ============================================================================
# TABLE DEFINITION TYPES
# ============================================================================


class FKDef(TypedDict):
    columns: List[str]
    ref_schema: str
    ref_table: str
    ref_columns: List[str]
    strategy: str
    on_update: str
    on_delete: str


class IndexDef(TypedDict):
    name: str
    columns: List[str]


class TableDef(TypedDict, total=False):
    schema: Union[str, None]
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
    "leagues": {
        "schema": "core",
        "primary_key": ["code"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    "countries": {
        "schema": "core",
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
        "schema": "core",
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
            }
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "players": {
        "schema": "core",
        "primary_key": ["sts_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — profile staging tables
    # ------------------------------------------------------------------
    "teams_staging": {
        "schema": "ext_staging",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    "players_staging": {
        "schema": "ext_staging",
        "primary_key": ["identity", "ext_id"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # STAGING — stats staging tables
    # ------------------------------------------------------------------
    "player_seasons_staging": {
        "schema": "ext_staging",
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
                "ref_schema": "ext_staging",
                "ref_table": "players_staging",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "ext_staging",
                "ref_table": "teams_staging",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "team_seasons_staging": {
        "schema": "ext_staging",
        "primary_key": ["identity", "ext_team_id", "season", "season_type"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "ext_staging",
                "ref_table": "teams_staging",
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
    "leagues_teams_staging": {
        "schema": "ext_staging",
        "primary_key": ["league_code", "identity", "ext_team_id"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "ext_staging",
                "ref_table": "teams_staging",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "teams_players_staging": {
        "schema": "ext_staging",
        "primary_key": [
            "league_code",
            "identity",
            "ext_team_id",
            "ext_player_id",
        ],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_team_id"],
                "ref_schema": "ext_staging",
                "ref_table": "teams_staging",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "ext_staging",
                "ref_table": "players_staging",
                "ref_columns": ["identity", "ext_id"],
                "strategy": "direct",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
            },
        ],
        "unique_constraints": None,
        "indexes": None,
    },
    "countries_players_staging": {
        "schema": "ext_staging",
        "primary_key": ["identity", "country_code", "ext_player_id"],
        "foreign_keys": [
            {
                "columns": ["identity", "ext_player_id"],
                "ref_schema": "ext_staging",
                "ref_table": "players_staging",
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
    # CORE — roster tables
    # ------------------------------------------------------------------
    "leagues_teams": {
        "schema": "core",
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
        "indexes": None,
    },
    "teams_players": {
        "schema": "core",
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
        "indexes": None,
    },
    "countries_players": {
        "schema": "core",
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
    "identities_entities": {
        "schema": "core",
        "primary_key": ["identity", "ext_id", "entity"],
        "foreign_keys": None,
        "unique_constraints": None,
        "indexes": None,
    },
    # ------------------------------------------------------------------
    # CORE — stats tables
    # ------------------------------------------------------------------
    "player_seasons": {
        "schema": "core",
        "primary_key": ["league_code", "player_id", "team_id", "season", "season_type"],
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
        "schema": "core",
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
    # ------------------------------------------------------------------
    # CORE — operational tables
    # ------------------------------------------------------------------
    "stat_coverages": {
        "schema": "core",
        "primary_key": [
            "identity",
            "league_code",
            "entity",
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
        ],
        "unique_constraints": None,
        "indexes": None,
    },
}
