"""
Shoot the Sheet - PBP Derivation Engine

Sequence-based, config-driven derivation of game context from the
canonical event stream:

  - chain resolution: FT -> foul, rebound -> shot, attributions,
    fouled-shot miss removal, same-period foul/FT re-anchoring
  - lineups: period-end sweeps, period-start starters, boundary subs
  - scoring sequences: ``pot_poss_ending_scoring_opp`` placement
  - possession: ``poss_start``/``poss_end``, transitions, team-rebound
    and jump-ball-turnover synthesis
  - cleanup + invariant validation (pairing, on-court, lineup size)

Every rule operates on ``seq`` -- never on ``secs``.  The engine
accumulates ALL errors for a game and returns them (finish-the-game-first).

Before returning, a clock-completion pass fills missing ``secs`` only
for events with ``inherit_secs_from_indicate_poss=True`` (period_end,
player in/out markers, possession markers) -- the events the clock-
derived result fields read -- copying the nearest previous
``indicate_poss`` event's clock in the same period (an untimed
``indicate_poss`` blocks the fill).  All derivation rules key off
``seq``; ``secs`` is optional per-event metadata consumed only by the
accumulator's clock-derived fields.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.definitions.pbp import (
    BLOCK_EVENT,
    CHAIN_RULES,
    D_REB_EVENT,
    FG_ASSIST_EVENTS,
    FG_EVENTS,
    FG_MAKE_EVENTS,
    FG_MISS_EVENTS,
    FT_EVENTS,
    INVARIANTS,
    JUMP_BALL_WIN_EVENT,
    MISS_EVENTS,
    O_REB_EVENT,
    PBP_EVENTS,
    PERIOD_END_EVENT,
    PERIOD_START_EVENT,
    PLAYER_IN_EVENT,
    PLAYER_OUT_EVENT,
    POSS_END_EVENT,
    POSS_START_EVENT,
    POT_POSS_ENDING_SCORING_OPP_EVENT,
    REBOUND_EVENT,
    REBOUND_EVENTS,
    SUBSTITUTION_EVENTS,
    TURNOVER_EVENT,
    ChainRule,
    PBPEvent,
    PossTransition,
)
from src.lib.error_recorder import PbpError

logger = logging.getLogger(__name__)

# Attribution chains are the CHAIN_RULES entries bound within the same
# source row (``scope == "sequence"``): fg2_assist, fg3_assist, block,
# steal, o_foul_draw.  Derived from config so the engine never hardcodes
# the list.
ATTRIBUTION_EVENTS: frozenset[str] = frozenset(
    name for name, rule in CHAIN_RULES.items() if rule["scope"] == "sequence"
)

# FT / rebound chain-rule families, derived from config so the
# family-level ``reanchor`` / ``suppress`` gates in ``_stage_1_chains``
# never alias a single representative event.  A neutral ``rebound`` has
# no chain rule of its own (it reuses the ``o_reb`` semantics).
FT_RULES: tuple[ChainRule, ...] = tuple(
    CHAIN_RULES[name] for name in FT_EVENTS if name in CHAIN_RULES
)
REB_RULES: tuple[ChainRule, ...] = tuple(
    CHAIN_RULES[name] for name in REBOUND_EVENTS if name in CHAIN_RULES
)

# Events whose missing ``secs`` the clock-completion pass may fill:
# the clock-derived result fields read exactly these (team ``secs`` <-
# period_end; player ``secs`` <- player_in/out; ``o_poss_secs`` <-
# poss_start/end).  Derived from config so the engine never hardcodes
# the list.
_CLOCK_INHERIT_EVENTS: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["inherit_secs_from_indicate_poss"]
)


def _fill_missing_secs(events: list[PBPEvent]) -> None:
    """Forward-fill missing ``secs`` for clock-inheriting event types.

    An event with ``inherit_secs_from_indicate_poss=True`` and a missing
    ``secs`` inherits the clock of the nearest previous ``indicate_poss``
    event in the same period -- but only when that event is itself timed.
    An untimed ``indicate_poss`` event blocks the fill (the nearest
    previous one carries no clock; nothing older is used), and a fill
    never crosses a period boundary.  Every other event keeps its own
    parsed ``secs`` (or ``None``): a shot or turnover's clock is never
    fabricated.  Fully timed and fully untimed games are no-ops.  Mutates
    the list in place (metadata only; ordering and ``seq`` are untouched).
    """
    last_poss_secs: dict[int, int | None] = {}
    for e in events:
        ev_def = PBP_EVENTS[e["event"]]
        if ev_def["indicate_poss"]:
            last_poss_secs[e["period"]] = e["secs"]
        elif (
            e["event"] in _CLOCK_INHERIT_EVENTS
            and e["secs"] is None
            and e["period"] in last_poss_secs
            and last_poss_secs[e["period"]] is not None
        ):
            e["secs"] = last_poss_secs[e["period"]]

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class DeriveResult:
    """Output of the derivation engine."""

    events: list[PBPEvent]
    errors: list[PbpError] = field(default_factory=list)


def derive_game_context_events(
    events: list[PBPEvent],
    home_team_id: str,
    away_team_id: str,
    lineup_size: int = 5,
) -> DeriveResult:
    """Derive possession, lineup, and scoring-sequence context.

    Args:
        events: Normalized ``PBPEvent`` rows in feed order (each row has
            ``seq`` assigned by the normalizer).
        home_team_id: External id of the home team.
        away_team_id: External id of the away team.
        lineup_size: Number of players on court per team (from leagues).

    Returns:
        ``DeriveResult`` with the final ordered event list (re-sequenced)
        and every error accumulated for the game.
    """
    engine = _DeriveEngine(list(events), home_team_id, away_team_id, lineup_size)
    return engine.run()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class _DeriveEngine:
    """Stateful derivation pass over one game's event stream."""

    def __init__(
        self,
        events: list[PBPEvent],
        home_team_id: str,
        away_team_id: str,
        lineup_size: int,
    ) -> None:
        self._events = events
        self.home_team_id = home_team_id
        self.away_team_id = away_team_id
        self.lineup_size = lineup_size
        self.errors: list[PbpError] = []
        self._derived_counter = 0

        self._game_id = events[0]["game_id"] if events else ""
        self._identity = events[0]["identity"] if events else ""

        # id -> event lookup, refreshed whenever a stage rebuilds the list.
        self._by_id: dict[str, PBPEvent] = {e["event_id"]: e for e in events}

        # Instance state populated across stages.
        self._sequence_final_misses: set[str] = set()
        self._and_one_make_ids: set[str] = set()
        self._and_one_foul_ids: set[str] = set()
        self._trip_last_ft_ids: set[str] = set()

    # ==================================================================
    # Entry
    # ==================================================================

    def run(self) -> DeriveResult:
        events = sorted(self._events, key=lambda e: (e.get("seq", 0)))
        self._reindex(events)

        events = self._stage_1_chains(events)
        events = self._stage_2_lineups(events)
        events = self._stage_3_scoring(events)
        events = self._stage_4_possession(events)
        events = self._stage_5_cleanup(events)

        self._reindex(events)
        # Clock-completion pass: forward-fill missing ``secs`` for events
        # with ``inherit_secs_from_indicate_poss`` from the nearest
        # previous ``indicate_poss`` event in the period; all derivation
        # rules key off ``seq``.
        _fill_missing_secs(events)
        return DeriveResult(events=events, errors=self.errors)

    # ==================================================================
    # Helpers
    # ==================================================================

    def _reindex(self, events: list[PBPEvent]) -> None:
        """Assign sequential ``seq`` values matching list position."""
        for i, e in enumerate(events):
            e["seq"] = i

    def _error(
        self,
        rule: str,
        message: str,
        event: PBPEvent | None = None,
        **detail: object,
    ) -> None:
        self.errors.append(
            PbpError(
                rule=rule,
                message=message,
                game_id=self._game_id,
                event_id=event.get("event_id") if event else None,
                seq=event.get("seq") if event else None,
                event=event.get("event") if event else None,
                team_id=event.get("team_id") if event else None,
                player_id=event.get("player_id") if event else None,
                detail=detail,
            )
        )

    def _mk(
        self,
        anchor: PBPEvent,
        event: str,
        team_id: str,
        player_id: str = "",
        *,
        chain_id: str | None = None,
        source: str | None = None,
    ) -> PBPEvent:
        """Build a derived event anchored to *anchor* (inherits secs/period)."""
        self._derived_counter += 1
        return {
            "identity": anchor["identity"],
            "game_id": anchor["game_id"],
            "event_id": f"D{self._derived_counter}",
            "seq": anchor["seq"],
            "secs": anchor.get("secs"),
            "period": anchor.get("period", 1),
            "team_id": team_id,
            "player_id": player_id,
            "event": event,
            "chain_id": chain_id or anchor.get("event_id"),
            "fouled_player_id": None,
            "source": source or f"derived:{event}",
        }

    def _opp(self, team_id: str) -> str:
        if team_id == self.home_team_id:
            return self.away_team_id
        if team_id == self.away_team_id:
            return self.home_team_id
        return ""

    @staticmethod
    def _is_shot(e: PBPEvent) -> bool:
        return bool(PBP_EVENTS.get(e["event"], {}).get("shot"))

    @staticmethod
    def _is_indicate_poss(e: PBPEvent) -> bool:
        return bool(PBP_EVENTS.get(e["event"], {}).get("indicate_poss"))

    @staticmethod
    def _is_indicate_on_court(e: PBPEvent) -> bool:
        return bool(PBP_EVENTS.get(e["event"], {}).get("indicate_on_court"))

    @staticmethod
    def _is_ft(e: PBPEvent) -> bool:
        return e["event"] in FT_EVENTS

    @staticmethod
    def _is_fg(e: PBPEvent) -> bool:
        return e["event"] in FG_EVENTS

    @staticmethod
    def _is_source(e: PBPEvent) -> bool:
        return not str(e.get("source", "")).startswith("derived:")

    @staticmethod
    def _foul_family(e: PBPEvent) -> str:
        return PBP_EVENTS.get(e["event"], {}).get("foul_family", "none")

    # ==================================================================
    # Stage 1 -- chain resolution
    # ==================================================================

    def _stage_1_chains(self, events: list[PBPEvent]) -> list[PBPEvent]:
        # 1a. FT -> foul chains.  A foul always precedes its free throws
        # in every feed, so the FT search is backward-only; the backward
        # search is gated on the rule's scope (a "next" or "sequence"
        # scope on an FT rule is a config error that fails closed).
        for e in events:
            if not self._is_ft(e):
                continue
            rule = CHAIN_RULES[e["event"]]
            skip = frozenset(rule["skip"])
            foul = None
            if rule["scope"] in ("previous", "bidirectional"):
                foul = self._find_backward(
                    events, e["seq"], rule["anchor"],
                    skip=skip,
                    max_gap=rule["max_gap"],
                    cross_period=rule["cross_period"],
                )
            if foul is None:
                if rule["required"]:
                    self._error(
                        "ft_without_foul",
                        f"Free throw {e['event']} has no invoking foul",
                        e,
                    )
                continue
            e["chain_id"] = foul["event_id"]

        # 1b. Rebound -> shot chains (and off/def resolution).
        # A source ``rebound`` event is neutral; off/def is decided by
        # the chain: o_reb when the rebounding team is the shooting team,
        # d_reb otherwise.  A rebound is placed directly after its shot
        # (the user rule "rebounds and shots at the same sec keep the
        # order they came in"): when the feed placed the rebound ahead
        # of its miss, the rebound is re-anchored to sit immediately
        # after the shot.
        #
        # Search direction is config-driven: ``o_reb`` / ``d_reb`` scope
        # is ``"bidirectional"`` (backward first, then forward) to
        # tolerate feeds that place the rebound ahead of its miss.
        rebound_moves: list[tuple[PBPEvent, PBPEvent]] = []
        for e in events:
            if e["event"] not in REBOUND_EVENTS:
                continue
            # Neutral source ``rebound`` reuses the o_reb search semantics.
            rule = (
                CHAIN_RULES[e["event"]]
                if e["event"] in CHAIN_RULES
                else CHAIN_RULES[O_REB_EVENT]
            )
            skip = frozenset(rule["skip"])
            shot = self._find_backward(
                events, e["seq"], rule["anchor"],
                skip=skip,
                max_gap=rule["max_gap"],
                cross_period=rule["cross_period"],
            )
            if shot is None and rule["scope"] == "bidirectional":
                shot = self._find_forward(
                    events, e["seq"], skip=skip,
                    max_gap=rule["max_gap"],
                    cross_period=rule["cross_period"],
                )
                if shot is not None and not self._is_shot(shot):
                    shot = None
            if shot is None:
                self._error("rebound_no_shot", "Rebound with no anchoring shot", e)
                continue
            if e["event"] == REBOUND_EVENT:
                e["event"] = O_REB_EVENT if e["team_id"] == shot["team_id"] else D_REB_EVENT
            e["chain_id"] = shot["event_id"]
            # The rebound always sits directly after its anchor shot
            # (the user rule "rebounds and shots at the same sec keep the
            # order they came in"): the feed may record the rebound after
            # a tip-in make or before its miss at the same clock mark.
            rebound_moves.append((e, shot))

        if rebound_moves:
            events = self._place_after(events, rebound_moves)

        self._reindex(events)
        self._by_id = {e["event_id"]: e for e in events}

        # 1c. Attribution chains (same source row / same event_id).
        self._resolve_attributions(events)

        # 1d. Fouled-shot miss removal (impossible fg_miss on a fouled shot).
        events = self._remove_fouled_misses(events)

        # 1e. Re-anchor cross-period fouls to sit before their first FT.
        # The family-level gate is derived from the per-event rules so no
        # single event is treated as a representative of its family.
        if any(r["reanchor"] for r in FT_RULES):
            events = self._reanchor_fouls(events)

        # 1f. Suppress intra-sequence rebound artifacts so they never act
        # as indicate_poss events.
        if any(r["suppress"] == "open_scoring_sequence" for r in REB_RULES):
            events = self._suppress_intra_sequence_rebounds(events)

        self._reindex(events)
        return events

    def _find_backward(
        self,
        events: list[PBPEvent],
        idx: int,
        anchor_spec: tuple[str, ...],
        *,
        skip: frozenset[str],
        max_gap: int,
        cross_period: bool,
    ) -> PBPEvent | None:
        """Search backward from *idx* for an anchor event.

        ``anchor_spec`` is a tuple of event names or special tokens:
        ``"shot"`` (any shot) or ``"miss"`` (any missed shot).  Returns
        the first matching event, or ``None`` if none is found within
        ``max_gap`` non-skipped events.
        """
        anchors = anchor_spec
        anchor_shot = "shot" in anchors
        anchor_miss = "miss" in anchors
        start_period = events[idx].get("period")
        gap = 0
        for j in range(idx - 1, -1, -1):
            cand = events[j]
            if not cross_period and cand.get("period") != start_period:
                return None
            if cand["event"] in skip:
                continue
            if anchor_shot and self._is_shot(cand):
                return cand
            if anchor_miss and cand["event"] in MISS_EVENTS:
                return cand
            if cand["event"] in anchors:
                return cand
            gap += 1
            if max_gap >= 0 and gap > max_gap:
                return None
        return None

    def _place_after(
        self,
        events: list[PBPEvent],
        pairs: list[tuple[PBPEvent, PBPEvent]],
    ) -> list[PBPEvent]:
        """Move each chained event to sit immediately after its anchor.

        Used to enforce chain placement (a rebound always sits directly
        after its shot) when the feed order left the event ahead of its
        anchor.
        """
        move_ids = {e["event_id"] for e, _ in pairs}
        result = [e for e in events if e["event_id"] not in move_ids]
        self._reindex(result)
        for chained, anchor in sorted(pairs, key=lambda p: p[1]["seq"]):
            result.insert(anchor["seq"] + 1, chained)
            self._reindex(result)
        return result

    def _find_forward(
        self,
        events: list[PBPEvent],
        idx: int,
        *,
        skip: frozenset[str],
        max_gap: int,
        cross_period: bool,
    ) -> PBPEvent | None:
        """Return the first non-skipped event after *idx* (or None).

        ``max_gap`` bounds the number of NON-skipped events the search
        may pass over (mirroring ``_find_backward``) so the config value
        is genuinely authoritative.
        """
        start_period = events[idx].get("period")
        gap = 0
        for j in range(idx + 1, len(events)):
            cand = events[j]
            if not cross_period and cand.get("period") != start_period:
                return None
            if cand["event"] in skip:
                continue
            if max_gap >= 0 and gap >= max_gap:
                return None
            gap += 1
            return cand
        return None

    def _resolve_attributions(self, events: list[PBPEvent]) -> None:
        """Bind attribution events to their primary via same event_id."""
        for e in events:
            if e["event"] in ATTRIBUTION_EVENTS:
                primary = self._by_id.get(e.get("chain_id") or "")
                if primary is not None:
                    e["chain_id"] = primary["event_id"]

    def _remove_fouled_misses(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Remove ``fg_miss`` events recorded on fouled shots.

        A fouled shot never has an ``fg_miss`` (the foul row IS the
        record of the attempt).  If a miss appears immediately before a
        standard foul whose fouled player is the misser and whose FTs
        follow, the miss is an impossible event: remove it and record
        the invariant error.
        """
        remove: set[str] = set()
        for i, e in enumerate(events):
            if e["event"] not in FG_MISS_EVENTS:
                continue
            nxt = self._find_forward(
                events, i, skip=frozenset({BLOCK_EVENT}), max_gap=1, cross_period=False,
            )
            if nxt is None or self._foul_family(nxt) != "standard":
                continue
            if self._fouled_player(nxt) != e["player_id"]:
                continue
            if not self._foul_has_fts(events, nxt):
                continue
            self._error(
                "fouled_shot_miss",
                f"fg_miss by {e['player_id']} recorded on a fouled shot "
                f"(impossible event); removed",
                e,
                foul_id=nxt["event_id"],
            )
            remove.add(e["event_id"])
        return [e for e in events if e["event_id"] not in remove]

    def _fouled_player(self, foul: PBPEvent) -> str | None:
        """Return the fouled player id for a standard foul.

        Standard foul events carry the fouled player directly in
        ``PBPEvent.fouled_player_id`` (set by the normalizer).  A
        standard foul without one is a data-integrity error recorded by
        the ``foul_without_fouled_player`` invariant -- there is no
        fallback attribution path.
        """
        return foul.get("fouled_player_id") or None

    def _foul_has_fts(self, events: list[PBPEvent], foul: PBPEvent) -> bool:
        """True if any FT event chains to *foul*."""
        return any(
            e.get("chain_id") == foul["event_id"] and self._is_ft(e)
            for e in events
        )

    def _make_absorbed_by_trip(self, events: list[PBPEvent], idx: int) -> bool:
        """True when the fg_make at *idx* is absorbed into a foul trip.

        A made basket whose team immediately shoots free throws (from a
        foul on the play -- shooting or loose-ball on a teammate) is
        absorbed: the make does not transition and the trip carries the
        single ``pot_poss_ending_scoring_opp``.
        """
        make = events[idx]
        nxt = self._find_forward(
            events, idx, skip=frozenset(FG_ASSIST_EVENTS),
            max_gap=1, cross_period=False,
        )
        if nxt is None or self._foul_family(nxt) != "standard":
            return False
        trip_fts = [
            e for e in events
            if e.get("chain_id") == nxt["event_id"] and self._is_ft(e)
        ]
        return bool(trip_fts) and all(f["team_id"] == make["team_id"] for f in trip_fts)

    def _reanchor_fouls(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Move cross-period fouls to sit immediately before their first FT.

        Runs after FT chains are resolved: a foul whose period differs
        from its trip's period is relocated to the trip's first FT
        position so foul and FTs live in the same period.
        """
        first_ft_by_foul: dict[str, PBPEvent] = {}
        for e in events:
            if not self._is_ft(e):
                continue
            chain_id = e.get("chain_id")
            if chain_id is None:
                continue
            cur = first_ft_by_foul.get(chain_id)
            if cur is None or e["seq"] < cur["seq"]:
                first_ft_by_foul[chain_id] = e

        moves: list[tuple[PBPEvent, PBPEvent]] = []
        for foul_id, first_ft in first_ft_by_foul.items():
            foul = self._by_id.get(foul_id)
            if foul is None or foul.get("period") == first_ft.get("period"):
                continue
            moves.append((foul, first_ft))

        if not moves:
            return events

        move_ids = {m[0]["event_id"] for m in moves}
        result = [e for e in events if e["event_id"] not in move_ids]
        self._reindex(result)
        for foul, first_ft in moves:
            foul["period"] = first_ft["period"]
            foul["secs"] = first_ft["secs"]
            result.insert(first_ft["seq"], foul)
        self._reindex(result)
        self._by_id = {e["event_id"]: e for e in result}
        return result

    def _suppress_intra_sequence_rebounds(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Drop rebounds anchored to a non-final shot of its trip.

        A rebound between shots of the same trip (an and-one make + its
        FTs, or multiple FTs of one trip) is a source artifact
        (``CHAIN_RULES`` ``suppress="open_scoring_sequence"``).
        """
        non_final: set[str] = set()

        # A shot is non-final when a later shot shares its foul trip.
        trip_shots: dict[str, list[PBPEvent]] = {}
        for e in events:
            if not self._is_shot(e):
                continue
            chain_id = e.get("chain_id")
            if chain_id is None:
                continue
            trip_shots.setdefault(chain_id, []).append(e)
        for trip in trip_shots.values():
            if len(trip) > 1:
                last = max(trip, key=lambda x: x["seq"])
                for shot in trip:
                    if shot is not last:
                        non_final.add(shot["event_id"])

        # An and-one make is "in" its foul's trip: non-final when the
        # foul's FTs follow (the foul row follows the make in the feed;
        # the make's assist attribution sits between them).
        for i, e in enumerate(events):
            if e["event"] not in FG_MAKE_EVENTS:
                continue
            if self._make_absorbed_by_trip(events, i):
                non_final.add(e["event_id"])

        # Only one rebound per anchor shot: sources may credit duplicates
        # on tip-in sequences (miss -> o_reb -> tip make -> o_reb).  Keep
        # the first rebound for each anchor; suppress the rest.  Neutral
        # source ``rebound`` events were resolved to o_reb/d_reb in stage
        # 1 (or carry no chain_id and are skipped below), so the family
        # check is equivalent to o_reb/d_reb here.
        rebound_anchors: dict[str, list[PBPEvent]] = {}
        for e in events:
            if e["event"] not in REBOUND_EVENTS:
                continue
            chain_id = e.get("chain_id")
            if chain_id is None:
                continue
            rebound_anchors.setdefault(chain_id, []).append(e)
        duplicate_reb_ids: set[str] = set()
        for rebs in rebound_anchors.values():
            if len(rebs) > 1:
                first = min(rebs, key=lambda x: x["seq"])
                for reb in rebs:
                    if reb is not first:
                        duplicate_reb_ids.add(reb["event_id"])

        if not non_final and not duplicate_reb_ids:
            return events

        suppressed = [
            e for e in events
            if not (
                e["event"] in REBOUND_EVENTS
                and (
                    e.get("chain_id") in non_final
                    or e["event_id"] in duplicate_reb_ids
                )
            )
        ]
        self._reindex(suppressed)
        self._by_id = {e["event_id"]: e for e in suppressed}
        return suppressed

    # ==================================================================
    # Stage 2 -- lineups
    # ==================================================================

    def _stage_2_lineups(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Derive period-end sweeps and period-start starters.

        Lineups never carry over between periods.  At every
        ``period_end`` every on-court player gets a ``player_out``; at
        every ``period_start`` starters are derived from
        ``indicate_on_court`` events (with between-period boundary subs
        recognized before the team's first non-substitution event).

        A player is a starter when they appear in any non-substitution
        ``indicate_on_court`` event, or when a source ``player_out``
        proves they were on court.  Boundary sub-ins (a ``player_in``
        paired with a ``player_out`` before the team's first on-court
        event) are starters; their source markers are dropped because
        the derived starter ``player_in`` and the prior-period sweep
        supersede them.  Boundary sub-outs were swept at the prior
        ``period_end``.
        """
        result: list[PBPEvent] = []

        on_court: dict[str, set[str]] = {}
        starters: dict[str, set[str]] = {}
        finalized: dict[str, bool] = {}
        period_start_pos: int | None = None
        period_anchor: PBPEvent | None = None
        period_num = 1
        in_period = False
        boundary_ids: set[str] = set()

        # Group source substitution events by event_id so boundary pairs
        # (player_out + player_in from one source row) are recognized.
        sub_pairs: dict[str, frozenset[str]] = {}
        for e in events:
            if e["event"] in SUBSTITUTION_EVENTS:
                sub_pairs[e["event_id"]] = frozenset(
                    sub_pairs.get(e["event_id"], frozenset()) | {e["event"]}
                )

        def _finalize(end_anchor: PBPEvent) -> None:
            """Validate lineups, sweep, and insert starter player_ins.

            ``end_anchor`` is the period's ``period_end`` event: the sweep
            ``player_out`` rows inherit its clock so on-court intervals
            measure real minutes (period_end secs minus period_start secs).
            """
            anchor = period_anchor
            pos = period_start_pos
            if anchor is None or pos is None:
                return
            if end_anchor["event"] != PERIOD_END_EVENT:
                # Truncated game: the period was closed at its own start
                # (the next period_start) or at end of stream without a
                # real ``period_end``.  Swept ``player_out`` rows inherit
                # the ``period_start`` clock (approx. 0 minutes); flag the
                # game for review -- the error status gates it downstream.
                self._error(
                    "missing_period_end",
                    f"Period {period_num} finalized without a period_end event",
                    end_anchor,
                )
            self._validate_period_lineup(on_court, anchor)
            # Sweep: every on-court player gets a player_out right after
            # the period_end.
            for team, players in sorted(on_court.items()):
                for pid in sorted(players):
                    sweep = self._mk(
                        end_anchor, PLAYER_OUT_EVENT, team, pid,
                        source="derived:lineup_sweep",
                    )
                    result.append(sweep)
            # Starter player_ins are inserted right after the period_start.
            starter_events: list[PBPEvent] = []
            for team, players in sorted(starters.items()):
                for pid in sorted(players):
                    starter_events.append(self._mk(
                        anchor, PLAYER_IN_EVENT, team, pid,
                        source="derived:starter",
                    ))
            if starter_events:
                result[pos + 1:pos + 1] = starter_events

        for e in events:
            evt = e["event"]
            team = e.get("team_id", "")
            player = e.get("player_id", "")

            if evt == PERIOD_START_EVENT:
                if in_period and period_start_pos is not None and period_anchor is not None:
                    _finalize(period_anchor)
                on_court = {}
                starters = {}
                finalized = {}
                period_start_pos = len(result)
                period_anchor = e
                period_num = e.get("period", 1)
                in_period = True
                result.append(e)
                continue

            if evt == PERIOD_END_EVENT:
                result.append(e)
                if in_period and period_start_pos is not None and period_anchor is not None:
                    _finalize(e)
                in_period = False
                continue

            if not in_period or not team or not self._is_source(e):
                result.append(e)
                continue

            court = on_court.setdefault(team, set())
            st = starters.setdefault(team, set())
            paired = sub_pairs.get(e["event_id"], frozenset()) == frozenset(
                SUBSTITUTION_EVENTS
            )
            # Between-period boundary subs exist only from period 2 on
            # (the departing player was swept at the prior period_end).
            # In period 1 the departing player started the game.
            boundary = (
                paired
                and not finalized.get(team, False)
                and period_num > 1
            )

            if evt == PLAYER_IN_EVENT:
                if boundary:
                    # Between-period boundary sub: the incoming player is
                    # a starter; the source markers are superseded by the
                    # derived ones.
                    st.add(player)
                    court.add(player)
                    boundary_ids.add(e["event_id"])
                else:
                    if player in court:
                        self._error("player_in_twice", f"player_in for on-court player {player}", e)
                    court.add(player)
            elif evt == PLAYER_OUT_EVENT:
                if boundary:
                    # The departing player was swept at the prior
                    # period_end; drop the redundant source marker.
                    boundary_ids.add(e["event_id"])
                elif player in court:
                    court.discard(player)
                else:
                    # A player_out for a player not on court proves they
                    # started the period (they are leaving now).
                    st.add(player)
            elif self._is_indicate_on_court(e) and player:
                finalized[team] = True
                if player not in court:
                    st.add(player)
                    court.add(player)

            result.append(e)

        if in_period and period_start_pos is not None and period_anchor is not None:
            _finalize(period_anchor)

        if boundary_ids:
            result = [e for e in result if e["event_id"] not in boundary_ids]

        self._reindex(result)
        return result

    def _validate_period_lineup(
        self,
        on_court: dict[str, set[str]],
        period_anchor: PBPEvent | None,
    ) -> None:
        # Every period must field lineup_size players for both teams,
        # even when a team has no events in the period at all.
        for team in (self.home_team_id, self.away_team_id):
            players = on_court.get(team, set())
            if len(players) != self.lineup_size:
                rule = "lineup_too_large" if len(players) > self.lineup_size else "lineup_too_small"
                self._error(
                    rule,
                    f"Team {team} has {len(players)} players on court "
                    f"(expected {self.lineup_size})",
                    period_anchor,
                )

    # ==================================================================
    # Stage 3 -- scoring sequences
    # ==================================================================

    def _stage_3_scoring(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Place ``pot_poss_ending_scoring_opp`` before each eligible
        scoring sequence and mark sequence-final misses."""
        # Precompute trip facts from stage-1 chains.
        ft_by_foul: dict[str, list[PBPEvent]] = {}
        for e in events:
            if not self._is_ft(e):
                continue
            chain_id = e.get("chain_id")
            if chain_id is None:
                continue
            ft_by_foul.setdefault(chain_id, []).append(e)
        for fts in ft_by_foul.values():
            last = max(fts, key=lambda x: x["seq"])
            self._trip_last_ft_ids.add(last["event_id"])

        # An and-one make: an fg_make immediately followed by a standard
        # foul whose FTs are shot by the make's team (the foul row
        # follows the make in the feed; the make's assist attribution sits
        # between them).  The make is absorbed into the trip -- its live
        # shot transition is suppressed and the trip carries the single
        # pot_poss_ending_scoring_opp.
        for i, e in enumerate(events):
            if e["event"] not in FG_MAKE_EVENTS:
                continue
            if not self._make_absorbed_by_trip(events, i):
                continue
            nxt = self._find_forward(
                events, i, skip=frozenset(FG_ASSIST_EVENTS),
                max_gap=1, cross_period=False,
            )
            if nxt is None:
                continue
            self._and_one_make_ids.add(e["event_id"])
            self._and_one_foul_ids.add(nxt["event_id"])

        result: list[PBPEvent] = []
        seq_team: str | None = None
        seq_has_ppo = False
        seq_last_shot: PBPEvent | None = None
        open_trip_foul: str | None = None

        def _close_sequence() -> None:
            nonlocal seq_last_shot, open_trip_foul
            if (
                seq_last_shot is not None
                and seq_last_shot["event"] in MISS_EVENTS
            ):
                self._sequence_final_misses.add(seq_last_shot["event_id"])
            seq_last_shot = None
            open_trip_foul = None

        for e in events:
            if self._is_shot(e):
                if self._is_ft(e):
                    foul = self._by_id.get(e.get("chain_id") or "")
                    if foul is None:
                        # ft_without_foul already recorded in stage 1.
                        result.append(e)
                        continue
                    if self._foul_family(foul) == "elevated":
                        # Elevated trips are transparent: they neither
                        # start nor continue a scoring sequence.
                        result.append(e)
                        continue
                    if foul["event_id"] in self._and_one_foul_ids:
                        # The make already opened the sequence; the FTs
                        # continue it (single attempt).
                        seq_team = e["team_id"]
                        seq_has_ppo = True
                        seq_last_shot = e
                        open_trip_foul = foul["event_id"]
                        result.append(e)
                    elif open_trip_foul == foul["event_id"]:
                        # Continuation of this trip's fresh sequence.
                        seq_team = e["team_id"]
                        seq_has_ppo = True
                        seq_last_shot = e
                        result.append(e)
                    else:
                        # A standard-foul trip always starts a fresh
                        # scoring sequence.
                        _close_sequence()
                        self._place_ppo(result, e)
                        seq_team = e["team_id"]
                        seq_has_ppo = True
                        seq_last_shot = e
                        open_trip_foul = foul["event_id"]
                        result.append(e)
                else:
                    # FG attempt.
                    if seq_team != e["team_id"] or not seq_has_ppo:
                        _close_sequence()
                        self._place_ppo(result, e)
                        seq_team = e["team_id"]
                        seq_has_ppo = True
                    seq_last_shot = e
                    result.append(e)
                continue

            if self._is_indicate_poss(e):
                _close_sequence()
                seq_team = None
                seq_has_ppo = False

            result.append(e)

        _close_sequence()
        self._reindex(result)
        self._by_id = {e["event_id"]: e for e in result}
        return result

    def _place_ppo(self, result: list[PBPEvent], shot: PBPEvent) -> None:
        """Insert a ``pot_poss_ending_scoring_opp`` immediately before *shot*.

        The shot itself is appended by the caller after placement.
        """
        ppo = self._mk(
            shot, POT_POSS_ENDING_SCORING_OPP_EVENT,
            shot["team_id"], shot.get("player_id", ""),
            chain_id=shot["event_id"], source="derived:scoring_opp",
        )
        result.append(ppo)

    # ==================================================================
    # Stage 4 -- possession
    # ==================================================================

    def _stage_4_possession(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Derive possession markers, transitions, and synthesis."""
        result: list[PBPEvent] = []
        current_poss: str | None = None
        window_turnovers = 0

        # Precompute the next-indicate-poss team for sequence-final
        # misses (team-rebound synthesis lookahead over the source stream).
        rebound_for_miss: dict[str, str] = {}
        for e in events:
            if e["event_id"] not in self._sequence_final_misses:
                continue
            if e["event"] not in MISS_EVENTS:
                continue
            nxt = self._next_indicate_poss(events, e["seq"])
            if nxt is None or nxt["event"] == PERIOD_END_EVENT:
                rebound_for_miss[e["event_id"]] = self._opp(e["team_id"])
            elif nxt["team_id"] == e["team_id"]:
                rebound_for_miss[e["event_id"]] = e["team_id"]
            else:
                rebound_for_miss[e["event_id"]] = nxt["team_id"]

        for e in events:
            evt = e["event"]
            team = e.get("team_id", "")
            ev_def = PBP_EVENTS.get(evt)
            transition = ev_def["poss_transition"] if ev_def is not None else None

            if evt == PERIOD_START_EVENT:
                # Place the period's first poss_start at the period_start
                # for the team of the period's first indicate_poss.
                first = self._next_indicate_poss(events, e["seq"])
                current_poss = first["team_id"] if first is not None and first["event"] != PERIOD_END_EVENT else None
                result.append(e)
                if current_poss:
                    ps = self._mk(e, POSS_START_EVENT, current_poss, source="derived:poss_start")
                    result.append(ps)
                window_turnovers = 0
                continue

            if evt == PERIOD_END_EVENT:
                result.append(e)
                if current_poss:
                    pe = self._mk(e, POSS_END_EVENT, current_poss, source="derived:poss_end")
                    result.append(pe)
                current_poss = None
                window_turnovers = 0
                continue

            if evt == JUMP_BALL_WIN_EVENT:
                # A real turnover in the current window -- or one recorded
                # immediately after the jump ball (sources log the held-ball
                # team turnover after the jump row) -- means the possession
                # change is already recorded: skip synthesis and skip the
                # jump-ball's own transition.  The "immediately after" rule
                # is config-driven via the chain rule's ``superseded_by``
                # and ``max_gap``.
                jb_rule = CHAIN_RULES["jump_ball_turnover"]
                real_turnover = (
                    window_turnovers > 0
                    or self._has_following_event(
                        events, e["seq"],
                        event_types=jb_rule["superseded_by"],
                        max_gap=jb_rule["max_gap"],
                    )
                )
                if (
                    current_poss is not None
                    and current_poss != team
                    and not real_turnover
                    and jb_rule["synthesize"] == "team_turnover"
                ):
                    # Synthesize a team turnover for the possessor placed
                    # immediately before the jump-ball; its always
                    # transition handles the handoff.
                    tov = self._mk(
                        e, TURNOVER_EVENT, current_poss, "",
                        chain_id=e["event_id"], source="derived:jump_ball_turnover",
                    )
                    result.append(tov)
                    self._emit_pair(result, current_poss, team, tov)
                    current_poss = team
                    window_turnovers = 0
                result.append(e)
                continue

            if transition is not None:
                if evt == TURNOVER_EVENT and self._is_source(e):
                    window_turnovers += 1
                result.append(e)
                fired = self._handle_transition(
                    e, transition, current_poss, team, result,
                )
                if fired is not None:
                    current_poss = fired[1]
                    window_turnovers = 0
                continue

            if self._is_indicate_poss(e):
                if current_poss is None:
                    ps = self._mk(e, POSS_START_EVENT, team, source="derived:poss_start")
                    result.append(ps)
                    current_poss = team
                    window_turnovers = 0
                elif current_poss != team:
                    self._error(
                        "poss_change_without_transition",
                        f"indicate_poss by {team} while {current_poss} possesses",
                        e,
                    )
                result.append(e)
                continue

            # Team-rebound synthesis: place a team rebound right after a
            # sequence-final miss with no assigned rebound.
            if (
                evt in MISS_EVENTS
                and e["event_id"] in self._sequence_final_misses
                and CHAIN_RULES[O_REB_EVENT]["synthesize"] == "team_rebound"
            ):
                has_real = any(
                    x.get("chain_id") == e["event_id"]
                    and x["event"] in REBOUND_EVENTS
                    for x in events
                )
                if not has_real:
                    reb_team = rebound_for_miss.get(e["event_id"])
                    if reb_team:
                        evt_type = O_REB_EVENT if reb_team == e["team_id"] else D_REB_EVENT
                        reb = self._mk(
                            e, evt_type, reb_team, "",
                            chain_id=e["event_id"], source="derived:team_rebound",
                        )
                        result.append(e)
                        if evt_type == D_REB_EVENT:
                            # The synthesized d_reb closes the shooter's
                            # window and opens the rebounder's (its
                            # always-transition).
                            if current_poss is not None:
                                if current_poss != e["team_id"]:
                                    self._error(
                                        "poss_mismatch",
                                        f"d_reb by {reb_team} while {current_poss} possesses",
                                        reb,
                                    )
                                else:
                                    self._emit_pair(
                                        result, current_poss, reb_team, reb,
                                    )
                                    current_poss = reb_team
                            else:
                                self._emit_start(result, reb_team, reb)
                                current_poss = reb_team
                            window_turnovers = 0
                        else:
                            if current_poss is None:
                                ps = self._mk(reb, POSS_START_EVENT, reb_team, source="derived:poss_start")
                                result.append(ps)
                                current_poss = reb_team
                                window_turnovers = 0
                            elif current_poss != reb_team:
                                self._error(
                                    "poss_change_without_transition",
                                    f"indicate_poss by {reb_team} while {current_poss} possesses",
                                    reb,
                                )
                        result.append(reb)
                        continue

            result.append(e)

        self._reindex(result)
        return result

    def _has_following_event(
        self,
        events: list[PBPEvent],
        idx: int,
        *,
        event_types: tuple[str, ...],
        max_gap: int,
    ) -> bool:
        """True when a source event of one of *event_types* follows within
        ``max_gap`` non-skipped events of *idx*.

        Config-driven via a chain rule's ``superseded_by``/``max_gap``:
        the real event (e.g. a held-ball team turnover after a jump-ball
        row) carries the possession change, so synthesis is unnecessary.
        """
        if not event_types:
            return False
        for gap, cand in enumerate(events[idx + 1:], start=1):
            if cand["event"] == PERIOD_END_EVENT:
                return False
            if cand["event"] in event_types and self._is_source(cand):
                return True
            if max_gap >= 0 and gap > max_gap:
                return False
        return False

    def _handle_transition(
        self,
        e: PBPEvent,
        transition: PossTransition,
        current_poss: str | None,
        team: str,
        result: list[PBPEvent],
    ) -> tuple[str, str] | None:
        """Apply one event's possession transition.

        Returns ``(POSS_START_EVENT, new_team)`` when possession changed
        hands (so the caller updates state), or ``None`` when nothing
        fired.
        """
        evt = e["event"]
        condition = transition.get("condition")
        end_spec = transition.get("end_team")

        if condition == "always":
            if evt in (D_REB_EVENT, TURNOVER_EVENT):
                end_team = self._opp(team) if end_spec == "opponent" else team
                if current_poss is not None:
                    if evt == D_REB_EVENT and current_poss == team:
                        # The possessor defended a missed free throw during
                        # an elevated-foul pause and retained possession:
                        # no possession change, no error.
                        return None
                    if current_poss != end_team:
                        self._error(
                            "poss_mismatch",
                            f"{evt} by {team} while {current_poss} possesses",
                            e,
                        )
                        return None
                    start_team = team if evt == D_REB_EVENT else self._opp(team)
                    self._emit_pair(result, current_poss, start_team, e)
                    return (POSS_START_EVENT, start_team)
                start_team = team if evt == D_REB_EVENT else self._opp(team)
                self._emit_start(result, start_team, e)
                return (POSS_START_EVENT, start_team)
            return None

        if condition == "live_shot":
            if not self._is_shot(e) or evt in MISS_EVENTS:
                return None
            if self._is_ft(e):
                foul = self._by_id.get(e.get("chain_id") or "")
                if foul is None:
                    return None
                if self._foul_family(foul) == "elevated":
                    return None  # elevated FTs never transition
                if e["event_id"] not in self._trip_last_ft_ids:
                    return None  # mid-trip FT
            else:
                if e["event_id"] in self._and_one_make_ids:
                    return None  # and-one make absorbed into its trip
            if current_poss is None or current_poss != team:
                if current_poss is not None:
                    self._error(
                        "poss_mismatch",
                        f"{evt} by {team} while {current_poss} possesses",
                        e,
                    )
                return None
            self._emit_pair(result, team, self._opp(team), e)
            return (POSS_START_EVENT, self._opp(team))

        return None

    def _emit_pair(
        self,
        result: list[PBPEvent],
        end_team: str,
        start_team: str,
        anchor: PBPEvent,
    ) -> None:
        pe = self._mk(anchor, POSS_END_EVENT, end_team, source="derived:poss_end")
        ps = self._mk(anchor, POSS_START_EVENT, start_team, source="derived:poss_start")
        result.append(pe)
        result.append(ps)

    def _emit_start(self, result: list[PBPEvent], start_team: str, anchor: PBPEvent) -> None:
        ps = self._mk(anchor, POSS_START_EVENT, start_team, source="derived:poss_start")
        result.append(ps)

    def _next_indicate_poss(
        self, events: list[PBPEvent], idx: int,
    ) -> PBPEvent | None:
        """Next ``indicate_poss`` event (or period_end) after *idx*."""
        for j in range(idx + 1, len(events)):
            cand = events[j]
            if cand["event"] == PERIOD_END_EVENT:
                return cand
            if self._is_indicate_poss(cand):
                return cand
        return None

    # ==================================================================
    # Stage 5 -- cleanup + validation
    # ==================================================================

    def _stage_5_cleanup(self, events: list[PBPEvent]) -> list[PBPEvent]:
        """Drop empty possession windows, then validate invariants."""
        # Reconstruct possession windows by FIFO pairing per team.
        windows: list[tuple[PBPEvent, PBPEvent]] = []
        open_windows: dict[str, PBPEvent] = {}
        for e in events:
            if e["event"] == POSS_START_EVENT:
                if e["team_id"] not in open_windows:
                    open_windows[e["team_id"]] = e
            elif e["event"] == POSS_END_EVENT:
                ps = open_windows.pop(e["team_id"], None)
                if ps is not None:
                    windows.append((ps, e))

        # Empty-window cleanup: a window with no indicate_poss by its
        # team is not a possession -- remove both markers.
        remove_ids: set[str] = set()
        for ps, pe in windows:
            team = ps["team_id"]
            start, end = ps["seq"], pe["seq"]
            has_indication = any(
                start < e.get("seq", 0) < end
                and self._is_indicate_poss(e)
                and e["team_id"] == team
                for e in events
            )
            if not has_indication:
                remove_ids.update({ps["event_id"], pe["event_id"]})

        kept = [e for e in events if e["event_id"] not in remove_ids]
        self._reindex(kept)
        self._validate_invariants(kept)
        return kept

    def _validate_invariants(self, events: list[PBPEvent]) -> None:
        """Run pairing, on-court, and end-of-game checks over the final
        stream.  Errors are accumulated (finish-the-game-first)."""
        # --- Standard fouls must carry the fouled player. ---
        for e in events:
            if (
                PBP_EVENTS.get(e["event"], {}).get("foul_family") == "standard"
                and not e.get("fouled_player_id")
            ):
                self._error(
                    "foul_without_fouled_player",
                    f"Standard foul {e['event']} has no fouled player",
                    e,
                )

        # --- Possession marker pairing (per team). ---
        poss_open: dict[str, str] = {}
        for e in events:
            if e["event"] == POSS_START_EVENT:
                if e["team_id"] in poss_open:
                    self._error("double_poss_open", "poss_start while a window is open", e)
                poss_open[e["team_id"]] = e["event_id"]
            elif e["event"] == POSS_END_EVENT:
                if e["team_id"] not in poss_open:
                    self._error("poss_end_no_open", "poss_end with no open window", e)
                else:
                    del poss_open[e["team_id"]]
        for team, start_id in poss_open.items():
            self._error(
                "poss_marker_unpaired",
                f"Unpaired poss_start ({start_id}) for team {team}",
            )

        # --- On-court activity + player marker pairing (per team). ---
        on_court: dict[str, set[str]] = {}
        player_open: dict[str, list[str]] = {}
        final_period_end = max(
            (e["seq"] for e in events if e["event"] == PERIOD_END_EVENT),
            default=None,
        )
        except_events = frozenset(INVARIANTS["event_off_court"]["except_events"])

        for e in events:
            evt = e["event"]
            team = e.get("team_id", "")
            player = e.get("player_id", "")

            if (
                self._is_source(e)
                and final_period_end is not None
                and e["seq"] > final_period_end
            ):
                self._error("activity_after_end", "Event activity after the final period_end", e)
                continue

            if evt == PLAYER_IN_EVENT and team and player:
                on_court.setdefault(team, set()).add(player)
                player_open.setdefault(player, []).append(e["event_id"])
            elif evt == PLAYER_OUT_EVENT and team and player:
                on_court.setdefault(team, set()).discard(player)
                if player_open.get(player):
                    player_open[player].pop()
                elif self._is_source(e):
                    self._error("player_out_not_on_court", f"player_out for off-court player {player}", e)
            elif (
                self._is_indicate_on_court(e)
                and team
                and player
                and evt not in except_events
            ):
                if player not in on_court.get(team, set()):
                    self._error(
                        "event_off_court",
                        f"On-court activity by {player} ({evt}) not in the derived lineup",
                        e,
                    )

        for player, opens in player_open.items():
            if opens:
                self._error(
                    "player_marker_unpaired",
                    f"Unpaired player_in ({opens[-1]}) for player {player}",
                )
