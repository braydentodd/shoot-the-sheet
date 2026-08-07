"""
Shoot the Sheet - Play-by-Play Definitions

All PBP configuration: the canonical event vocabulary (``PBP_EVENTS``),
chained/assigned event relationships (``CHAIN_RULES``), impossible-state
invariants (``INVARIANTS``), the source-agnostic event row contract
(``PBPEvent``), and the single unified result-set field dictionary
(``RESULT_SET_FIELDS``).

This is the single source of truth for PBP domain knowledge.  The
derivation engine (``src.lib.pbp_deriver``) and the accumulator
(``src.lib.pbp_accumulator``) read these definitions and apply them
generically.

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
    "ft_miss",
    "turnover",
    "o_reb",
    "d_reb",
    "rebound",
    # Fouls -- the only foul event types supported (no ``foul`` fallback).
    # Standard fouls split by who committed them: ``o_standard_foul``
    # (offensive, e.g. a charge) triggers the ``o_foul_draw`` attribution;
    # ``d_standard_foul`` (defensive, e.g. a shooting foul) carries the
    # fouled player on the event itself (``PBPEvent.fouled_player_id``).
    # Both count toward the ``standard_fouls`` stat and share the same
    # FT/possession semantics.
    "o_standard_foul",
    "d_standard_foul",
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


class PBPEvent(TypedDict):
    """A single normalized play-by-play event.

    This is the source-agnostic contract between normalizers and the
    derivation engine / accumulator.  Every source-specific normalizer
    produces rows of this shape, and every row carries every field (the
    TypedDict is ``total=True``): optional values are expressed with
    their types (``secs=None``, ``chain_id=None``), never by omitting
    the key.

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
        fouled_player_id: For standard foul events, the id of the player
            who was fouled (the shooter on a shooting foul, the defender
            on an offensive foul).  ``None`` when not a foul, when the
            foul was elevated (no player to credit), or when the source
            provides no player 2.
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
    fouled_player_id: str | None
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
        indicate_poss: The event indicates a team has possession.
            Used to pair ``poss_start``/``poss_end``, to define whether
            a possession window counts, and to break scoring sequences.
        indicate_on_court: The event indicates a player is on the court
            (builds starting lineups at period starts).
        inherit_secs_from_indicate_poss: When True, a missing ``secs`` may
            inherit the nearest previous ``indicate_poss`` event's clock
            in the same period -- only when that event is timed; an
            untimed ``indicate_poss`` blocks the fill.  True exactly on
            the events the clock-derived result fields read:
            ``period_end`` (team ``secs``), ``player_in`` / ``player_out``
            (player ``secs``), and ``poss_start`` / ``poss_end``
            (``o_poss_secs``).
        shot: A scoring opportunity.  Shots are NOT ``indicate_poss``;
            ``pot_poss_ending_scoring_opp`` is placed before the first
            shot of each eligible scoring sequence instead.
        points: Points awarded for the event (0 for non-scoring
            events).  FT point values are the attempt-index contract:
            ``ft1_make=1``, ``ft2_make=2``, ``ft3_make=3`` (leagues that
            award multi-point FTs emit the matching event).
        shot_family: ``"fg"``, ``"ft"``, or ``"none"`` -- the scoring
            family, replacing name-splicing (``startswith("fg")``).
        shot_result: ``"make"``, ``"miss"``, or ``"none"`` -- the
            attempt result, replacing name-splicing
            (``endswith("_miss")``).
        foul_family: ``"standard"``, ``"elevated"``, or ``"none"`` --
            the foul semantics a foul event invokes, replacing
            name-splicing (``event == "elevated_foul"``).
        poss_transition: Possession transition semantics, or ``None``.
    """

    indicate_poss: bool
    indicate_on_court: bool
    inherit_secs_from_indicate_poss: bool
    shot: bool
    points: int
    shot_family: Literal["fg", "ft", "none"]
    shot_result: Literal["make", "miss", "none"]
    foul_family: Literal["standard", "elevated", "none"]
    poss_transition: PossTransition | None


PBP_EVENTS: dict[str, EventDef] = {
    "d_reb": {
        "indicate_poss": True,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "opponent",
            "start_team": "self",
            "condition": "always",
        },
    },
    "o_reb": {
        "indicate_poss": True,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "rebound": {
        "indicate_poss": True,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "o_standard_foul": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "standard",
        "poss_transition": None,
    },
    "d_standard_foul": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "standard",
        "poss_transition": None,
    },
    "elevated_foul": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "elevated",
        "poss_transition": None,
    },
    "pot_poss_ending_scoring_opp": {
        "indicate_poss": True,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "fg2_make": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 2,
        "shot_family": "fg",
        "shot_result": "make",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "fg2_miss": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 0,
        "shot_family": "fg",
        "shot_result": "miss",
        "foul_family": "none",
        "poss_transition": None,
    },
    "fg3_make": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 3,
        "shot_family": "fg",
        "shot_result": "make",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "fg3_miss": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 0,
        "shot_family": "fg",
        "shot_result": "miss",
        "foul_family": "none",
        "poss_transition": None,
    },
    "turnover": {
        "indicate_poss": True,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "always",
        },
    },
    "fg2_assist": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "fg3_assist": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "block": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "steal": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "o_foul_draw": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "ft1_make": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 1,
        "shot_family": "ft",
        "shot_result": "make",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft2_make": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 2,
        "shot_family": "ft",
        "shot_result": "make",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft3_make": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 3,
        "shot_family": "ft",
        "shot_result": "make",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "self",
            "start_team": "opponent",
            "condition": "live_shot",
        },
    },
    "ft_miss": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": True,
        "points": 0,
        "shot_family": "ft",
        "shot_result": "miss",
        "foul_family": "none",
        "poss_transition": None,
    },
    "period_end": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": True,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "last_possessing",
            "start_team": None,
            "condition": "always",
        },
    },
    "player_out": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": True,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "period_start": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": {
            "end_team": None,
            "start_team": "next_poss_event",
            "condition": "always",
        },
    },
    "player_in": {
        "indicate_poss": False,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": True,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "jump_ball_win": {
        "indicate_poss": True,
        "indicate_on_court": True,
        "inherit_secs_from_indicate_poss": False,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": {
            "end_team": "opponent",
            "start_team": "self",
            "condition": "jump_ball_changes_possession",
        },
    },
    "poss_end": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": True,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
    "poss_start": {
        "indicate_poss": False,
        "indicate_on_court": False,
        "inherit_secs_from_indicate_poss": True,
        "shot": False,
        "points": 0,
        "shot_family": "none",
        "shot_result": "none",
        "foul_family": "none",
        "poss_transition": None,
    },
}


# ============================================================================
# EVENT GROUPINGS (canonical vocabulary)
# ============================================================================

# Shot-family / result views derived from ``PBP_EVENTS`` metadata.  These
# are the canonical groupings; engines consume them instead of splicing
# event names (``startswith("fg")`` / ``endswith("_miss")``) or
# hardcoding literals.
FG_EVENTS: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["shot_family"] == "fg"
)
FT_EVENTS: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["shot_family"] == "ft"
)
MAKE_EVENTS: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["shot_result"] == "make"
)
MISS_EVENTS: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["shot_result"] == "miss"
)
FG_MAKE_EVENTS: frozenset[str] = FG_EVENTS & MAKE_EVENTS
FG_MISS_EVENTS: frozenset[str] = FG_EVENTS & MISS_EVENTS

# Semantic groups not expressible in ``EventDef`` metadata.  Declared here
# so the event vocabulary lives in config, not scattered through engine
# code.
REBOUND_EVENTS: frozenset[str] = frozenset(
    {"o_reb", "d_reb", "rebound"}
)
FG_ASSIST_EVENTS: frozenset[str] = frozenset({"fg2_assist", "fg3_assist"})
SUBSTITUTION_EVENTS: frozenset[str] = frozenset({"player_in", "player_out"})
PERIOD_BOUNDARY_EVENTS: frozenset[str] = frozenset({"period_start", "period_end"})
POSSESSION_MARKER_EVENTS: frozenset[str] = frozenset({"poss_start", "poss_end"})

# Canonical single-event names used by engine branching and derived-event
# synthesis.
PERIOD_START_EVENT: str = "period_start"
PERIOD_END_EVENT: str = "period_end"
PLAYER_IN_EVENT: str = "player_in"
PLAYER_OUT_EVENT: str = "player_out"
POSS_START_EVENT: str = "poss_start"
POSS_END_EVENT: str = "poss_end"
JUMP_BALL_WIN_EVENT: str = "jump_ball_win"
TURNOVER_EVENT: str = "turnover"
O_REB_EVENT: str = "o_reb"
D_REB_EVENT: str = "d_reb"
REBOUND_EVENT: str = "rebound"
POT_POSS_ENDING_SCORING_OPP_EVENT: str = "pot_poss_ending_scoring_opp"
BLOCK_EVENT: str = "block"


# ============================================================================
# CATALOG HANDLING VALUES
# ============================================================================

# ``core.pbp_events.handling`` may take any canonical ``PBP_EVENTS`` key
# plus a few catalog-only pseudo-values: the ``unreviewed`` default,
# ``ignore``, and ``substitution`` (a source-level pseudo-handling the
# normalizer expands into ``player_in`` / ``player_out``).  This set
# drives the column-level CHECK constraint on ``core.pbp_events.handling``
# so the database enforces the same vocabulary the classifier trusts.
CATALOG_HANDLING_EXTRA: frozenset[str] = frozenset(
    {"ignore", "substitution", "unreviewed"}
)

PBP_HANDLING_VALUES: frozenset[str] = frozenset(PBP_EVENTS) | CATALOG_HANDLING_EXTRA


# ============================================================================
# RESULT SET FIELD DEFINITIONS
# ============================================================================

# The five result-set scopes a PBP stat can appear in.  ``team`` /
# ``opp_team`` are computed for a team row (self / opponent events);
# ``player`` / ``opp_player`` / ``on_player`` for a player row (the
# player's own events, opponents' events while on court, and the team's
# events while the player is on court).  This tuple is the vocabulary
# used by ``RESULT_SET_FIELDS``, the accumulator partitions, the DB
# column ``result_set`` values, and the config validators.
PBP_SCOPES: tuple[str, ...] = (
    "team", "player", "opp_team", "opp_player", "on_player",
)

# Single unified dictionary of every result-set field.
#
# Each entry is a dict with the following shape:
#
#   op             -- "count" | "derived" | "special"
#   type           -- "int" | "bool"
#   events         -- (count only) list of standard event types to count
#   formula        -- (derived only) math expression referencing other fields
#   fields         -- (derived only) field names referenced in formula
#   result_sets    -- tuple of ``PBP_SCOPES`` members this field appears
#                     in.  The accumulator computes the field once per
#                     scope; DB columns map (field, scope) pairs.
#   requires_clock -- True when the value is derived from per-event
#                     ``secs`` metadata.  Computed only from the events
#                     the field reads: outputs None when those events
#                     carry no clock (e.g. untimed sources).  The
#                     deriver's clock-completion pass fills missing
#                     ``secs`` only for events with
#                     ``inherit_secs_from_indicate_poss=True``,
#                     copying the nearest previous ``indicate_poss``
#                     event's clock in the same period (an untimed
#                     ``indicate_poss`` blocks the fill).
#
# One field per stat -- there are no ``opp_`` / ``on_`` prefixed
# mirrors; a stat's opponent / on-court values come from the same field
# computed in the ``opp_team`` / ``opp_player`` / ``on_player`` scopes.

RESULT_SET_FIELDS: dict[str, dict] = {

    # -- Count fields ---------------------------------------------------

    "fg2m": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "fg2a": {
        "op": "count",
        "type": "int",
        "events": ["fg2_make", "fg2_miss"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "fg3m": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "fg3a": {
        "op": "count",
        "type": "int",
        "events": ["fg3_make", "fg3_miss"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "ftm": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "fta": {
        "op": "count",
        "type": "int",
        "events": ["ft1_make", "ft2_make", "ft3_make", "ft_miss"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "o_rebs": {
        "op": "count",
        "type": "int",
        "events": ["o_reb"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "d_rebs": {
        "op": "count",
        "type": "int",
        "events": ["d_reb"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "turnovers": {
        "op": "count",
        "type": "int",
        "events": ["turnover"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "pot_poss_ending_scoring_opps": {
        "op": "count",
        "type": "int",
        "events": ["pot_poss_ending_scoring_opp"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "steals": {
        "op": "count",
        "type": "int",
        "events": ["steal"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "blocks": {
        "op": "count",
        "type": "int",
        "events": ["block"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "standard_fouls": {
        "op": "count",
        "type": "int",
        "events": ["o_standard_foul", "d_standard_foul"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "elevated_fouls": {
        "op": "count",
        "type": "int",
        "events": ["elevated_foul"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "o_fouls_drawn": {
        "op": "count",
        "type": "int",
        "events": ["o_foul_draw"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "fg2_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "fg3_assists": {
        "op": "count",
        "type": "int",
        "events": ["fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "assists": {
        "op": "count",
        "type": "int",
        "events": ["fg2_assist", "fg3_assist"],
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },

    # -- Derived fields -------------------------------------------------

    "assist_points": {
        "op": "derived",
        "type": "int",
        "events": None,
        "formula": "fg2_assists*2 + fg3_assists*3",
        "fields": ["fg2_assists", "fg3_assists"],
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },

    # -- Special fields -------------------------------------------------

    "points": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": True,
    },
    "o_poss_secs": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("team", "opp_team", "on_player", "opp_player"),
        "requires_clock": True,
    },
    "poss": {
        "op": "special",
        "type": "int",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("team", "opp_team", "opp_player", "on_player"),
        "requires_clock": False,
    },
    "win": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("team", "player"),
        "requires_clock": False,
    },
    "start": {
        "op": "special",
        "type": "bool",
        "events": None,
        "formula": None,
        "fields": None,
        "result_sets": ("player",),
        "requires_clock": False,
    },
}


# ============================================================================
# CHAIN RULES -- CHAINED/ASSIGNED EVENT RELATIONSHIPS
# ============================================================================


class ChainRule(TypedDict, total=True):
    """How one canonical event relates to another.

    Every entry carries every field.

    Attributes:
        anchor: The event type(s) this rule binds to.  Special tokens
            name engine-computed anchors:
              - ``"shot"``                 -- the nearest preceding shot
              - ``"miss"``                 -- the nearest preceding miss
              - ``"first_shot_of_scoring_sequence"``
              - ``"possession_end_event"`` -- an event whose
                ``poss_transition`` closes the current window
        scope: Search direction relative to the chained event.
            ``"previous"``/``"next"`` search the event stream in one
            direction; ``"bidirectional"`` searches backward first and
            falls forward only when the backward search fails;
            ``"sequence"`` means same-source-row association (the
            normalizer already expressed the link via ``chain_id``).
        skip: Event types stepped over while searching (``()`` = none).
        max_gap: Max number of NON-skipped events between anchor and the
            chained event; ``-1`` = unbounded.  Also bounds the
            ``superseded_by`` lookahead.
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
        superseded_by: Event types whose real occurrence immediately
            after the anchor (within ``max_gap``) makes the synthesis
            unnecessary -- the real event already carries the change
            (e.g. a held-ball team turnover following a jump ball).
    """

    anchor: tuple[str, ...]
    scope: Literal["previous", "next", "bidirectional", "sequence"]
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
    superseded_by: tuple[str, ...]


CHAIN_RULES: dict[str, ChainRule] = {
    # --- Attribution chains (same source row / same event_id) ---------------
    "fg2_assist": {
        "anchor": ("fg2_make",),
        "scope": "sequence",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
        "superseded_by": (),
    },
    "fg3_assist": {
        "anchor": ("fg3_make",),
        "scope": "sequence",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
        "superseded_by": (),
    },
    "block": {
        "anchor": ("fg2_miss", "fg3_miss"),
        "scope": "sequence",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
        "superseded_by": (),
    },
    "steal": {
        "anchor": ("turnover",),
        "scope": "sequence",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
        "superseded_by": (),
    },
    "o_foul_draw": {
        "anchor": ("o_standard_foul",),
        "scope": "sequence",
        "skip": (),
        "max_gap": 0,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "none",
        "suppress": "none",
        "superseded_by": (),
    },

    # --- Structural chains --------------------------------------------------
    # Rebounds bind to the preceding MISSED shot (a make never produces a
    # rebound); a block, substitutions, makes, and intra-trip rebounds in
    # between are stepped over.  The rebound keeps its own timestamp and
    # the chain binds by sequence.  A rebound anchored to a non-final shot
    # of an open scoring sequence is a source artifact and is suppressed
    # (stage 2, before it can act as an indicate_poss event).
    "o_reb": {
        "anchor": ("miss",),
        "scope": "bidirectional",
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
        "superseded_by": (),
    },
    "d_reb": {
        "anchor": ("miss",),
        "scope": "bidirectional",
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
        "superseded_by": (),
    },
    # Every FT must be invoked by a foul.  The search skips intervening
    # shots (and-one makes) and the foul's own attribution (o_foul_draw)
    # plus the trip's other FTs so any FT chains back to its foul.  When
    # the foul was logged at the end of period N and the FTs at the start
    # of N+1, the search crosses the boundary and the foul is re-anchored
    # to sit immediately before its first FT (both live in the FT's
    # period).
    "ft1_make": {
        "anchor": ("o_standard_foul", "d_standard_foul", "elevated_foul"),
        "scope": "previous",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make", "ft_miss",
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
        "superseded_by": (),
    },
    "ft2_make": {
        "anchor": ("o_standard_foul", "d_standard_foul", "elevated_foul"),
        "scope": "previous",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make", "ft_miss",
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
        "superseded_by": (),
    },
    "ft3_make": {
        "anchor": ("o_standard_foul", "d_standard_foul", "elevated_foul"),
        "scope": "previous",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make", "ft_miss",
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
        "superseded_by": (),
    },
    "ft_miss": {
        "anchor": ("o_standard_foul", "d_standard_foul", "elevated_foul"),
        "scope": "previous",
        "skip": (
            "fg2_make", "fg3_make",
            "ft1_make", "ft2_make", "ft3_make", "ft_miss",
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
        "superseded_by": (),
    },

    # --- Synthesis / placement ---------------------------------------------
    "pot_poss_ending_scoring_opp": {
        "anchor": ("first_shot_of_scoring_sequence",),
        "scope": "previous",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "scoring_opp",
        "suppress": "none",
        "superseded_by": (),
    },
    "poss_start": {
        "anchor": ("poss_end", "period_start"),
        "scope": "previous",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "poss_marker",
        "suppress": "none",
        "superseded_by": (),
    },
    "poss_end": {
        "anchor": ("possession_end_event", "period_end"),
        "scope": "previous",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "poss_marker",
        "suppress": "none",
        "superseded_by": (),
    },
    "player_out_sweep": {
        "anchor": ("period_end",),
        "scope": "previous",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "lineup_sweep",
        "suppress": "none",
        "superseded_by": (),
    },
    "player_in_starters": {
        "anchor": ("period_start",),
        "scope": "previous",
        "skip": (),
        "max_gap": -1,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "starters",
        "suppress": "none",
        "superseded_by": (),
    },
    "jump_ball_turnover": {
        "anchor": ("jump_ball_win",),
        "scope": "previous",
        "skip": (),
        "max_gap": 2,
        "cross_period": False,
        "reanchor": False,
        "required": False,
        "synthesize": "team_turnover",
        "suppress": "none",
        "superseded_by": ("turnover",),
    },
}


# ============================================================================
# INVARIANTS -- IMPOSSIBLE-STATE CHECKS
# ============================================================================


class InvariantDef(TypedDict, total=True):
    """An impossible-state check the engine enforces.

    Attributes:
        except_events: Events exempted from the check.
    """

    except_events: tuple[str, ...]


INVARIANTS: dict[str, InvariantDef] = {
    "ft_without_foul": {
        "except_events": (),
    },
    "foul_without_fouled_player": {
        "except_events": (),
    },
    "fouled_shot_miss": {
        "except_events": (),
    },
    "double_poss_open": {
        "except_events": (),
    },
    "poss_end_no_open": {
        "except_events": (),
    },
    "poss_marker_unpaired": {
        "except_events": (),
    },
    "poss_mismatch": {
        "except_events": (),
    },
    "poss_change_without_transition": {
        "except_events": (),
    },
    "rebound_no_shot": {
        "except_events": (),
    },
    "player_in_twice": {
        "except_events": (),
    },
    "player_out_not_on_court": {
        "except_events": (),
    },
    "player_marker_unpaired": {
        "except_events": (),
    },
    "lineup_too_small": {
        "except_events": (),
    },
    "lineup_too_large": {
        "except_events": (),
    },
    "event_off_court": {
        "except_events": ("o_standard_foul", "d_standard_foul", "elevated_foul"),
    },
    "activity_after_end": {
        "except_events": (),
    },
}
