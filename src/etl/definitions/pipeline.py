"""
The Glass - Global ETL Pipeline Policy

One shared ETL policy for all leagues and sources.
Keep this intentionally small: define step behavior once, then map phases
to ordered step keys.
"""

from typing import Any, Dict, List

from src.core.definitions.stats import RETENTION_SEASONS  # noqa: F401  -- backwards-compatible re-export

VALID_ETL_PHASES = frozenset({'full', 'upsert', 'prune'})
VALID_ETL_STEP_HANDLERS = frozenset({
    'stage_and_match_entities',
    'backfill_stats',
    'update_current_stats',
    'normalize_stats_domains',
    'prune_stats_retention',
    'prune_entities',
    'prune_coverages',
})
VALID_SEASON_WINDOWS = frozenset({'none', 'current', 'previous', 'all'})
VALID_SEASON_TYPE_MODES = frozenset({'none', 'regular', 'requested'})


PIPELINE_STEPS: Dict[str, Dict[str, Any]] = {
    'stage_and_match_entities': {
        'handler': 'stage_and_match_entities',
        'season_window': 'all',
        'season_type_mode': 'regular',
    },
    'backfill_stats': {
        'handler': 'backfill_stats',
        'season_window': 'previous',
        'season_type_mode': 'requested',
    },
    'update_current_stats': {
        'handler': 'update_current_stats',
        'season_window': 'current',
        'season_type_mode': 'requested',
    },
    'normalize_stats': {
        'handler': 'normalize_stats_domains',
        'season_window': 'all',
        'season_type_mode': 'requested',
    },
    'prune_stats': {
        'handler': 'prune_stats_retention',
        'season_window': 'current',
        'season_type_mode': 'none',
    },
    'prune_orphans': {
        'handler': 'prune_entities',
        'season_window': 'none',
        'season_type_mode': 'none',
    },
    'prune_coverage': {
        'handler': 'prune_coverages',
        'season_window': 'none',
        'season_type_mode': 'none',
    },
}


# Phases are ordered execution macros over shared step keys.
PIPELINE_PHASES: Dict[str, List[str]] = {
    'upsert': [
        'stage_and_match_entities',
        'backfill_stats',
        'update_current_stats',
        'normalize_stats',
    ],
    'prune': [
        'prune_stats',
        'prune_orphans',
        'prune_coverage',
    ],
}

# The 'full' phase executes both 'upsert' and 'prune' phases in sequence
PIPELINE_PHASES['full'] = PIPELINE_PHASES['upsert'] + PIPELINE_PHASES['prune']

