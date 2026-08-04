"""
Shoot the Sheet - PBP Chain Rules and Invariants

The second/third PBP configuration layers.  ``CHAIN_RULES`` describes
every chained/assigned event relationship (attribution, structural,
synthesis, and placement); ``INVARIANTS`` lists impossible-state checks
the derivation engine enforces.

Everything here is declarative.  The engine (``src.lib.pbp_derive``)
consumes it generically; nothing is hardcoded in lib code.

Convention: definitions = config/dicts/constants.  Code lives in lib
or source folders, never here.
"""

from typing import Literal, TypedDict

# ============================================================================
# CHAIN RULES
# ============================================================================


class ChainRule(TypedDict, total=True):
    """How one canonical event relates to another.

    Every entry carries every field.

    Attributes:
        anchor: The event type this rule binds to.  ``"|"``-joined
            alternatives name specific events; special tokens name
            engine-computed anchors:
              - ``"shot"``                 -- the nearest preceding shot
              - ``"first_shot_of_scoring_sequence"``
              - ``"possession_end_event"`` -- an event whose
                ``poss_transition`` closes the current window
        scope: Search direction relative to the chained event.
            ``"previous"``/``"next"`` search the event stream;
            ``"sequence"`` means same-source-row association (the
            normalizer already expressed the link via ``chain_id``).
        position: Where the chained event sits relative to its anchor.
        skip: Event types stepped over while searching (``()`` = none).
        max_gap: Max number of NON-skipped events between anchor and the
            chained event; ``-1`` = unbounded.
        cross_period: The search may cross a period boundary.
        reanchor: When the anchor is found in a different period, move
            it to sit immediately before/after the chained event so both
            live in the same period (same-period foul/FT rule).
        required: ``True`` -> hard error if the anchor is not found.
        synthesize: What the engine synthesizes when the chained event
            is missing or for placement purposes.
        suppress: Drop the event when it occurs in a state where it is
            a source artifact (e.g. a rebound inside an open scoring
            sequence).
    """

    anchor: str
    scope: Literal["previous", "next", "sequence"]
    position: Literal["before", "after"]
    skip: tuple[str, ...]
    max_gap: int
    cross_period: bool
    reanchor: bool
    required: bool
    synthesize: Literal[
        "none",
        "team_rebound",
        "team_turnover",
        "scoring_opp",
        "poss_marker",
        "lineup_sweep",
        "starters",
    ]
    suppress: Literal["none", "open_scoring_sequence"]


CHAIN_RULES: dict[str, ChainRule] = {
    # --- Attribution chains (same source row / same event_id) ---------------
    "fg2_assist": {
        "anchor": "fg2_make",
        "scope": "sequence",
        "position": "after",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
    },
    "fg3_assist": {
        "anchor": "fg3_make",
        "scope": "sequence",
        "position": "after",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
    },
    "block": {
        "anchor": "fg2_miss|fg3_miss",
        "scope": "sequence",
        "position": "after",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
    },
    "steal": {
        "anchor": "turnover",
        "scope": "sequence",
        "position": "after",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
    },
    "o_foul_draw": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "sequence",
        "position": "after",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
    },

    # --- Structural chains --------------------------------------------------
    # Rebounds bind to the preceding MISSED shot (a make never produces a
    # rebound); a block, substitutions, makes, and intra-trip rebounds in
    # between are stepped over.  The rebound keeps its own timestamp and
    # the chain binds by sequence.  A rebound anchored to a non-final shot
    # of an open scoring sequence is a source artifact and is suppressed
    # (stage 2, before it can act as an indicate_poss event).
    "o_reb": {
        "anchor": "miss",
        "scope": "previous",
        "position": "after",
        "skip": (
            "block", "player_in", "player_out",
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "team_rebound",
        "suppress": "open_scoring_sequence",
    },
    "d_reb": {
        "anchor": "miss",
        "scope": "previous",
        "position": "after",
        "skip": (
            "block", "player_in", "player_out",
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "team_rebound",
        "suppress": "open_scoring_sequence",
    },
    # Every FT must be invoked by a foul.  The search skips intervening
    # shots (and-one makes) and the foul's own attribution (o_foul_draw)
    # plus the trip's other FTs so any FT chains back to its foul.  When
    # the foul was logged at the end of period N and the FTs at the start
    # of N+1, the search crosses the boundary and the foul is re-anchored
    # to sit immediately before its first FT (both live in the FT's
    # period).
    "ft1_make": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },
    "ft1_miss": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },
    "ft2_make": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },
    "ft2_miss": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },
    "ft3_make": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },
    "ft3_miss": {
        "anchor": "standard_foul|elevated_foul",
        "scope": "previous",
        "position": "after",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft1_miss", "ft2_make", "ft2_miss",
            "ft3_make", "ft3_miss",
            "o_foul_draw",
            "player_in", "player_out",
            "o_reb", "d_reb", "rebound",
        ),
        "max_gap": 2,
        "cross_period": True,
        "reanchor": True,
        "required": True,
        "synthesize": "none",
        "suppress": "none",
    },

    # --- Synthesis / placement ---------------------------------------------
    "pot_poss_ending_scoring_opp": {
        "anchor": "first_shot_of_scoring_sequence",
        "scope": "previous",
        "position": "before",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "scoring_opp",
        "suppress": "none",
    },
    "poss_start": {
        "anchor": "poss_end|period_start",
        "scope": "previous",
        "position": "after",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "poss_marker",
        "suppress": "none",
    },
    "poss_end": {
        "anchor": "possession_end_event|period_end",
        "scope": "previous",
        "position": "after",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "poss_marker",
        "suppress": "none",
    },
    "player_out_sweep": {
        "anchor": "period_end",
        "scope": "previous",
        "position": "after",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "lineup_sweep",
        "suppress": "none",
    },
    "player_in_starters": {
        "anchor": "period_start",
        "scope": "previous",
        "position": "after",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "starters",
        "suppress": "none",
    },
    "jump_ball_turnover": {
        "anchor": "jump_ball_win",
        "scope": "previous",
        "position": "after",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "team_turnover",
        "suppress": "none",
    },
}


