"""
The Glass - Global ETL Pipeline Policy

Phases are ordered lists of handler names.  The orchestrator dispatches each
handler directly; season/season-type scoping lives in the orchestrator, not
in declarative step metadata.
"""

from typing import Dict, List

VALID_ETL_PHASES = frozenset({'full', 'upsert', 'prune'})

PIPELINE_PHASES: Dict[str, List[str]] = {
    'upsert': [
        'stage_and_match_entities',
        'backfill_stats',
        'update_current_stats',
        'normalize_stats_domains',
    ],
    'prune': [
        'prune_stats_retention',
        'prune_entities',
        'prune_coverages',
    ],
}

# The 'full' phase executes both 'upsert' and 'prune' phases in sequence
PIPELINE_PHASES['full'] = PIPELINE_PHASES['upsert'] + PIPELINE_PHASES['prune']

VALID_ETL_STEP_HANDLERS = frozenset(
    handler for handlers in PIPELINE_PHASES.values() for handler in handlers
)

