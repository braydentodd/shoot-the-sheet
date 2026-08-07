"""
Shoot the Sheet - PBP Accumulation Engine

Config-driven accumulation of standard PBP events into per-game
result sets for teams and players.

Reads the single unified ``RESULT_SET_FIELDS`` dict from
:data:`src.definitions.pbp` and applies it generically.  Each field
defines which result sets it appears in and how to compute it.

All on-court / possession window logic operates on ``seq`` -- never
``secs``.  Clock-derived fields (``secs``, possession seconds) read only
the events they need: a value is computed from the events the field
consumes and outputs ``None`` when those events carry no clock
(per-event clock gating).

Convention: code lives in lib.  Config/dicts/constants live in
definitions (src.definitions.pbp).
"""

import logging
from typing import Any

from src.definitions.pbp import (
    PBP_EVENTS,
    PERIOD_END_EVENT,
    PLAYER_IN_EVENT,
    PLAYER_OUT_EVENT,
    POSS_END_EVENT,
    POSS_START_EVENT,
    RESULT_SET_FIELDS,
    PBPEvent,
)
from src.lib.math_evaluator import evaluate as eval_math

logger = logging.getLogger(__name__)


# ============================================================================
# RESULT SET ACCUMULATION
# ============================================================================


def accumulate_result_set(
    events: list[PBPEvent],
    scope: str,
    entity_id: str,
    opp_entity_id: str | None = None,
    player_team_id: str | None = None,
    on_court_intervals: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Accumulate standard PBP events into one result-set row.

    Generic over scope.  Iterates ``RESULT_SET_FIELDS`` once, computing
    every field that appears in *scope* (a ``PBP_SCOPES`` member).  The
    same field is computed once per scope -- ``team`` / ``opp_team`` for
    a team's self/opponent row, ``player`` / ``opp_player`` /
    ``on_player`` for a player's own/opponent/on-court row -- so a DB
    row is assembled from several scope rows via the (field, scope)
    column map.

    Args:
        events: Standard PBPEvent rows for a single game (final seq).
        scope: Which ``PBP_SCOPES`` member to compute.
        entity_id: Subject entity ID (team_id or player_id).
        opp_entity_id: Opposing entity ID.
        player_team_id: Subject player's team ID (player scopes only).
        on_court_intervals: Court-time intervals as ``(start_seq, end_seq)``
            pairs (player scopes only).

    Returns:
        Dict of field_name -> value for this scope.
    """
    partitions = _build_partitions(
        events, entity_id, opp_entity_id, player_team_id, on_court_intervals,
    )

    result: dict[str, Any] = {}

    for field_name, field_def in RESULT_SET_FIELDS.items():
        if scope not in field_def.get("result_sets", ()):
            continue

        op = field_def["op"]

        if op == "count":
            event_set = set(field_def["events"])
            result[field_name] = sum(
                1 for e in partitions[scope] if e["event"] in event_set
            )

        elif op == "derived":
            result[field_name] = _evaluate_derived(field_def, result)

        elif op == "special":
            result[field_name] = _handle_special(
                field_name,
                scope,
                events,
                partitions,
                entity_id,
                opp_entity_id,
                player_team_id,
                on_court_intervals,
            )

    return result


# ==============================================================================
# EVENT PARTITIONING
# ==============================================================================


def _build_partitions(
    events: list[PBPEvent],
    entity_id: str,
    opp_entity_id: str | None,
    player_team_id: str | None,
    on_court_intervals: list[tuple[int, int]] | None,
) -> dict[str, list[PBPEvent]]:
    """Partition events by scope for the given entity context."""
    return {
        "team": [e for e in events if e["team_id"] == entity_id],
        "opp_team": [
            e for e in events
            if opp_entity_id and e["team_id"] == opp_entity_id
        ],
        "player": [
            e for e in events if e["player_id"] == entity_id
        ],
        "opp_player": [
            e for e in events
            if opp_entity_id
            and e["team_id"] == opp_entity_id
            and _is_on_court(e, on_court_intervals)
        ],
        "on_player": [
            e for e in events
            if player_team_id
            and e["team_id"] == player_team_id
            and e["player_id"] != entity_id
            and _is_on_court(e, on_court_intervals)
        ],
    }


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
         if e["event"] == PLAYER_IN_EVENT and e.get("player_id") == player_id),
    )
    outs = sorted(
        (e["seq"] for e in events
         if e["event"] == PLAYER_OUT_EVENT and e.get("player_id") == player_id),
    )
    if not ins and not outs:
        return None
    intervals: list[tuple[int, int]] = []
    out_idx = 0
    num_outs = len(outs)
    for start in ins:
        while out_idx < num_outs and outs[out_idx] < start:
            out_idx += 1
        if out_idx < num_outs:
            intervals.append((start, outs[out_idx]))
            out_idx += 1
    return intervals or None


# ============================================================================
# SPECIAL HANDLERS
# ============================================================================


def _handle_special(
    field: str,
    scope: str,
    all_events: list[PBPEvent],
    partitions: dict[str, list[PBPEvent]],
    entity_id: str,
    opp_entity_id: str | None,
    player_team_id: str | None,
    on_court_intervals: list[tuple[int, int]] | None,
) -> Any:
    """Compute a special field for one scope.

    ``scope`` is the row the value is computed for: "team" (self),
    "opp_team" (opponent), "player" (the player's own value),
    "opp_player" (opponents while the player is on court), or
    "on_player" (the team's value while the player is on court).
    """
    if field == "points":
        return _sum_points(partitions.get(scope, []))

    if field == "secs":
        if scope == "team":
            # Derive from period_end events (game length), not max
            # team-event timestamp.  None when any period_end is untimed
            # (never report 0 when measurement was impossible).
            period_ends = [e for e in all_events if e["event"] == PERIOD_END_EVENT]
            timed_ends = [e["secs"] for e in period_ends if e["secs"] is not None]
            if not timed_ends or len(timed_ends) != len(period_ends):
                return None
            return max(timed_ends)
        return _calc_player_secs(all_events, entity_id)

    if field == "win":
        team_id = entity_id if scope == "team" else player_team_id
        # DNP (no on-court intervals) -> no win value for players.
        if scope != "team" and (not player_team_id or not on_court_intervals):
            return None
        # Fail closed: without the opponent's events a win/loss cannot be
        # decided -- never report a win from a zero-point comparison.
        if not opp_entity_id:
            return None
        team_pts = _sum_points(
            [e for e in all_events if e["team_id"] == team_id]
        )
        opp_pts = _sum_points(
            [e for e in all_events if e["team_id"] == opp_entity_id]
        )
        return team_pts > opp_pts if team_pts != opp_pts else None

    if field == "start":
        # Started the game = a derived starter player_in in the first period.
        for e in all_events:
            if (
                e["event"] == PLAYER_IN_EVENT
                and e.get("period") == 1
                and e.get("source") == "derived:starter"
                and e.get("player_id") == entity_id
            ):
                return True
        return False

    if field == "poss":
        if scope == "team":
            return sum(
                1 for e in all_events
                if e["event"] == POSS_START_EVENT and e["team_id"] == entity_id
            )
        if scope == "opp_team":
            if opp_entity_id:
                return sum(
                    1 for e in all_events
                    if e["event"] == POSS_START_EVENT
                    and e["team_id"] == opp_entity_id
                )
            return None
        if scope == "on_player":
            if player_team_id:
                return _player_possession_count(
                    all_events, player_team_id, entity_id, on_court_intervals,
                )
            return None
        if scope == "opp_player":
            if opp_entity_id:
                return _player_possession_count(
                    all_events, opp_entity_id, entity_id, on_court_intervals,
                )
            return None
        return None

    if field == "o_poss_secs":
        # Offensive possession seconds use the team's own windows; the
        # opponent's offensive possession seconds are the same field in
        # the ``opp_team`` / ``opp_player`` scopes (no ``d_poss_secs``
        # mirror field exists -- DB columns map the opp scopes instead).
        if scope == "team":
            return _calc_possession_secs(all_events, entity_id)
        if scope == "opp_team":
            if opp_entity_id:
                return _calc_possession_secs(all_events, opp_entity_id)
            return None
        if scope == "on_player":
            if player_team_id:
                return _player_possession_secs(
                    all_events, player_team_id, entity_id, on_court_intervals,
                )
            return None
        if scope == "opp_player":
            if opp_entity_id:
                return _player_possession_secs(
                    all_events, opp_entity_id, entity_id, on_court_intervals,
                )
            return None
        return None

    return None


# ============================================================================
# POSSESSION CALCULATIONS (seq-paired, per-window clock)
# ============================================================================


def _pair_windows(
    events: list[PBPEvent],
    team_id: str,
) -> list[tuple[PBPEvent, PBPEvent]]:
    """Pair ``poss_start``/``poss_end`` markers per team, in seq order."""
    open_marker: PBPEvent | None = None
    windows: list[tuple[PBPEvent, PBPEvent]] = []
    for e in events:
        if e["event"] == POSS_START_EVENT and e["team_id"] == team_id:
            open_marker = e
        elif (
            e["event"] == POSS_END_EVENT
            and e["team_id"] == team_id
            and open_marker is not None
        ):
            windows.append((open_marker, e))
            open_marker = None
    return windows


def _calc_possession_secs(
    events: list[PBPEvent],
    team_id: str,
) -> int | None:
    """Sum seconds between poss_start/poss_end pairs for a team.

    Per-window clock gating: a window counts toward the total only when
    both boundary markers carry ``secs``; returns ``None`` when no
    window is timed (never report 0 when measurement was impossible).
    """
    windows = _pair_windows(events, team_id)
    if not windows:
        return None
    total = 0
    timed = 0
    for start, end in windows:
        start_secs, end_secs = start.get("secs"), end.get("secs")
        if start_secs is None or end_secs is None:
            continue
        timed += 1
        total += max(0, end_secs - start_secs)
    if timed == 0:
        return None
    return total if total > 0 else None


def _player_possession_windows(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> tuple[int, int, int]:
    """Return qualified windows, timed windows, and total secs.

    A player qualifies for a possession window if they were on court
    during part of the window AND at least one of the window's
    ``indicate_poss`` events falls inside their on-court span (seq-based).
    A window's seconds are included only when both boundary markers
    carry ``secs`` (per-window clock gating); ``timed_count`` is how many
    qualified windows were measurable.
    """
    if on_court_intervals is None:
        return 0, 0, 0

    windows = _pair_windows(events, team_id)
    if not windows:
        return 0, 0, 0

    count = 0
    timed_count = 0
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
                start_secs, end_secs = start.get("secs"), end.get("secs")
                if start_secs is not None and end_secs is not None:
                    timed_count += 1
                    total_secs += max(0, end_secs - start_secs)
                break  # count this window once

    return count, timed_count, total_secs


def _player_possession_count(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> int | None:
    """Count qualified possession windows for a player (seq-based)."""
    count, _, _ = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    return count if count > 0 else None


def _player_possession_secs(
    events: list[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: list[tuple[int, int]] | None,
) -> int | None:
    """Sum full possession secs for qualified windows for a player.

    Per-window clock gating: returns ``None`` when the player qualifies
    for windows but none is timed.
    """
    count, timed_count, total = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    if count == 0 or timed_count == 0:
        return None
    return total if total > 0 else None


def _calc_player_secs(
    events: list[PBPEvent],
    player_id: str,
) -> int | None:
    """Sum seconds between player_in and player_out events (seq-paired).

    Reads only the player's own interval boundary markers: an interval
    counts when both boundaries carry ``secs``; returns ``None`` when
    the player has intervals but none is timed.
    """
    intervals = player_on_court_intervals(events, player_id)
    if not intervals:
        return None
    by_seq = {e["seq"]: e for e in events}
    total = 0
    timed = 0
    for start_seq, end_seq in intervals:
        start_secs = by_seq[start_seq].get("secs")
        end_secs = by_seq[end_seq].get("secs")
        if start_secs is None or end_secs is None:
            continue
        timed += 1
        total += max(0, end_secs - start_secs)
    if timed == 0:
        return None
    return total if total > 0 else None
