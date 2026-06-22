"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are ordered lists of handler names grouped into execution clusters.
The orchestrator dispatches each handler directly.  Which datasets run in
which phase is declared by each dataset's ``role`` field in
:data:`src.etl.definitions.datasets.DATASETS`.

Clusters:
    - ``execution_start`` — runs once at the start of a multi-league run.
    - ``per_identity``  — runs once per identity per league.
    - ``execution_end``  — runs once at the end of a multi-league run.
"""

from typing import Dict, List

VALID_ETL_PHASES = frozenset({"execution_start", "per_identity", "execution_end"})

PIPELINE_PHASES: Dict[str, List[str]] = {
    "execution_start": [
        "build_schema",
        "season_detector",
    ],
    "per_identity": [
        "team_discoverer",
        "player_discoverer",
        "profile_maintainer",
        "stats_maintainer",
        "match_entities",
        "upsert_entities",
    ],
    "execution_end": [
        "prune_stats_retention",
        "prune_entities",
        "prune_coverages",
    ],
}

VALID_ETL_STEP_HANDLERS = frozenset(
    handler for handlers in PIPELINE_PHASES.values() for handler in handlers
)
