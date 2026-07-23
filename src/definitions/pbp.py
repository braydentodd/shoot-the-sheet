"""
Shoot the Sheet - Play-by-Play Definitions

All PBP configuration: standard event types, standard event groupings,
and a single unified result-set field dictionary.

This is the single source of truth for PBP domain knowledge.  The
accumulator (src.lib.accumulator) reads these definitions and applies
them generically.

Convention: definitions = config/dicts/constants.  Code lives in lib
or source folders, never here.
"""

from typing import Dict, Literal, Tuple, TypedDict


# ============================================================================
# STANDARD EVENT TYPES
# ============================================================================

PBPEventType = Literal[
    # Direct actions
    "fg2_make",
    "fg2_miss",
    "fg3_make",
    "fg3_miss",
    "ft1_make",
    "ft2_make",
    "ft3_make",
    "ft1_miss",
    "turnover",
    "o_reb",
    "d_reb",
    "foul",
    # Secondary actions (may not be provided by all sources)
    "fg2_assist",
    "fg3_assist",
    "block",
    "steal",
    "o_foul_draw",
    # Possession events (derived, complex)
    "poss_ending_ft_trip",
    "poss_start",
    "poss_end",
    # Game context events
    "period_start",
    "period_end",
    "player_in",
    "player_out",
    "jump_ball_win",
]


# ============================================================================
# STANDARD PBP EVENT ROW
# ============================================================================


class PBPEvent(TypedDict):
    """A single normalized play-by-play event.

    This is the source-agnostic contract between normalizers and the
    accumulator.  Every source-specific normalizer produces rows of
    this shape; every accumulator consumes them.
    """

    identity: str
    game_id: str
    secs: int
    event_id: int
    team_id: str
    player_id: str
    event: str  # PBPEventType value


# ============================================================================
# STANDARD EVENT GROUPINGS
# ============================================================================

# Groupings of standard event types for use across accumulators and
# normalizers.  Source-agnostic -- they describe the standard
# PBPEventType values, not any specific API response.

FT_MAKE_EVENTS: Tuple[str, ...] = ("ft1_make", "ft2_make", "ft3_make")
FT_MISS_EVENTS: Tuple[str, ...] = ("ft1_miss",)
FT_ALL_EVENTS: Tuple[str, ...] = FT_MAKE_EVENTS + FT_MISS_EVENTS

FG_MAKE_EVENTS: Tuple[str, ...] = ("fg2_make", "fg3_make")
FG_MISS_EVENTS: Tuple[str, ...] = ("fg2_miss", "fg3_miss")
FG_ALL_EVENTS: Tuple[str, ...] = FG_MAKE_EVENTS + FG_MISS_EVENTS

REB_EVENTS: Tuple[str, ...] = ("o_reb", "d_reb")
TOV_EVENTS: Tuple[str, ...] = ("turnover",)
FOUL_EVENTS: Tuple[str, ...] = ("foul",)

# Events that definitively tell us which team has possession.
# Used when scanning for possession after a made FT or at period start.
POSSESSION_EVENTS: Tuple[str, ...] = (
    FG_MAKE_EVENTS + FG_MISS_EVENTS + FT_ALL_EVENTS + REB_EVENTS + TOV_EVENTS
)


# ============================================================================
# EVENT SORT PRIORITY
# ============================================================================

# When multiple events share the same secs timestamp, this dict controls
# their relative ordering (lower = earlier in the sorted output).

EVENT_SORT_PRIORITY: Dict[str, int] = {
    "foul": 0,
    "o_reb": 1,
    "d_reb": 1,
    "fg2_make": 2,
    "fg3_make": 2,
    "fg2_miss": 2,
    "fg3_miss": 2,
    "turnover": 2,
    "poss_ending_ft_trip": 3,
    "ft1_make": 4,
    "ft1_miss": 4,
    "ft2_make": 4,
    "ft3_make": 4,
    "block": 5,
    "steal": 5,
    "fg2_assist": 6,
    "fg3_assist": 6,
    "period_end": 7,
    "poss_start": 8,
    "poss_end": 9,
    "player_out": 10,
    "player_in": 11,
    "period_start": 12,
    "jump_ball_win": 13,
}


# ============================================================================
# RESULT SET FIELD DEFINITIONS
# ============================================================================

# Single unified dictionary of every result-set field.
#
# Each entry is a dict with the following shape:
#
#   op           -- "count" | "derived" | "special"
#   result_sets  -- dict mapping result-set name to its configuration:
#                     count:   scope string ("team", "player", "opp_team",
#                              "opp_player", "on_player")
#                     derived: None
#                     special: handler name string
#   events       -- (count only) list of standard event types to count
#   formula      -- (derived only) math expression referencing other fields
#   fields       -- (derived only) field names referenced in formula
#
# A field only appears in the result sets listed in its result_sets dict.

