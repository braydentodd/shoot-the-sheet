"""
Shoot the Sheet - Play-by-Play Event Definitions

Standardized event types and stat accumulation rules for play-by-play data.

Every PBP source normalizes to these event types, then stats are accumulated
via the generic rules defined here. This keeps source-specific logic minimal
and stat logic centralized.
"""

from typing import Dict, List, Literal, TypedDict

# ============================================================================
# TYPE ALIASES
# ============================================================================

EventType = Literal[
    "fg2_make",
    "fg2_miss",
    "fg3_make",
    "fg3_miss",
    "ft_make",
    "ft_miss",
    "o_reb",
    "d_reb",
    "turnover",
    "block",
    "steal",
    "period_start",
    "overtime_start",
    "sub_in",
    "sub_out",
    "jump_ball_win",
    "jump_ball_lose",
    "poss_ending_ft_trip",
    "new_poss",
]

ResultSetType = Literal["game", "team", "player", "opp_team", "opp_player", "on_player"]

# ============================================================================
# ALLOWED VALUE SETS
# ============================================================================

VALID_EVENT_TYPES = frozenset(
    {
        "fg2_make",
        "fg2_miss",
        "fg3_make",
        "fg3_miss",
        "ft_make",
        "ft_miss",
        "o_reb",
        "d_reb",
        "turnover",
        "block",
        "steal",
        "period_start",
        "overtime_start",
        "sub_in",
        "sub_out",
        "jump_ball_win",
        "jump_ball_lose",
        "poss_ending_ft_trip",
        "new_poss",
    }
)

VALID_RESULT_SET_TYPES = frozenset(
    {"game", "team", "player", "opp_team", "opp_player", "on_player"}
)

# ============================================================================
# STAT ACCUMULATION RULES
# ============================================================================


class StatRuleDef(TypedDict):
    """Stat accumulation rule from PBP events.

    Attributes:
        events: List of event types that contribute to this stat.
        domains: List of result set domains this stat applies to.
        operation: Accumulation operation ('count' or 'sum_duration').
    """

    events: List[EventType]
    domains: List[ResultSetType]
    operation: Literal["count", "sum_duration"]


# Domain-specific prefixes for stat names
# When a stat is computed for a domain, the stat name becomes {prefix}{base_stat}
# Example: fg2m for team → "fg2m", fg2m for player → "fg2m", fg2m for opp_team → "opp_fg2m"
DOMAIN_PREFIXES: Dict[ResultSetType, str] = {
    "team": "",
    "player": "",
    "opp_team": "opp_",
    "opp_player": "opp_",
    "on_player": "on_",
}

# Stat rules: base_stat_name -> accumulation rule
# The actual column name will be prefixed based on domain
PBP_STAT_RULES: Dict[str, StatRuleDef] = {
    "fg2m": {
        "events": ["fg2_make"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "fg2a": {
        "events": ["fg2_make", "fg2_miss"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "fg3m": {
        "events": ["fg3_make"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "fg3a": {
        "events": ["fg3_make", "fg3_miss"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "ftm": {
        "events": ["ft_make"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "fta": {
        "events": ["ft_make", "ft_miss"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "o_rebs": {
        "events": ["o_reb"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "d_rebs": {
        "events": ["d_reb"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "turnovers": {
        "events": ["turnover"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "poss": {
        "events": ["new_poss"],
        "domains": ["team", "opp_team"],
        "operation": "count",
    },
    "poss_ending_ft_trips": {
        "events": ["poss_ending_ft_trip"],
        "domains": ["team", "player", "opp_team", "opp_player", "on_player"],
        "operation": "count",
    },
    "secs": {
        "events": ["sub_in", "sub_out"],
        "domains": ["player"],
        "operation": "sum_duration",
    },
}
