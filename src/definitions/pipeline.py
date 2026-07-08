"""
Shoot the Sheet - Global ETL Pipeline Policy

Phases are grouped into clusters, and clusters are grouped into stages.

  stage (ingest | promote)
    └─ cluster (execution_start | league_setup | league_ingest | execution_end)
         └─ phase  (build_schema | maintain_games | promote_profiles | ...)

A dataset's ``phase`` field declares which phase triggers it.

The orchestrator dispatches each phase directly.
"""

from typing import Dict, List, Literal

# ============================================================================
# TYPE ALIASES
# ============================================================================

Phase = Literal[
    "build_schema",
    "detect_season_activity",
    "seed_season_coverage",
    "maintain_leagues_teams",
    "maintain_teams_players",
    "match_entities",
    "maintain_seasons",
    "maintain_games",
    "match_games",
    "seed_game_coverage",
    "maintain_pbp",
    "maintain_profiles",
    "merge_staging",
    "promote_intermediate",
    "normalize_intermediate",
    "clean_staging",
    "clean_intermediate",
    "prune_stats",
    "prune_entities",
    "prune_countries",
    "prune_coverage",
]


# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

PIPELINE: Dict[str, List[str]] = {
    "execution_start": [
        "build_schema",
    ],
    "league_setup": [
        "detect_season_activity",
        "seed_season_coverage",
    ],
    "league_ingest": [
        "maintain_leagues_teams",
        "maintain_teams_players",
        "match_entities",
        "maintain_seasons",
        "maintain_games",
        "match_games",
        "seed_game_coverage",
        "maintain_pbp",
        "maintain_profiles",
        "merge_staging",
    ],
    "execution_end": [
        "normalize_intermediate",
        "promote_intermediate",
        "clean_staging",
        "clean_intermediate",
        "prune_stats",
        "prune_entities",
        "prune_countries",
        "prune_coverage",
    ],
}

VALID_CLUSTERS = frozenset(PIPELINE.keys())

VALID_PHASES = frozenset(phase for phases in PIPELINE.values() for phase in phases)