# ============================================================================
# INVARIANTS
# ============================================================================


class InvariantDef(TypedDict, total=True):
    """An impossible-state check the engine enforces.

    Attributes:
        events: Canonical events this applies to (``()`` = any).
        except_events: Events exempted from the check.
        state: Named engine state the check inspects.
        severity: ``"error"`` fails the game; ``"warn"`` logs loudly.
        message: Human-readable invariant description.
    """

    events: tuple[str, ...]
    except_events: tuple[str, ...]
    state: str
    severity: Literal["error", "warn"]
    message: str


INVARIANTS: dict[str, InvariantDef] = {
    "ft_without_foul": {
        "events": ("ft1_make", "ft2_make", "ft3_make", "ft1_miss", "ft2_miss", "ft3_miss"),
        "except_events": (),
        "state": "no_anchor_foul",
        "severity": "error",
        "message": "Free throw with no invoking foul",
    },
    "fouled_shot_miss": {
        "events": ("fg2_miss", "fg3_miss"),
        "except_events": (),
        "state": "fouled_shot",
        "severity": "error",
        "message": "fg_miss recorded on a fouled shot (impossible event)",
    },
    "double_poss_open": {
        "events": ("poss_start",),
        "except_events": (),
        "state": "poss_open",
        "severity": "error",
        "message": "poss_start fired while a possession window is open",
    },
    "poss_end_no_open": {
        "events": ("poss_end",),
        "except_events": (),
        "state": "poss_open",
        "severity": "error",
        "message": "poss_end fired with no open possession window",
    },
    "poss_marker_unpaired": {
        "events": ("poss_start", "poss_end"),
        "except_events": (),
        "state": "pairing",
        "severity": "error",
        "message": "Unpaired poss_start/poss_end marker",
    },
    "poss_mismatch": {
        "events": ("d_reb", "turnover", "fg2_make", "fg3_make"),
        "except_events": (),
        "state": "poss_team_mismatch",
        "severity": "error",
        "message": "Transition event does not match the possessing team",
    },
    "poss_change_without_transition": {
        "events": (),
        "except_events": (),
        "state": "poss_team_changed_no_transition",
        "severity": "error",
        "message": "indicate_poss by a different team with no transition event",
    },
    "rebound_no_shot": {
        "events": ("o_reb", "d_reb"),
        "except_events": (),
        "state": "no_anchor_shot",
        "severity": "error",
        "message": "Rebound with no anchoring shot",
    },
    "player_in_twice": {
        "events": ("player_in",),
        "except_events": (),
        "state": "on_court",
        "severity": "error",
        "message": "player_in for a player already on court",
    },
    "player_out_not_on_court": {
        "events": ("player_out",),
        "except_events": (),
        "state": "on_court",
        "severity": "error",
        "message": "player_out for a player not on court",
    },
    "player_marker_unpaired": {
        "events": ("player_in", "player_out"),
        "except_events": (),
        "state": "pairing",
        "severity": "error",
        "message": "Unpaired player_in/player_out marker",
    },
    "lineup_too_small": {
        "events": (),
        "except_events": (),
        "state": "lineup_size",
        "severity": "error",
        "message": "Fewer than lineup_size players on court",
    },
    "lineup_too_large": {
        "events": (),
        "except_events": (),
        "state": "lineup_size",
        "severity": "error",
        "message": "More than lineup_size players on court",
    },
    "event_off_court": {
        "events": (),
        "except_events": ("standard_foul", "elevated_foul"),
        "state": "on_court",
        "severity": "error",
        "message": "On-court activity by a player not in the derived lineup",
    },
    "activity_after_end": {
        "events": (),
        "except_events": (),
        "state": "game_ended",
        "severity": "error",
        "message": "Event activity after the final period_end",
    },
}
