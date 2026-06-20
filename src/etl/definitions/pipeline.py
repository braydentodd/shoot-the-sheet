"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are ordered lists of handler names.  The orchestrator dispatches each
handler directly.  Which datasets run in which phase is declared by each
dataset's ``pipeline_role`` field in
:data:`src.etl.definitions.datasets.DATASETS`.

Scoping:
    - ``build_schema`` and ``prune_*`` run once per run (outside league loop).
    - ``season_detector`` runs once per league.
    - All other phases run once per identity per league.
"""

from typing import Dict, List

VALID_ETL_PHASES = frozenset({"full"})

PIPELINE_PHASES: Dict[str, List[str]] = {
    "full": [
        "build_schema",
        "season_detector",
        "team_discoverer",
        "player_discoverer",
        "stats_maintainer",
        "profile_maintainer",
        "match_entities",
        "upsert_entities",
        "prune_stats_retention",
        "prune_entities",
        "prune_coverages",
    ],
}

VALID_ETL_STEP_HANDLERS = frozenset(
    handler for handlers in PIPELINE_PHASES.values() for handler in handlers
)
