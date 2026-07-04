"""
Shoot the Sheet - Validation Constants

Centralized constants for config validation. These define the allowed/valid
values for various config dimensions and enable startup validation to catch
errors early.
"""

from typing import Literal

# ============================================================================
# ENTITY TYPES
# ============================================================================

EntityType = Literal["player", "team"]

VALID_ENTITY_TYPES = frozenset({"player", "team"})

# ============================================================================
# TABLE NAMES
# ============================================================================

# All tables defined in schema.py (with schema-qualified keys)
VALID_STAGING_TABLES = frozenset(
    {
        "staging.teams",
        "staging.players",
        "staging.leagues_teams",
        "staging.teams_players",
        "staging.countries_players",
        "staging.team_seasons",
        "staging.player_seasons",
        "staging.games",
        "staging.player_games",
        "staging.team_games",
        "staging.pbp_events",
    }
)

VALID_CORE_TABLES = frozenset(
    {
        "core.leagues",
        "core.teams",
        "core.players",
        "core.countries",
        "core.leagues_teams",
        "core.teams_players",
        "core.countries_players",
        "core.identities_players",
        "core.identities_teams",
        "core.identities_games",
        "core.team_seasons",
        "core.player_seasons",
        "core.games",
        "core.player_games",
        "core.team_games",
        "core.coverage",
    }
)

VALID_READY_TABLES = frozenset(
    {
        "ready.teams",
        "ready.players",
        "ready.leagues_teams",
        "ready.teams_players",
        "ready.countries_players",
        "ready.identities_players",
        "ready.identities_teams",
        "ready.identities_games",
        "ready.team_seasons",
        "ready.player_seasons",
        "ready.games",
        "ready.player_games",
        "ready.team_games",
        "ready.pbp_events",
    }
)

# ============================================================================
# IDENTITIES
# ============================================================================

# All identities defined in datasets.py (will be validated at startup)
VALID_IDENTITIES = frozenset(
    {
        "nba_id",
        "realgm_id",
        "barttorvik_id",
    }
)

# ============================================================================
# SOURCES
# ============================================================================

# All sources defined in leagues.py SOURCES (will be validated at startup)
VALID_SOURCES = frozenset(
    {
        "nba_api",
        "realgm",
        "barttorvik",
    }
)
