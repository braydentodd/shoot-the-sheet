"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are grouped into clusters, and clusters are grouped into stages.

  stage (ingest | promote)
    └─ cluster (execution_start | per_league | per_identity | execution_end)
         └─ phase  (build_schema | maintain_games | promote_profiles | ...)

A dataset's ``phase`` field declares which phase triggers it.

The orchestrator dispatches each phase directly.
"""

from typing import Dict, List, Literal

# ============================================================================
# TYPE ALIASES
# ============================================================================

ClusterT = Literal["execution_start", "per_league", "per_identity", "execution_end"]

PhaseT = Literal[
    "build_schema",
    "detect_season_activity",
    "seed_season_coverage",
    "maintain_leagues_teams",
    "maintain_teams_players",
    "match_entities",
    "maintain_games",
    "match_games",
    "seed_game_coverage",
    "maintain_pbp",
    "maintain_seasons",
    "maintain_profiles",
    "merge_to_intermediate",
    "merge_staging",
    "promote_to_core",
    "promote_profiles",
    "promote_rosters",
    "promote_seasons",
    "promote_games",
    "cascade_delete_reviewed",
    "normalize_nulls_zeroes",
    "prune_stats_retention",
    "prune_entities",
    "prune_coverage",
]

# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

VALID_CLUSTERS = frozenset(
    {"execution_start", "per_league", "per_identity", "execution_end"}
)

PIPELINE: Dict[str, List[str]] = {
    "execution_start": [
        "build_schema",
    ],
    "per_league": [
        "detect_season_activity",
        "seed_season_coverage",
    ],
    "per_identity": [
        "maintain_leagues_teams",
        "maintain_teams_players",
        "match_entities",
        "maintain_games",
        "match_games",
        "seed_game_coverage",
        "maintain_pbp",
        "maintain_seasons",
        "maintain_profiles",
        "merge_to_intermediate",
    ],
    "execution_end": [
        "merge_staging",
        "promote_to_core",
        "promote_profiles",
        "promote_rosters",
        "promote_seasons",
        "promote_games",
        "cascade_delete_reviewed",
        "normalize_nulls_zeroes",
        "prune_stats_retention",
        "prune_entities",
        "prune_coverage",
    ],
}

VALID_PHASES = frozenset(phase for phases in PIPELINE.values() for phase in phases)
