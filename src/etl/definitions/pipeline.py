"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are ordered lists of handler names grouped into execution clusters.
The orchestrator dispatches each handler directly.  Which datasets run in
which phase is declared by each dataset's ``stage`` field in
:data:`src.etl.definitions.datasets.DATASETS`.

Clusters:
    - ``execution_start``  — runs once before all leagues (schema bootstrap only).
    - ``per_league``       — runs once per league (season detection).
    - ``per_identity``     — runs once per league (maintain / match / upsert).
    - ``execution_end``    — runs once after all leagues (prune phases).
"""

from typing import Dict, List

VALID_ETL_PHASES = frozenset(
    {"execution_start", "per_league", "per_identity", "execution_end"}
)

PIPELINE_PHASES: Dict[str, List[str]] = {
    "execution_start": [
        "build_schema",
    ],
    "per_league": [
        "season_detector",
    ],
    "per_identity": [
        "leagues_teams_maintainer",
        "teams_players_maintainer",
        "current_stats_maintainer",
        "stats_coverage_maintainer",
        "profile_maintainer",
        "match_entities",
        "upsert_entities",
    ],
    "execution_end": [
        "normalize_null_zero",
        "prune_stats_retention",
        "prune_entities",
        "prune_coverages",
    ],
}

VALID_ETL_STEP_HANDLERS = frozenset(
    handler for handlers in PIPELINE_PHASES.values() for handler in handlers
)
