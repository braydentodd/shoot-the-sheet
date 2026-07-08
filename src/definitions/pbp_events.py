"""
Shoot the Sheet - Play-by-Play Event Definitions

Standardized event types and stat accumulation rules for play-by-play data.

Every PBP source normalizes to these event types. The accumulator in
``src.lib.pbp_accumulator`` then applies the rules below to produce, for each
result set (team, player, opp_team, opp_player, on_player), a dict of
canonical stat field names (e.g. ``"fg2m"``, never prefixed).

Column targeting is NOT done here. ``src.definitions.db_columns.DB_COLUMNS``
is the single source of truth for where each accumulated field is written:
every stat column that can be derived from PBP declares a ``"pbp_data"``
entry in its ``dataset_mapping`` naming the accumulator ``field`` and
``result_set`` it is sourced from (identical in shape to every other
dataset_mapping entry in the registry).
"""

from typing import Dict, List, Literal, TypedDict

# ============================================================================
# TYPE ALIASES
# ============================================================================

Event = Literal[
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

ResultSet = Literal["team", "player", "opp_team", "opp_player", "on_player"]

# ============================================================================
# STAT ACCUMULATION RULES
# ============================================================================


class StatRule(TypedDict):
    """Stat accumulation rule from PBP events.

    Attributes:
        events: List of event types that contribute to this stat.
        domains: List of result set domains this stat applies to. Domains
            not listed here are intentionally not computed (e.g. plain
            ``"player"`` does not track raw possessions -- only
            ``"opp_player"`` and ``"on_player"`` do, per the on/off-court
            possession model).
        operation: Accumulation operation ('count' or 'sum_duration').
    """

    events: List[Event]
    domains: List[ResultSet]
    operation: Literal["count", "sum_duration"]


PBP_STAT_RULES: Dict[str, StatRule] = {
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
        "domains": ["team", "opp_team", "opp_player", "on_player"],
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
