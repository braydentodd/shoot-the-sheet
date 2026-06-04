"""
The Glass - Database Schema Registry

Unified registry of every table and shared sequence in the database:
profiles, stats, rosters, and operational (run-tracking) tables.

Operational tables use a ``pipeline`` discriminator column so both ETL and
publish runs share single ``runs`` and ``tasks`` tables rather than
maintaining four mirrored tables.

Column definitions live in ``src.core.definitions.db_columns.DB_COLUMNS``.
Operational and roster tables reference columns by name; the DDL generator
looks up type, nullable, default, and other metadata from the column registry.
"""

from typing import TypedDict, Dict, List, Union


# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

VALID_PG_TYPES = frozenset({
    'SERIAL', 'SMALLINT', 'INTEGER', 'BIGINT', 'VARCHAR', 'TEXT', 'CHAR',
    'BOOLEAN', 'TIMESTAMP', 'DATE', 'NUMERIC', 'REAL', 'DOUBLE PRECISION',
})
VALID_REFRESH_MODES = frozenset({'null_only', 'always'})
VALID_FK_ACTIONS = frozenset({'CASCADE', 'RESTRICT', 'SET NULL', 'NO ACTION'})
VALID_MANAGERS = frozenset({'db', 'execution_context', 'in_season_source', 'perennial_source'})
VALID_FK_STRATEGIES = frozenset({'direct', 'profile_lookup'})

THE_GLASS_ID = 'the_glass_id'

# Default transform per PostgreSQL base type, applied when a source does not
# declare its own ``transform`` and is not a pipeline / multi-call shape.
DEFAULT_TYPE_TRANSFORMS: Dict[str, str] = {
    'SMALLINT': 'safe_int',
    'INTEGER':  'safe_int',
    'BIGINT':   'safe_int',
    'VARCHAR':  'safe_str',
    'TEXT':     'safe_str',
    'CHAR':     'safe_str',
}


# ============================================================================
# SEQUENCE REGISTRY
# ============================================================================
# Shared sequences referenced by column defaults via nextval().
# Kept explicit so DDL can validate coverage without regex scanning.
# ============================================================================

class SequenceDef(TypedDict):
    schema: str
    owner_columns: List[str]


SEQUENCES: Dict[str, SequenceDef] = {
    'ops.process_id_seq': {
        'schema': 'ops',
        'owner_columns': ['process_id'],
    },
    'profiles.the_glass_id_seq': {
        'schema': 'profiles',
        'owner_columns': ['the_glass_id'],
    },
}


# ============================================================================
# TABLE DEFINITION TYPES
# ============================================================================

class FKDef(TypedDict):
    column: str
    ref_schema: str
    ref_table: str
    ref_column: str
    strategy: str
    on_update: str
    on_delete: str

class IndexDef(TypedDict):
    name: str
    columns: List[str]

class TableDef(TypedDict):
    entity: str
    schema: Union[str, None]
    primary_key: Union[List[str], None]
    foreign_keys: Union[List[FKDef], None]
    unique_constraints: Union[List[List[str]], None]
    indexes: Union[List[IndexDef], None]
    source_ids: Union[bool, None]


# ============================================================================
# TABLE REGISTRY
# ============================================================================

