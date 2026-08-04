"""
Shoot the Sheet - Play-by-Play Definitions

All PBP configuration: the canonical event vocabulary (``PBP_EVENTS``),
the source-agnostic event row contract (``PBPEvent``), and the single
unified result-set field dictionary (``RESULT_SET_FIELDS``).

This is the single source of truth for PBP domain knowledge.  The
derivation engine (``src.lib.pbp_derive``) and the accumulator
(``src.lib.pbp_accumulator``) read these definitions and apply them
generically.

Chained/assigned event relationships and impossible-state invariants
live in ``src.definitions.chain_rules``.

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
    "ft1_miss",
    "ft2_make",
    "ft2_miss",
    "ft3_make",
    "ft3_miss",
    "turnover",
    "o_reb",
    "d_reb",
    "rebound",
    # Fouls -- the only foul event types supported (no ``foul`` fallback)
    "standard_foul",
    "elevated_foul",
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


class PBPEvent(TypedDict, total=False):
    """A single normalized play-by-play event.

    This is the source-agnostic contract between normalizers and the
    derivation engine / accumulator.  Every source-specific normalizer
    produces rows of this shape.

    Attributes:
        identity: Identity code (e.g. ``"nba_id"``).
        game_id: External game ID.
        event_id: Source event id -- NEVER renumbered.  Derived events
            use synthetic ids (e.g. ``"D12"``) namespaced so they can
            never collide with source ids.
        seq: Final sequence position (the only ordering the derivation
            engine trusts -- never ``secs``).
        secs: Optional clock seconds; ``None`` for untimed sources.
        period: Period number this event belongs to.
        team_id: External team ID (``""`` for system events).
        player_id: External player ID (``""`` for team-only events).
        event: Canonical event name -- a ``PBP_EVENTS`` key.
        chain_id: Id of the anchor event (the invoking foul for an FT,
            the shot for a rebound, ...); ``None`` when unanchored.
        source: Diagnostics -- the raw row id that produced this event,
            or ``"derived:<rule>"`` for engine-synthesized events.
    """

    identity: str
    game_id: str
    event_id: str
    seq: int
    secs: int | None
    period: int
    team_id: str
    player_id: str
    event: str  # PBPEventType value
    chain_id: str | None
    source: str


# ============================================================================
# CONSOLIDATED EVENT DEFINITIONS
# ============================================================================


class PossTransition(TypedDict):
    """Possession transition semantics for an event.

    Attributes:
        end_team: Team whose possession ends (``"self"`` = event's team,
            ``"opponent"`` = the other team, ``"last_possessing"`` =
            whoever currently possesses, ``None`` = nothing ends).
        start_team: Team whose possession starts (``"self"``,
            ``"opponent"``, ``"next_poss_event"`` = the team of the
            period's first ``indicate_poss`` event, ``None`` = nothing
            starts).
        condition: When the transition fires.
    """

    end_team: Literal["self", "opponent", "last_possessing"] | None
    start_team: Literal["self", "opponent", "next_poss_event"] | None
    condition: Literal["always", "live_shot", "jump_ball_changes_possession"] | None


class EventDef(TypedDict, total=True):
    """Per-canonical-event semantics.  Every entry carries every field.

    Attributes:
        sort_priority: Ordering tie-breaker at the same clock second
            (ascending: lower = earlier).  Events with equal priority
            keep their arrival order.  Only source events are
            priority-sorted; derived/chained events are chain-placed by
            the engine.
        indicate_poss: The event indicates a team has possession.
            Used to pair ``poss_start``/``poss_end``, to define whether
            a possession window counts, and to break scoring sequences.
        indicate_on_court: The event indicates a player is on the court
            (builds starting lineups at period starts).
        shot: A scoring opportunity.  Shots are NOT ``indicate_poss``;
            ``pot_poss_ending_scoring_opp`` is placed before the first
            shot of each eligible scoring sequence instead.
        points: Points awarded for the event (0 for non-scoring
            events).  FT point values are the attempt-index contract:
            ``ft1_make=1``, ``ft2_make=2``, ``ft3_make=3`` (leagues that
            award multi-point FTs emit the matching event).
        poss_transition: Possession transition semantics, or ``None``.
    """

    sort_priority: int
    indicate_poss: bool
    indicate_on_court: bool
    shot: bool
    points: int
    poss_transition: PossTransition | None


PBP_EVENTS: dict[str, EventDef] = {
    "d_reb": {
        "sort_priority": 5,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": {
            "end_team": "opponent",
            "start_team": "self",
            "condition": "always",
        },
    },
    "o_reb": {
        "sort_priority": 5,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "rebound": {
        "sort_priority": 5,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "standard_foul": {
        "sort_priority": 1,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "elevated_foul": {
        "sort_priority": 1,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "pot_poss_ending_scoring_opp": {
        "sort_priority": 2,
        "indicate_poss": True,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "fg2_make": {
        "sort_priority": 3,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 2,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "fg2_miss": {
        "sort_priority": 3,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 0,
        "poss_transition": None,
    },
    "fg3_make": {
        "sort_priority": 3,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 3,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "fg3_miss": {
        "sort_priority": 3,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 0,
        "poss_transition": None,
    },
    "turnover": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "always",
        },
    },
    "fg2_assist": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "fg3_assist": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "block": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "steal": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "o_foul_draw": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "ft1_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 1,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft1_miss": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 0,
        "poss_transition": None,
    },
    "ft2_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 2,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft2_miss": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 0,
        "poss_transition": None,
    },
    "ft3_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 3,
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft3_miss": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "points": 0,
        "poss_transition": None,
    },
    "period_end": {
        "sort_priority": 9,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": {
            "end_team": "last_possessing",
            "start_team": None,
            "condition": "always",
        },
    },
    "player_out": {
        "sort_priority": 10,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "period_start": {
        "sort_priority": 11,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": {
            "end_team": None,
            "start_team": "next_poss_event",
            "condition": "always",
        },
    },
    "player_in": {
        "sort_priority": 12,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "jump_ball_win": {
        "sort_priority": 13,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "points": 0,
        "poss_transition": {
            "end_team": "opponent",
            "start_team": "self",
            "condition": "jump_ball_changes_possession",
        },
    },
    "poss_end": {
        "sort_priority": 14,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
    "poss_start": {
        "sort_priority": 15,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "points": 0,
        "poss_transition": None,
    },
}


# ============================================================================
# RESULT SET FIELD DEFINITIONS
# ============================================================================

# Single unified dictionary of every result-set field.
#
# Each entry is a dict with the following shape:
#
#   op             -- "count" | "derived" | "special"
#   type           -- "int" | "bool"
#   events         -- (count only) list of standard event types to count
#   formula        -- (derived only) math expression referencing other fields
#   fields         -- (derived only) field names referenced in formula
#   result_sets    -- dict mapping result-set name to its configuration:
#                       count:   scope string ("team", "player", "opp_team",
#                                "opp_player", "on_player")
#                       derived: None
#                       special: handler name string
#   requires_clock -- True when the value can only be computed for games
#                     with a clock; outputs None for untimed sources.
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
        "requires_clock": False,
    },
    "fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make",
                   "ft1_miss", "ft2_miss", "ft3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "steals": {
        "op": "count",
        "type": "int",
        "events": ["steal"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "blocks": {
        "op": "count",
        "type": "int",
        "events": ["block"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "standard_fouls": {
        "op": "count",
        "type": "int",
        "events": ["standard_foul"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "elevated_fouls": {
        "op": "count",
        "type": "int",
        "events": ["elevated_foul"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "o_fouls_draws": {
        "op": "count",
        "type": "int",
        "events": ["o_foul_draw"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "fg2_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "fg3_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },

    # -- Count fields: opponent mirrors --

    "poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_poss", "player": "player_poss"},
        "requires_clock": False,
    },
    "pot_poss_ending_scoring_opps": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team", "player": "player"},
        "requires_clock": False,
    },
    "opp_fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make",
                   "ft1_miss", "ft2_miss", "ft3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "opp_poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team_poss", "player": "player_opp_poss"},
        "requires_clock": False,
    },

    # -- Count fields: on-court teammate mirrors --

    "opp_pot_poss_ending_scoring_opps": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team", "player": "opp_player"},
        "requires_clock": False,
    },
    "on_fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make",
                   "ft1_miss", "ft2_miss", "ft3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },
    "on_pot_poss_ending_scoring_opps": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": {"player": "on_player"},
        "requires_clock": False,
    },

    # -- Derived fields --

    "points": {
        "op": "derived",
        "type": "int",
        "events": None,
        "formula": "fg2m*2 + fg3m*3 + ftm",
        "fields": ["fg2m", "fg3m", "ftm"],
        "result_sets": {"team": None, "player": None},
        "requires_clock": False,
    },
    "assist_points": {
        "op": "derived",
        "type": "int",
        "events": None,
        "formula": "fg2_assists*2 + fg3_assists*3",
        "fields": ["fg2_assists", "fg3_assists"],
        "result_sets": {"team": None, "player": None},
        "requires_clock": False,
    },

    # -- Special fields --

    "secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_secs", "player": "player_secs"},
        "requires_clock": True,
    },
    "o_poss_secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_o_poss_secs", "player": "player_o_poss_secs"},
        "requires_clock": True,
    },
    "opp_o_poss_secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "opp_team_o_poss_secs", "player": "opp_player_o_poss_secs"},
        "requires_clock": True,
    },
    "win": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"team": "team_win", "player": "player_win"},
        "requires_clock": False,
    },
    "start": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": {"player": "player_start"},
        "requires_clock": False,
    },
}
