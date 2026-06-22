"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are ordered lists of handler names grouped into execution clusters.
The orchestrator dispatches each handler directly.  Which datasets run in
which phase is declared by each dataset's ``role`` field in
:data:`src.etl.definitions.datasets.DATASETS`.

Clusters:
    - ``execution_start`` — runs once per league before the main work (schema bootstrap only).
    - ``per_identity``  — runs once per league (season detection + discover / maintain / match / upsert).
    - ``execution_end``  — runs once per league after the main work (prune phases).
"""

from typing import Dict, List

VALID_ETL_PHASES = frozenset({"execution_start", "per_identity", "execution_end"})

PIPELINE_PHASES: Dict[str, List[str]] = {
    "execution_start": [
        "build_schema",
    ],
    "per_identity": [
        "season_detector",
        "team_discoverer",
        "player_discoverer",
        "stats_maintainer",
        "profile_maintainer",
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