TABLES: Dict[str, TableDef] = {

    # ------------------------------------------------------------------
    # PROFILES SCHEMA
    # ------------------------------------------------------------------
    'leagues': {
        'entity': 'league',
        'schema': 'profiles',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [],
        'unique_constraints': [['code']],
        'indexes': [],
        'source_ids': False,
    },
    'teams': {
        'entity': 'team',
        'schema': 'profiles',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [
            {
                'column':     'country_id',
                'ref_schema': 'profiles',
                'ref_table':  'countries',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'SET NULL',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': True,
    },
    'players': {
        'entity': 'player',
        'schema': 'profiles',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': True,
    },
    'countries': {
        'entity': 'country',
        'schema': 'profiles',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [
            {
                'column':     'sovereign_id',
                'ref_schema': 'profiles',
                'ref_table':  'countries',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'SET NULL',
            },
        ],
        'unique_constraints': [['code']],
        'indexes': [],
        'source_ids': False,
    },
    # ------------------------------------------------------------------
    # STAGING TABLES (profiles schema, transient ingestion)
    # ------------------------------------------------------------------
    'unmatched_teams': {
        'entity': 'team',
        'schema': 'staging',
        'primary_key': ['league_id', 'source_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [
            {'name': 'league_source', 'columns': ['league_id', 'source']},
            {'name': 'matched_glass_id', 'columns': ['matched_glass_id']},
        ],
        'source_ids': False,
    },
    'unmatched_players': {
        'entity': 'player',
        'schema': 'staging',
        'primary_key': ['league_id', 'source_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [
            {'name': 'league_source', 'columns': ['league_id', 'source']},
            {'name': 'matched_glass_id', 'columns': ['matched_glass_id']},
            {'name': 'team_source_id', 'columns': ['team_source_id']},
        ],
        'source_ids': False,
    },
    # ------------------------------------------------------------------
    # ROSTERS SCHEMA
    # ------------------------------------------------------------------
    'leagues_teams': {
        'entity': 'league',
        'schema': 'rosters',
        'primary_key': ['league_id', 'team_id'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'team_id',
                'ref_schema': 'profiles',
                'ref_table':  'teams',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': False,
    },
    'teams_players': {
        'entity': 'team',
        'schema': 'rosters',
        'primary_key': ['league_id', 'team_id', 'player_id'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'team_id',
                'ref_schema': 'profiles',
                'ref_table':  'teams',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'player_id',
                'ref_schema': 'profiles',
                'ref_table':  'players',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': False,
    },
    'countries_players': {
        'entity': 'country',
        'schema': 'rosters',
        'primary_key': ['player_id', 'country_id'],
        'foreign_keys': [
            {
                'column':     'player_id',
                'ref_schema': 'profiles',
                'ref_table':  'players',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'country_id',
                'ref_schema': 'profiles',
                'ref_table':  'countries',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': False,
    },
    # ------------------------------------------------------------------
    # STATS SCHEMA
    # ------------------------------------------------------------------
    'player_seasons': {
        'entity': 'player',
        'schema': 'stats',
        'primary_key': ['league_id', 'player_id', 'team_id', 'season', 'season_type'],
        'foreign_keys': [
            {
                'column':     'player_id',
                'ref_schema': 'profiles',
                'ref_table':  'players',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'team_id',
                'ref_schema': 'profiles',
                'ref_table':  'teams',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'season_type_season', 'columns': ['season_type', 'season']},
            ],
        'source_ids': False,
    },
    'team_seasons': {
        'entity': 'team',
        'schema': 'stats',
        'primary_key': ['league_id', 'team_id', 'season', 'season_type'],
        'foreign_keys': [
            {
                'column':     'team_id',
                'ref_schema': 'profiles',
                'ref_table':  'teams',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'season_type_season', 'columns': ['season_type', 'season']},
        ],
        'source_ids': False,
    },
    # ------------------------------------------------------------------
    # OPS SCHEMA
    # ------------------------------------------------------------------
    'runs': {
        'entity': 'run',
        'schema': 'ops',
        'primary_key': ['process_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [
            {'name': 'pipeline_status', 'columns': ['pipeline', 'status']},
        ],
        'source_ids': False,
    },
    'tasks': {
        'entity': 'task',
        'schema': 'ops',
        'primary_key': ['process_id'],
        'foreign_keys': [
            {
                'column':     'run_id',
                'ref_schema': 'ops',
                'ref_table':  'runs',
                'ref_column': 'process_id',
                'strategy':   'direct',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': [['run_id', 'task_name']],
        'indexes': [
            {'name': 'run_id_status', 'columns': ['run_id', 'status']},
        ],
        'source_ids': False,
    },
    'coverages': {
        'entity': 'coverage',
        'schema': 'ops',
        'primary_key': ['league_id', 'entity_type', 'season', 'season_type', 'source', 'dataset', 'field'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'profiles',
                'ref_table':  'leagues',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'source_ids': False,
    },
}

# table_name -> entity (e.g. 'players' -> 'player')
TABLE_ENTITY: Dict[str, str] = {
    table_name: meta['entity'] for table_name, meta in TABLES.items()
}