RESULT_SET_FIELDS: Dict[str, dict] = {

    # ── Count fields: base ────────────────────────────────────────────

    "fg2m": {
        "op": "count",
        "events": ["fg2_make"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg2a": {
        "op": "count",
        "events": ["fg2_make", "fg2_miss"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3m": {
        "op": "count",
        "events": ["fg3_make"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3a": {
        "op": "count",
        "events": ["fg3_make", "fg3_miss"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "ftm": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fta": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "o_rebs": {
        "op": "count",
        "events": ["o_reb"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "d_rebs": {
        "op": "count",
        "events": ["d_reb"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "turnovers": {
        "op": "count",
        "events": ["turnover"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "steals": {
        "op": "count",
        "events": ["steal"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "blocks": {
        "op": "count",
        "events": ["block"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fouls": {
        "op": "count",
        "events": ["foul"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "o_fouls_draws": {
        "op": "count",
        "events": ["o_foul_draw"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg2_assists": {
        "op": "count",
        "events": ["fg2_assist"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3_assists": {
        "op": "count",
        "events": ["fg3_assist"],
        "result_sets": {"team": "team", "player": "player"},
    },
    "poss": {
        "op": "count",
        "events": ["poss_start"],
        "result_sets": {"team": "team", "player": "player_poss"},
    },
    "poss_ending_ft_trips": {
        "op": "count",
        "events": ["poss_ending_ft_trip"],
        "result_sets": {"team": "team", "player": "player"},
    },

    # ── Count fields: opponent mirrors ────────────────────────────────

    "opp_fg2m": {
        "op": "count",
        "events": ["fg2_make"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg2a": {
        "op": "count",
        "events": ["fg2_make", "fg2_miss"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3m": {
        "op": "count",
        "events": ["fg3_make"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3a": {
        "op": "count",
        "events": ["fg3_make", "fg3_miss"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_ftm": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fta": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_o_rebs": {
        "op": "count",
        "events": ["o_reb"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_d_rebs": {
        "op": "count",
        "events": ["d_reb"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_turnovers": {
        "op": "count",
        "events": ["turnover"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_steals": {
        "op": "count",
        "events": ["steal"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_blocks": {
        "op": "count",
        "events": ["block"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fouls": {
        "op": "count",
        "events": ["foul"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_o_fouls_draws": {
        "op": "count",
        "events": ["o_foul_draw"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg2_assists": {
        "op": "count",
        "events": ["fg2_assist"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3_assists": {
        "op": "count",
        "events": ["fg3_assist"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_poss": {
        "op": "count",
        "events": ["poss_start"],
        "result_sets": {"team": "opp_team", "player": "player_opp_poss"},
    },
    "opp_poss_ending_ft_trips": {
        "op": "count",
        "events": ["poss_ending_ft_trip"],
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },

    # ── Count fields: on-court teammate mirrors ───────────────────────

    "on_fg2m": {
        "op": "count",
        "events": ["fg2_make"],
        "result_sets": {"player": "on_player"},
    },
    "on_fg2a": {
        "op": "count",
        "events": ["fg2_make", "fg2_miss"],
        "result_sets": {"player": "on_player"},
    },
    "on_fg3m": {
        "op": "count",
        "events": ["fg3_make"],
        "result_sets": {"player": "on_player"},
    },
    "on_fg3a": {
        "op": "count",
        "events": ["fg3_make", "fg3_miss"],
        "result_sets": {"player": "on_player"},
    },
    "on_ftm": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "result_sets": {"player": "on_player"},
    },
    "on_fta": {
        "op": "count",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "result_sets": {"player": "on_player"},
    },
    "on_o_rebs": {
        "op": "count",
        "events": ["o_reb"],
        "result_sets": {"player": "on_player"},
    },
    "on_d_rebs": {
        "op": "count",
        "events": ["d_reb"],
        "result_sets": {"player": "on_player"},
    },
    "on_turnovers": {
        "op": "count",
        "events": ["turnover"],
        "result_sets": {"player": "on_player"},
    },
    "on_steals": {
        "op": "count",
        "events": ["steal"],
        "result_sets": {"player": "on_player"},
    },
    "on_blocks": {
        "op": "count",
        "events": ["block"],
        "result_sets": {"player": "on_player"},
    },
    "on_fouls": {
        "op": "count",
        "events": ["foul"],
        "result_sets": {"player": "on_player"},
    },
    "on_o_fouls_draws": {
        "op": "count",
        "events": ["o_foul_draw"],
        "result_sets": {"player": "on_player"},
    },
    "on_fg2_assists": {
        "op": "count",
        "events": ["fg2_assist"],
        "result_sets": {"player": "on_player"},
    },
    "on_fg3_assists": {
        "op": "count",
        "events": ["fg3_assist"],
        "result_sets": {"player": "on_player"},
    },
    "on_poss": {
        "op": "count",
        "events": ["poss_start"],
        "result_sets": {"player": "player_poss"},
    },
    "on_poss_ending_ft_trips": {
        "op": "count",
        "events": ["poss_ending_ft_trip"],
        "result_sets": {"player": "on_player"},
    },

    # ── Derived fields ────────────────────────────────────────────────

    "points": {
        "op": "derived",
        "formula": "fg2m*2 + fg3m*3 + ftm",
        "fields": ["fg2m", "fg3m", "ftm"],
        "result_sets": {"team": None},
    },
    "assist_points": {
        "op": "derived",
        "formula": "fg2_assists*2 + fg3_assists*3",
        "fields": ["fg2_assists", "fg3_assists"],
        "result_sets": {"team": None},
    },

    # ── Special fields ────────────────────────────────────────────────

    "secs": {
        "op": "special",
        "result_sets": {
            "team": "team_secs",
            "player": "player_secs",
        },
    },
    "o_poss_secs": {
        "op": "special",
        "result_sets": {
            "team": "team_o_poss_secs",
            "player": "player_o_poss_secs",
        },
    },
    "win": {
        "op": "special",
        "result_sets": {"player": "player_win"},
    },
}
