"""
The Glass - Global ETL Pipeline Policy

One shared ETL policy for all leagues and sources.
Keep this intentionally small: define step behavior once, then map phases
to ordered step keys.
"""

from typing import Any, Dict, List, Optional

from src.core.definitions.tables import VALID_UPDATE_FREQUENCIES


VALID_ETL_PHASES = frozenset({'full', 'discover', 'rosters', 'backfill', 'update', 'prune'})
VALID_ETL_STEP_HANDLERS = frozenset({
    'discover_entities',
    'populate_profiles',
    'sync_rosters',
    'backfill_stats',
    'update_current_stats',
    'normalize_stats_domains',
    'prune_stats_retention',
})
VALID_SEASON_WINDOWS = frozenset({'none', 'current', 'retained'})
VALID_SEASON_TYPE_MODES = frozenset({'none', 'regular', 'requested'})
VALID_ENTITY_MATCHER_MODES = frozenset({
    'approve_all',
    'drop_missing_source_id',
    'drop_blocked_source_ids',
})


PIPELINE_STEP_SCHEMA: Dict[str, Dict[str, Any]] = {
    'handler':             {'required': True, 'types': (str,), 'allowed_values': VALID_ETL_STEP_HANDLERS},
    'season_window':       {'required': True, 'types': (str,), 'allowed_values': VALID_SEASON_WINDOWS},
    'season_type_mode':    {'required': True, 'types': (str,), 'allowed_values': VALID_SEASON_TYPE_MODES},
}


ENTITY_MATCHER_POLICY: Dict[str, Any] = {
    'default_mode': 'approve_all',
    'entity_rules': {},
}


PIPELINE_STEPS: Dict[str, Dict[str, Any]] = {
    'discover_entities_current': {
        'handler': 'discover_entities',
        'season_window': 'current',
        'season_type_mode': 'regular',
    },
    'discover_entities_retained': {
        'handler': 'discover_entities',
        'season_window': 'retained',
        'season_type_mode': 'regular',
    },
    'sync_rosters_current': {
        'handler': 'sync_rosters',
        'season_window': 'current',
        'season_type_mode': 'regular',
    },
    'sync_rosters_retained': {
        'handler': 'sync_rosters',
        'season_window': 'retained',
        'season_type_mode': 'regular',
    },
    'populate_profiles_discover': {
        'handler': 'populate_profiles',
        'season_window': 'current',
        'season_type_mode': 'regular',
    },
    'populate_profiles_update': {
        'handler': 'populate_profiles',
        'season_window': 'current',
        'season_type_mode': 'regular',
    },
    'backfill_stats': {
        'handler': 'backfill_stats',
        'season_window': 'retained',
        'season_type_mode': 'requested',
    },
    'update_current_stats': {
        'handler': 'update_current_stats',
        'season_window': 'current',
        'season_type_mode': 'requested',
    },
    'normalize_stats_domains_backfill': {
        'handler': 'normalize_stats_domains',
        'season_window': 'retained',
        'season_type_mode': 'requested',
    },
    'normalize_stats_domains_update': {
        'handler': 'normalize_stats_domains',
        'season_window': 'current',
        'season_type_mode': 'requested',
    },
    'prune_stats_retention': {
        'handler': 'prune_stats_retention',
        'season_window': 'current',
        'season_type_mode': 'none',
    },
}


# Phases are ordered execution macros over shared step keys.
PIPELINE_PHASES: Dict[str, List[str]] = {
    'full': [
        'discover_entities_current',
        'discover_entities_retained',
        'sync_rosters_current',
        'sync_rosters_retained',
        'populate_profiles_discover',
        'backfill_stats',
        'update_current_stats',
        'normalize_stats_domains_backfill',
    ],
    'discover': [
        'discover_entities_current',
        'sync_rosters_current',
        'populate_profiles_discover',
    ],
    'rosters': ['sync_rosters_current', 'sync_rosters_retained'],
    'backfill': [
        'discover_entities_retained',
        'sync_rosters_retained',
        'backfill_stats',
        'normalize_stats_domains_backfill',
    ],
    'update': [
        'populate_profiles_update',
        'update_current_stats',
        'normalize_stats_domains_update',
    ],
    'prune': ['prune_stats_retention'],
}
