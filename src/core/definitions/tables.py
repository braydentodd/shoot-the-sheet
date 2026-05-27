"""
The Glass - Database Table Registry

Unified registry of every table in the database: profiles, stats, rosters,
and operational (run-tracking) tables.

Operational tables use a ``pipeline`` discriminator column so both ETL and
publish runs share single ``runs`` and ``tasks`` tables rather than
maintaining four mirrored tables.

Column definitions live in ``src.core.definitions.columns.DB_COLUMNS``.
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
VALID_ENTITY_TYPES = frozenset({'league', 'player', 'team'})
VALID_SCOPES = frozenset({'profiles', 'stats', 'rosters', 'runs', 'tasks', 'backfill'})
VALID_REFRESH_MODES = frozenset({'null_only', 'always'})
VALID_SCHEMA_KINDS = frozenset({'core', 'league'})
VALID_FK_ACTIONS = frozenset({'CASCADE', 'RESTRICT', 'SET NULL', 'NO ACTION'})
VALID_MANAGERS = frozenset({'db', 'execution_context', 'source'})
VALID_FK_STRATEGIES = frozenset({'direct', 'profile_lookup'})


# ============================================================================
# DB_COLUMNS SCHEMA
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
    entity: Union[str, None]
    schema: Union[str, None]
    primary_key: Union[List[str], None]
    foreign_keys: Union[List[FKDef], None]
    scope: Union[str, None]
    unique_constraints: Union[List[List[str]], None]
    indexes: Union[List[IndexDef], None]
    source_ids: Union[bool, None]

TABLES: Dict[str, TableDef] = {

    # ------------------------------------------------------------------
    # PROFILE TABLES (core schema)
    # ------------------------------------------------------------------
    'league_profiles': {
        'entity': 'league',
        'schema': 'core',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [],
        'scope': 'profiles',
        'source_ids': False
    },
    'team_profiles': {
        'entity': 'team',
        'schema': 'core',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [],
        'scope': 'profiles',
        'source_ids': True
    },
    'player_profiles': {
        'entity': 'player',
        'schema': 'core',
        'primary_key': ['the_glass_id'],
        'foreign_keys': [],
        'unique_constraints': None,
        'indexes': [],
        'scope': 'profiles',
        'source_ids': True
    },
    # ------------------------------------------------------------------
    # STATS TABLES (per-league schema)
    # ------------------------------------------------------------------
    'player_season_stats': {
        'entity': 'player',
        'schema': 'league',
        'primary_key': ['player_id', 'team_id', 'season', 'season_type'],
        'foreign_keys': [
            {
                'column':     'player_id',
                'ref_schema': 'core',
                'ref_table':  'player_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'team_id',
                'ref_schema': 'core',
                'ref_table':  'team_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'scope': 'stats',
        'source_ids': False
    },
    'team_season_stats': {
        'entity': 'team',
        'schema': 'league',
        'primary_key': ['team_id', 'season', 'season_type'],
        'foreign_keys': [
            {
                'column':     'team_id',
                'ref_schema': 'core',
                'ref_table':  'team_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [],
        'scope': 'stats',
        'source_ids': False
    },
    # ------------------------------------------------------------------
    # ROSTER TABLES (core schema)
    # ------------------------------------------------------------------
    'league_rosters': {
        'entity': 'team',
        'schema': 'core',
        'primary_key': ['league_id', 'team_id'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'core',
                'ref_table':  'league_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'team_id',
                'ref_schema': 'core',
                'ref_table':  'team_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'league_id', 'columns': ['league_id']},
            {'name': 'team_id', 'columns': ['team_id']},
        ],
        'scope': 'rosters',
        'source_ids': False
    },
    'team_rosters': {
        'entity': 'player',
        'schema': 'core',
        'primary_key': ['team_id', 'player_id'],
        'foreign_keys': [
            {
                'column':     'team_id',
                'ref_schema': 'core',
                'ref_table':  'team_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'player_id',
                'ref_schema': 'core',
                'ref_table':  'player_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'team_id', 'columns': ['team_id']},
            {'name': 'player_id', 'columns': ['player_id']},
        ],
        'scope': 'rosters',
        'source_ids': False
    },
    # ------------------------------------------------------------------
    # OPERATIONAL TABLES (core schema)
    # ------------------------------------------------------------------
    'runs': {
        'entity': None,
        'schema': 'core',
        'primary_key': ['run_id'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'core',
                'ref_table':  'league_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            }
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'pipeline_status', 'columns': ['pipeline', 'status']},
        ],
        'scope': 'runs',
        'source_ids': False
    },
    'tasks': {
        'entity': None,
        'schema': 'core',
        'primary_key': ['task_id'],
        'foreign_keys': [
            {
                'column':     'run_id',
                'ref_schema': 'core',
                'ref_table':  'runs',
                'ref_column': 'run_id',
                'strategy':   'direct',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
            {
                'column':     'league_id',
                'ref_schema': 'core',
                'ref_table':  'league_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': [['run_id', 'item_key']],
        'indexes': [
            {'name': 'run_id_status', 'columns': ['run_id', 'status']},
        ],
        'scope': 'tasks',
        'source_ids': False
    },
    'backfill_tracker': {
        'entity': None,
        'schema': 'core',
        'primary_key': ['league_id', 'entity_type', 'season', 'season_type', 'source_key'],
        'foreign_keys': [
            {
                'column':     'league_id',
                'ref_schema': 'core',
                'ref_table':  'league_profiles',
                'ref_column': 'the_glass_id',
                'strategy':   'profile_lookup',
                'on_update':  'CASCADE',
                'on_delete':  'CASCADE',
            },
        ],
        'unique_constraints': None,
        'indexes': [
            {'name': 'entity_season', 'columns': ['entity_type', 'season', 'season_type']},
        ],
        'scope': 'backfill',
        'source_ids': False
    }
}