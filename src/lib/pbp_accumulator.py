"""
Shoot the Sheet - PBP Accumulation Engine

Config-driven accumulation of standard PBP events into per-game
result sets for teams and players.

Reads the single unified ``RESULT_SET_FIELDS`` dict from
:data:`src.definitions.pbp` and applies it generically.  Each field
defines which result sets it appears in and how to compute it.

All on-court / possession window logic operates on ``seq`` -- never
``secs``.  Clock-derived fields (``secs``, possession seconds) are
``requires_clock`` gated and output ``None`` for untimed games.

Convention: code lives in lib.  Config/dicts/constants live in
definitions (src.definitions.pbp).
"""

import logging
from typing import Any

from src.definitions.pbp import PBP_EVENTS, RESULT_SET_FIELDS, PBPEvent
from src.lib.math_evaluator import evaluate as eval_math

logger = logging.getLogger(__name__)


# ============================================================================
# RESULT SET ACCUMULATION
# ============================================================================


def accumulate_result_set(
    events: list[PBPEvent],
    result_set: str,
    entity_id: str,
    opp_entity_id: str | None = None,
    player_team_id: str | None = None,
    on_court_intervals: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Accumulate standard PBP events into one result set row.

    Generic over result-set type.  Iterates ``RESULT_SET_FIELDS`` once,
    skipping fields that don't apply to *result_set*.

    Args:
        events: Standard PBPEvent rows for a single game (final seq).
        result_set: Which result set to produce ("team" or "player").
        entity_id: Subject entity ID (team_id or player_id).
        opp_entity_id: Opposing entity ID.
        player_team_id: Subject player's team ID (player result set only).
        on_court_intervals: Court-time intervals as ``(start_seq, end_seq)``
            pairs (player result set only).

    Returns:
        Dict of field_name -> value.
    """
    timed = all(e.get("secs") is not None for e in events)

    partitions = _build_partitions(
        events, result_set, entity_id, opp_entity_id,
        player_team_id, on_court_intervals,
    )

    result: dict[str, Any] = {}

    for field_name, field_def in RESULT_SET_FIELDS.items():
        rs_map = field_def.get("result_sets", {})
        if result_set not in rs_map:
            continue

        op = field_def["op"]
        scope_or_handler = rs_map[result_set]

        if op == "count":
            source = _scope_events(scope_or_handler, partitions)
            event_set = set(field_def["events"])
            result[field_name] = sum(
                1 for e in source if e["event"] in event_set
            )

        elif op == "derived":
            result[field_name] = _evaluate_derived(field_def, result)

        elif op == "special":
            if field_def.get("requires_clock") and not timed:
                result[field_name] = None
                continue
            result[field_name] = _handle_special(
                scope_or_handler,
                events,
                partitions,
                entity_id,
                opp_entity_id,
                player_team_id,
                on_court_intervals,
                result,
            )

    return result


# ==============================================================================
# EVENT PARTITIONING
# ==============================================================================


def _build_partitions(
    events: list[PBPEvent],
    result_set: str,
    entity_id: str,
    opp_entity_id: str | None,
    player_team_id: str | None,
    on_court_intervals: list[tuple[int, int]] | None,
) -> dict[str, list[PBPEvent]]:
    """Partition events by scope for the given result set type."""
    if result_set == "team":
        return {
            "team": [e for e in events if e["team_id"] == entity_id],
            "opp_team": [
                e for e in events
                if opp_entity_id and e["team_id"] == opp_entity_id
            ],
        }

    if result_set == "player":
        player_events = [
            e for e in events if e["player_id"] == entity_id
        ]
        opp_events = [
            e for e in events
            if opp_entity_id
            and e["team_id"] == opp_entity_id
            and _is_on_court(e, on_court_intervals)
        ]
        on_events = [
            e for e in events
            if player_team_id
            and e["team_id"] == player_team_id
            and e["player_id"] != entity_id
            and _is_on_court(e, on_court_intervals)
        ]
        return {
            "player": player_events,
            "opp_player": opp_events,
            "on_player": on_events,
        }

    return {}


def _scope_events(
    scope: str,
    partitions: dict[str, list[PBPEvent]],
) -> list[PBPEvent]:
    """Route to the correct event list based on scope."""
    return partitions.get(scope, [])


# ============================================================================
# COMPUTATION HELPERS
# ============================================================================


def _evaluate_derived(
    field_def: dict[str, Any],
    result: dict[str, Any],
) -> float | None:
    """Evaluate a derived field formula using the safe math evaluator."""
    formula = field_def["formula"]
    fields = field_def["fields"]
    variables: dict[str, float] = {}
    for f in fields:
        val = result.get(f)
        if val is None:
            return None
        try:
            variables[f] = float(val)
        except (ValueError, TypeError):
            return None
    try:
        return eval_math(formula, variables)
    except (TypeError, NameError, ArithmeticError, SyntaxError) as exc:
        logger.debug(
            "Derived formula failed: %s with %s -- %s", formula, variables, exc
        )
        return None


def _is_on_court(
    event: PBPEvent,
    on_court_intervals: list[tuple[int, int]] | None = None,
) -> bool:
    """Check if an event falls within any on-court interval (by seq)."""
    if on_court_intervals is None:
        return True
    seq = event.get("seq", 0)
    return any(start <= seq <= end for start, end in on_court_intervals)


def _sum_points(events: list[PBPEvent]) -> int:
    """Sum points from a list of events (points live in PBP_EVENTS)."""
    return sum(PBP_EVENTS[e["event"]]["points"] for e in events)


def player_on_court_intervals(
    events: list[PBPEvent],
    player_id: str,
) -> list[tuple[int, int]] | None:
    """Build ``(start_seq, end_seq)`` on-court intervals for a player.

    Pairs the player's ``player_in``/``player_out`` markers in seq
    order.  Returns ``None`` when the player has no intervals.
    """
    ins = sorted(
        (e["seq"] for e in events
         if e["event"] == "player_in" and e.get("player_id") == player_id),
    )
    outs = sorted(
        (e["seq"] for e in events
         if e["event"] == "player_out" and e.get("player_id") == player_id),
    )
    if not ins and not outs:
        return None
    intervals: list[tuple[int, int]] = []
    for start in ins:
        end = next((o for o in outs if o >= start), None)
        if end is not None:
            intervals.append((start, end))
    return intervals or None


# ============================================================================
# SPECIAL HANDLERS
# ============================================================================


def _handle_special(
    handler: str,
    all_events: list[PBPEvent],
    partitions: dict[str, list[PBPEvent]],
    entity_id: str,
    opp_entity_id: str | None,
    player_team_id: str | None,
    on_court_intervals: list[tuple[int, int]] | None,
    result: dict[str, Any],
) -> Any:
    """Dispatch a special field handler by name."""

    # -- Team handlers --
    if handler == "team_secs":
        # Derive from period_end events (game length), not max team-event timestamp.
        period_ends = [e for e in all_events if e["event"] == "period_end"]
        if period_ends:
            return max(e["secs"] for e in period_ends)
        return None

    if handler == "team_o_poss_secs":
        return _calc_possession_secs(all_events, entity_id)

    if handler == "opp_team_o_poss_secs":
        if opp_entity_id:
            return _calc_possession_secs(all_events, opp_entity_id)
        return None

    if handler == "team_poss":
        return sum(1 for e in all_events
                   if e["event"] == "poss_start" and e["team_id"] == entity_id)

    if handler == "opp_team_poss":
        if opp_entity_id:
            return sum(1 for e in all_events
                       if e["event"] == "poss_start" and e["team_id"] == opp_entity_id)
        return None

    if handler == "player_start":
        # Started the game = a derived starter player_in in the first period.
        for e in all_events:
            if (
                e["event"] == "player_in"
                and e.get("period") == 1
                and e.get("source") == "derived:starter"
                and e.get("player_id") == entity_id
            ):
                return True
        return False

    if handler == "team_win":
        team_events = [e for e in all_events if e["team_id"] == entity_id]
        team_pts = _sum_points(team_events)
        opp_events = [e for e in all_events
                      if opp_entity_id and e["team_id"] == opp_entity_id]
        opp_pts = _sum_points(opp_events)
        return team_pts > opp_pts if team_pts != opp_pts else None

    # -- Player handlers --
    if handler == "player_win":
        # DNP (no on-court intervals) -> no win value
        if not player_team_id or not on_court_intervals:
            return None
        team_events = [e for e in all_events if e["team_id"] == player_team_id]
        team_pts = _sum_points(team_events)
        opp_events = [e for e in all_events
                      if opp_entity_id and e["team_id"] == opp_entity_id]
        opp_pts = _sum_points(opp_events)
        return team_pts > opp_pts if team_pts != opp_pts else None

    if handler == "player_secs":
        return _calc_player_secs(all_events, entity_id)

    if handler == "player_o_poss_secs":
        if player_team_id:
            return _player_possession_secs(
                all_events, player_team_id, entity_id, on_court_intervals)
        return None

    if handler == "opp_player_o_poss_secs":
        if opp_entity_id:
            return _player_possession_secs(
                all_events, opp_entity_id, entity_id, on_court_intervals)
        return None

    if handler == "player_poss":
        if player_team_id:
            return _player_possession_count(
                all_events, player_team_id, entity_id, on_court_intervals)
        return None

    if handler == "player_opp_poss":
        if opp_entity_id:
            return _player_possession_count(
                all_events, opp_entity_id, entity_id, on_court_intervals)
        return None

    return None


# ============================================================================
# POSSESSION CALCULATIONS (seq-paired, clock-gated)
# ============================================================================


def _pair_windows(
    events: list[PBPEvent],
    team_id: str,
) -> list[tuple[PBPEvent, PBPEvent]]:
    """Pair ``poss_start``/``poss_end`` markers per team, in seq order."""
    open_marker: PBPEvent | None = None
    windows: list[tuple[PBPEvent, PBPEvent]] = []
    for e in events:
        if e["event"] == "poss_start" and e["team_id"] == team_id:
            open_marker = e
        elif e["event"] == "poss_end" and e["team_id"] == team_id:
            if open_marker is not None:
                windows.append((open_marker, e))
                open_marker = None
    return windows


def _calc_possession_secs(
    events: list[PBPEvent],
    team_id: str,
) -> int | None:
    """Sum seconds between poss_start/poss_end pairs for a team.

    Clock-gated: returns ``None`` when the game has no clock.
    """
    if any(e.get("secs") is None for e in events):
        return None
    windows = _pair_windows(events, team_id)
    if not windows:
        return None
    total = sum(
        max(0, (end["secs"] or 0) - (start["secs"] or 0))
        for start, end in windows
    )
    return total if total > 0 else None


def _player_possession_windows(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> tuple[int, int]:
    """Count possession windows and total secs where a player qualifies.

    A player qualifies for a possession window if they were on court
    during part of the window AND at least one of the window's
    ``indicate_poss`` events falls inside their on-court span (seq-based).
    """
    if on_court_intervals is None:
        return 0, 0

    windows = _pair_windows(events, team_id)
    if not windows:
        return 0, 0

    count = 0
    total_secs = 0
    for start, end in windows:
        w_start, w_end = start["seq"], end["seq"]

        # Check each court interval for overlap with this window.
        for oc_start, oc_end in on_court_intervals:
            overlap_start = max(w_start, oc_start)
            overlap_end = min(w_end, oc_end)
            if overlap_start >= overlap_end:
                continue
            # Any indicate_poss event by this team in the overlap?
            has_event = any(
                PBP_EVENTS.get(e["event"], {}).get("indicate_poss")
                and e["team_id"] == team_id
                and overlap_start <= e["seq"] < overlap_end
                for e in events
            )
            if has_event:
                count += 1
                if any(e.get("secs") is None for e in events):
                    total_secs += 0
                else:
                    total_secs += max(0, (end["secs"] or 0) - (start["secs"] or 0))
                break  # count this window once

    return count, total_secs


def _player_possession_count(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> int | None:
    """Count qualified possession windows for a player."""
    count, _ = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    return count if count > 0 else None


def _player_possession_secs(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> int | None:
    """Sum full possession secs for qualified windows for a player."""
    if any(e.get("secs") is None for e in events):
        return None
    count, total = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    return total if count > 0 else None


def _calc_player_secs(
    events: list[PBPEvent],
    player_id: str,
) -> int | None:
    """Sum seconds between player_in and player_out events (seq-paired).

    Clock-gated: returns ``None`` when the game has no clock.
    """
    if any(e.get("secs") is None for e in events):
        return None
    intervals = player_on_court_intervals(events, player_id)
    if not intervals:
        return None
    total = 0
    for start_seq, end_seq in intervals:
        start = next(e for e in events if e["seq"] == start_seq)
        end = next(e for e in events if e["seq"] == end_seq)
        total += max(0, (end["secs"] or 0) - (start["secs"] or 0))
    return total if total > 0 else None
