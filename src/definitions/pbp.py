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

from typing import Literal, TypedDict

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
    # Possession events (derived)
    "pot_poss_ending_scoring_opp",
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
# CONSOLIDATED EVENT DEFINITIONS
# ============================================================================

# Single authoritative registry of every PBPEventType property.
# All derived groupings below are computed from this dict -- never edited
# manually.  No drift possible between scattered constants.


class PossessionTransition(TypedDict):
    end_team: Literal["self", "opponent", "last_possessing", None]
    start_team: Literal["self", "opponent", "next_poss_event", None]
    condition: Literal[
        "always",
        "live_shot",
        "jump_ball_changes_possession",
        None,
    ]


class EventDef(TypedDict):
    category: str
    sort_priority: int
    poss_indication: bool
    transition: PossessionTransition | None
    pot_poss_ending: bool


PBP_EVENT_DEFINITIONS: dict[str, EventDef] = {
    # --- Shots (all share live_shot + pot_poss_ending) ---
    "fg2_make": {
        "category": "shot",
        "sort_priority": 10,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "fg2_miss": {
        "category": "shot",
        "sort_priority": 20,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "fg3_make": {
        "category": "shot",
        "sort_priority": 10,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "fg3_miss": {
        "category": "shot",
        "sort_priority": 20,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "ft1_make": {
        "category": "shot",
        "sort_priority": 15,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "ft2_make": {
        "category": "shot",
        "sort_priority": 15,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "ft3_make": {
        "category": "shot",
        "sort_priority": 15,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },
    "ft1_miss": {
        "category": "shot",
        "sort_priority": 25,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
        "pot_poss_ending": True,
    },

    # --- Rebounds ---
    "d_reb": {
        "category": "rebound",
        "sort_priority": 30,
        "poss_indication": True,
        "transition": {"end_team": "opponent", "start_team": "self", "condition": "always"},
    },
    "o_reb": {
        "category": "rebound",
        "sort_priority": 30,
        "poss_indication": True,
    },

    # --- Turnover ---
    "turnover": {
        "category": "turnover",
        "sort_priority": 35,
        "poss_indication": True,
        "transition": {"end_team": "self", "start_team": "opponent", "condition": "always"},
    },

    # --- Fouls ---
    "foul": {"category": "foul", "sort_priority": 40},
    "o_foul_draw": {"category": "foul", "sort_priority": 40},

    # --- Jump ball ---
    "jump_ball_win": {
        "category": "possession",
        "sort_priority": 50,
        "poss_indication": True,
        "transition": {"end_team": "opponent", "start_team": "self", "condition": "jump_ball_changes_possession"},
    },

    # --- Period boundaries ---
    "period_start": {
        "category": "system",
        "sort_priority": 0,
        "transition": {"end_team": None, "start_team": "next_poss_event", "condition": "always"},
    },
    "period_end": {
        "category": "system",
        "sort_priority": 100,
        "transition": {"end_team": "last_possessing", "start_team": None, "condition": "always"},
    },

    # --- Lineup ---
    "player_in": {"category": "lineup", "sort_priority": 5},
    "player_out": {"category": "lineup", "sort_priority": 95},

    # --- Secondary events ---
    "fg2_assist": {"category": "secondary", "sort_priority": 10},
    "fg3_assist": {"category": "secondary", "sort_priority": 10},
    "block": {"category": "secondary", "sort_priority": 25},
    "steal": {"category": "secondary", "sort_priority": 35},

    # --- Derived events (emitted by accumulator, not raw sources) ---
    "pot_poss_ending_scoring_opp": {"category": "derived", "sort_priority": 999},
    "poss_start": {"category": "derived", "sort_priority": 999},
    "poss_end": {"category": "derived", "sort_priority": 999},
}


# ============================================================================
# DERIVED GROUPINGS (computed from PBP_EVENT_DEFINITIONS)
# ============================================================================

SHOT_EVENTS: tuple[str, ...] = tuple(
    e for e, d in PBP_EVENT_DEFINITIONS.items() if d.get("category") == "shot"
)

FG_MAKE_EVENTS: tuple[str, ...] = ("fg2_make", "fg3_make")
FG_MISS_EVENTS: tuple[str, ...] = ("fg2_miss", "fg3_miss")
FG_ALL_EVENTS: tuple[str, ...] = FG_MAKE_EVENTS + FG_MISS_EVENTS

FT_MAKE_EVENTS: tuple[str, ...] = ("ft1_make", "ft2_make", "ft3_make")
FT_MISS_EVENTS: tuple[str, ...] = ("ft1_miss",)
FT_ALL_EVENTS: tuple[str, ...] = FT_MAKE_EVENTS + FT_MISS_EVENTS

REB_EVENTS: tuple[str, ...] = ("o_reb", "d_reb")
TOV_EVENTS: tuple[str, ...] = ("turnover",)
FOUL_EVENTS: tuple[str, ...] = ("foul",)

POSS_INDICATION_EVENTS: tuple[str, ...] = tuple(
    e for e, d in PBP_EVENT_DEFINITIONS.items() if d.get("poss_indication")
)

# Backward-compatible alias.
POSSESSION_EVENTS: tuple[str, ...] = POSS_INDICATION_EVENTS

POT_POSS_ENDING_EVENTS: tuple[str, ...] = tuple(
    e for e, d in PBP_EVENT_DEFINITIONS.items() if d.get("pot_poss_ending")
)

EVENT_SORT_PRIORITY: dict[str, int] = {
    e: d["sort_priority"] for e, d in PBP_EVENT_DEFINITIONS.items()
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

RESULT_SET_FIELDS: dict[str, dict] = {

    "fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "steals": {
        "op": "count",
        "type": "int",
        "events": ["steal"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "blocks": {
        "op": "count",
        "type": "int",
        "events": ["block"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fouls": {
        "op": "count",
        "type": "int",
        "events": ["foul"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "o_fouls_draws": {
        "op": "count",
        "type": "int",
        "events": ["o_foul_draw"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg2_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "fg3_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },

    # -- Count fields: opponent mirrors --

    "poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_poss", "player": "player_poss"},
    },
    "poss_ending_ft_trips": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
    },
    "opp_fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_steals": {
        "op": "count",
        "type": "int",
        "events": ["steal"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_blocks": {
        "op": "count",
        "type": "int",
        "events": ["block"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fouls": {
        "op": "count",
        "type": "int",
        "events": ["foul"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_o_fouls_draws": {
        "op": "count",
        "type": "int",
        "events": ["o_foul_draw"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg2_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_fg3_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "opp_poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team_poss", "player": "player_opp_poss"},
    },

    # -- Count fields: on-court teammate mirrors --

    "opp_poss_ending_ft_trips": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
    },
    "on_fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft1_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_steals": {
        "op": "count",
        "type": "int",
        "events": ["steal"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_blocks": {
        "op": "count",
        "type": "int",
        "events": ["block"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fouls": {
        "op": "count",
        "type": "int",
        "events": ["foul"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_o_fouls_draws": {
        "op": "count",
        "type": "int",
        "events": ["o_foul_draw"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fg2_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_fg3_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },
    "on_poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"player": "player_poss"},
    },
    "on_poss_ending_ft_trips": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
    },

    # -- Derived fields --

    "points": {
        "op": "derived",
        "type": "int",
        "events": None,
        "formula": "fg2m*2 + fg3m*3 + ftm",
        "fields": ["fg2m", "fg3m", "ftm"],
        "result_sets": {"team": None, "player": None},
    },
    "assist_points": {
        "op": "derived",
        "type": "int",
        "events": None,
        "formula": "fg2_assists*2 + fg3_assists*3",
        "fields": ["fg2_assists", "fg3_assists"],
        "result_sets": {"team": None, "player": None},
    },

    # -- Special fields --

    "secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_secs", "player": "player_secs"},
    },
    "o_poss_secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_o_poss_secs", "player": "player_o_poss_secs"},
    },
    "win": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_win", "player": "player_win"},
    },
    "start": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"player": "player_start"},
    },
}
