"""
Shoot the Sheet - PBP Accumulation Engine

Config-driven accumulation of standard PBP events into per-game
result sets for teams and players.

Reads the single unified RESULT_SET_FIELDS dict from
:data:`src.definitions.pbp` and applies it generically.  Each field
defines which result sets it appears in and how to compute it.

Convention: code lives in lib.  Config/dicts/constants live in
definitions (src.definitions.pbp).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.definitions.pbp import (
    PBPEvent,
    RESULT_SET_FIELDS,
    EVENT_SORT_PRIORITY,
    FG_MAKE_EVENTS,
    POSSESSION_EVENTS,
)
from src.lib.math_evaluator import evaluate as eval_math

logger = logging.getLogger(__name__)


# ============================================================================
# EVENT ID RENUMBERING
# ============================================================================


def _renumber_event_ids(
    events: List[PBPEvent],
) -> List[PBPEvent]:
    """Assign sequential event_ids (1, 2, 3, ...) sorted by (secs, event)."""
    events.sort(key=lambda e: (
        e["secs"],
        EVENT_SORT_PRIORITY.get(e["event"], 50),
        e["event_id"],
    ))
    for i, e in enumerate(events):
        e["event_id"] = i + 1
    return events


# ============================================================================
# RESULT SET ACCUMULATION
# ============================================================================


def accumulate_result_set(
    events: List[PBPEvent],
    result_set: str,
    entity_id: str,
    opp_entity_id: Optional[str] = None,
    player_team_id: Optional[str] = None,
    on_court_intervals: Optional[List[Tuple[int, int]]] = None,
) -> Dict[str, Any]:
    """Accumulate standard PBP events into one result set row.

    Generic over result-set type.  Iterates RESULT_SET_FIELDS once,
    skipping fields that don't apply to *result_set*.

    Args:
        events: Standard PBPEvent rows for a single game.
        result_set: Which result set to produce ("team" or "player").
        entity_id: Subject entity ID (team_id or player_id).
        opp_entity_id: Opposing entity ID.
        player_team_id: Subject player's team ID (player result set only).
        on_court_intervals: Court-time intervals (player result set only).

    Returns:
        Dict of field_name -> value.
    """
    partitions = _build_partitions(
        events, result_set, entity_id, opp_entity_id,
        player_team_id, on_court_intervals,
    )

    result: Dict[str, Any] = {}

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
# ============================================================================


def _build_partitions(
    events: List[PBPEvent],
    result_set: str,
    entity_id: str,
    opp_entity_id: Optional[str],
    player_team_id: Optional[str],
    on_court_intervals: Optional[List[Tuple[int, int]]],
) -> Dict[str, List[PBPEvent]]:
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
    partitions: Dict[str, List[PBPEvent]],
) -> List[PBPEvent]:
    """Route to the correct event list based on scope."""
    return partitions.get(scope, [])


# ============================================================================
# COMPUTATION HELPERS
# ============================================================================


def _evaluate_derived(
    field_def: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[float]:
    """Evaluate a derived field formula using the safe math evaluator."""
    formula = field_def["formula"]
    fields = field_def["fields"]
    variables: Dict[str, float] = {}
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
    except Exception:
        logger.debug(
            "Derived formula failed: %s with %s", formula, variables
        )
        return None


def _is_on_court(
    event: PBPEvent,
    on_court_intervals: Optional[List[Tuple[int, int]]] = None,
) -> bool:
    """Check if an event falls within any on-court interval."""
    if on_court_intervals is None:
        return True
    return any(
        start <= event["secs"] <= end
        for start, end in on_court_intervals
    )


def _sum_points(team_events: List[PBPEvent]) -> int:
    """Sum points from a list of events."""
    pts = 0
    for e in team_events:
        ev = e["event"]
        if ev == "fg2_make":
            pts += 2
        elif ev == "fg3_make":
            pts += 3
        elif ev == "ft1_make":
            pts += 1
        elif ev == "ft2_make":
            pts += 2
        elif ev == "ft3_make":
            pts += 3
    return pts


# ============================================================================
# SPECIAL HANDLERS
# ============================================================================


def _handle_special(
    handler: str,
    all_events: List[PBPEvent],
    partitions: Dict[str, List[PBPEvent]],
    entity_id: str,
    opp_entity_id: Optional[str],
    player_team_id: Optional[str],
    on_court_intervals: Optional[List[Tuple[int, int]]],
    result: Dict[str, Any],
) -> Any:
    """Dispatch a special field handler by name."""

    # -- Team handlers --
    if handler == "team_secs":
        team_evts = partitions.get("team", [])
        if team_evts:
            return max(e["secs"] for e in team_evts)
        return None

    if handler == "team_o_poss_secs":
        return _calc_possession_secs(all_events, entity_id)

    # -- Player handlers --
    if handler == "player_win":
        team_pts = result.get("points")
        if team_pts is None:
            return None
        opp_evts = partitions.get("opp_player", [])
        opp_pts = _sum_points(opp_evts)
        return team_pts > opp_pts

    if handler == "player_secs":
        return _calc_player_secs(all_events, entity_id)

    if handler == "player_o_poss_secs":
        if player_team_id:
            return _player_possession_secs(
                all_events, player_team_id, entity_id, on_court_intervals)
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
# POSSESSION CALCULATIONS
# ============================================================================


def _calc_possession_secs(
    events: List[PBPEvent],
    team_id: str,
) -> Optional[int]:
    """Sum seconds between poss_start/poss_end pairs for a team."""
    starts = [
        e for e in events
        if e["event"] == "poss_start" and e["team_id"] == team_id
    ]
    if not starts:
        return None
    total = 0
    for s in starts:
        matching_end = next(
            (
                e for e in events
                if e["event"] == "poss_end"
                and e["team_id"] == team_id
                and e["secs"] >= s["secs"]
            ),
            None,
        )
        if matching_end:
            total += matching_end["secs"] - s["secs"]
    return total


def _player_possession_windows(
    events: List[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: Optional[List[Tuple[int, int]]],
) -> Tuple[int, int]:
    """Count possession windows and total secs where a player qualifies.

    A player qualifies for a possession window if:
    1. They were on court during any part of the window, AND
    2. A POSSESSION_EVENT occurred during their court time within that
       window (proving they were actively involved).

    Returns (count, total_secs).
    """
    if on_court_intervals is None:
        return 0, 0

    starts = [
        e for e in events
        if e["event"] == "poss_start" and e["team_id"] == team_id
    ]
    if not starts:
        return 0, 0

    count = 0
    total_secs = 0
    for s in starts:
        matching_end = next(
            (
                e for e in events
                if e["event"] == "poss_end"
                and e["team_id"] == team_id
                and e["secs"] >= s["secs"]
            ),
            None,
        )
        if matching_end is None:
            continue

        w_start = s["secs"]
        w_end = matching_end["secs"]

        # Check each court interval for overlap with this window.
        for oc_start, oc_end in on_court_intervals:
            overlap_start = max(w_start, oc_start)
            overlap_end = min(w_end, oc_end)
            if overlap_start >= overlap_end:
                continue

            # Any POSSESSION_EVENT by this team in the overlap?
            has_event = any(
                e["event"] in POSSESSION_EVENTS
                and e["team_id"] == team_id
                and overlap_start <= e["secs"] < overlap_end
                for e in events
            )
            if has_event:
                count += 1
                total_secs += w_end - w_start
                break  # count this window once

    return count, total_secs


def _player_possession_count(
    events: List[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: Optional[List[Tuple[int, int]]],
) -> Optional[int]:
    """Count qualified possession windows for a player."""
    count, _ = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    return count if count > 0 else None


def _player_possession_secs(
    events: List[PBPEvent],
    team_id: str,
    player_id: str,
    on_court_intervals: Optional[List[Tuple[int, int]]],
) -> Optional[int]:
    """Sum full possession secs for qualified windows for a player."""
    count, total = _player_possession_windows(
        events, team_id, player_id, on_court_intervals)
    return total if count > 0 else None


def _calc_player_secs(
    events: List[PBPEvent],
    player_id: str,
) -> Optional[int]:
    """Sum seconds between player_in and player_out events."""
    ins = [
        e for e in events
        if e["event"] == "player_in" and e["player_id"] == player_id
    ]
    outs = [
        e for e in events
        if e["event"] == "player_out" and e["player_id"] == player_id
    ]
    if not ins and not outs:
        return None
    total = 0
    for inp in ins:
        matching_out = next(
            (o for o in outs if o["secs"] >= inp["secs"]),
            None,
        )
        if matching_out:
            total += matching_out["secs"] - inp["secs"]
    return total


# ============================================================================
# PBP EVENT DERIVATION (Phase 2 + 3)
# ============================================================================


def derive_game_context_events(
    events: List[PBPEvent],
    home_team_id: str,
    away_team_id: str,
    lineup_size: int = 5,
) -> List[PBPEvent]:
    """Derive possession, substitution, and lineup events from raw events.

    This is the Phase 2/3 entry point that adds derived events to the
    raw event list before accumulation.

    Derives:
        - player_in / player_out from substitution events
        - player_in at period start / player_out at period end (inferred)
        - poss_start / poss_end from scoring/turnover/rebound events
        - poss_ending_ft_trip from free throw sequences

    Args:
        events: Normalized PBPEvent rows (must be sorted by secs).
        home_team_id: External ID of the home team.
        away_team_id: External ID of the away team.
        lineup_size: Number of players on court per team (from leagues.py).

    Returns:
        New list with derived events appended (original list is not mutated).
    """
    result = list(events)
    _reset_derived_id(result)
    result = _derive_substitution_events(result)
    result = _derive_lineup_events(result, lineup_size)
    result = _derive_possession_events(result, home_team_id, away_team_id)
    result = _renumber_event_ids(result)
    return result


# ============================================================================
# SHARED DERIVATION HELPER
# ============================================================================

_derived_id_counter = 0


def _mk_derived(
    events: List[PBPEvent],
    event_type: str,
    secs: int,
    team_id: str,
    player_id: str = "",
) -> PBPEvent:
    """Build a derived PBPEvent with a unique event_id.

    Uses a module-level counter seeded from max(event_id) + 1 on first
    call within a derivation pass.  Call ``_reset_derived_id`` between
    games to avoid unbounded growth.
    """
    global _derived_id_counter
    ev: PBPEvent = {
        "identity": events[0]["identity"],
        "game_id": events[0]["game_id"],
        "secs": secs,
        "event_id": _derived_id_counter,
        "team_id": team_id,
        "player_id": player_id,
        "event": event_type,
    }
    _derived_id_counter += 1
    return ev


def _reset_derived_id(events: List[PBPEvent]) -> None:
    """Seed the derived event_id counter from the given event list."""
    global _derived_id_counter
    _derived_id_counter = max(e["event_id"] for e in events) + 1 if events else 1


# ============================================================================
# PHASE 2: PLAYER IN/OUT INFERENCE
# ============================================================================


def _derive_substitution_events(
    events: List[PBPEvent],
) -> List[PBPEvent]:
    """Convert raw substitution events into standard player_in/player_out.

    Source normalizers may emit non-standard substitution event types
    (e.g. "substitution_in").  This function renames those events to
    the standard player_in / player_out format.
    """
    result = []
    for event in events:
        if event["event"] == "substitution_in":
            result.append({**event, "event": "player_in"})
        elif event["event"] == "substitution_out":
            result.append({**event, "event": "player_out"})
        else:
            result.append(event)
    return result


def _derive_lineup_events(
    events: List[PBPEvent],
    lineup_size: int,
) -> List[PBPEvent]:
    """Derive player_in at period start and player_out at period end.

    Tracks on-court players per team via explicit substitution events.
    When a player appears in any non-substitution event for their team
    without having been formally subbed in during the period, they are
    inferred to have started the period -- a ``player_in`` is emitted
    retroactively at the period_start secs.

    At period_end, every player currently on court gets a ``player_out``.
    """
    if not events:
        return events

    result = list(events)
    derived: List[PBPEvent] = []

    on_court: Dict[str, set[str]] = {}
    period_start_secs: Optional[int] = None
    in_period = False

    for event in result:
        evt = event["event"]
        team = event["team_id"]
        player = event["player_id"]
        secs = event["secs"]

        if evt == "period_start":
            period_start_secs = secs
            in_period = True
            on_court = {}

        elif evt == "period_end":
            if in_period:
                for t, players in on_court.items():
                    if len(players) != lineup_size:
                        logger.debug(
                            "Lineup size mismatch at period end secs=%d: "
                            "team=%s expected=%d actual=%d players=%s",
                            secs, t, lineup_size, len(players), sorted(players))
                    for pid in players:
                        derived.append(
                            _mk_derived(result, "player_out", secs, t, pid))
            in_period = False

        elif evt == "player_in":
            if team and player and in_period:
                on_court.setdefault(team, set()).add(player)

        elif evt == "player_out":
            if team and player and in_period:
                on_court.get(team, set()).discard(player)

        elif in_period and team and player:
            # Non-sub event with a player: if they aren't already on
            # court, they must have started the period.
            court = on_court.setdefault(team, set())
            if player not in court:
                court.add(player)
                derived.append(
                    _mk_derived(result, "player_in", period_start_secs, team, player))

    result.extend(derived)
    result.sort(key=lambda e: (e["secs"], e["event_id"]))
    return result


# ============================================================================
# PHASE 3: POSSESSION EVENT DERIVATION
# ============================================================================


def _derive_possession_events(
    events: List[PBPEvent],
    home_team_id: str,
    away_team_id: str,
) -> List[PBPEvent]:
    """Derive poss_start, poss_end, and poss_ending_ft_trip events.

    Standard possession rules:
    - Made FG: scoring team's possession ends, other team gets ball.
    - Defensive rebound: previous team's possession ends, rebounding
      team starts a new possession.
    - Turnover: turnover team's possession ends, other team gets ball.
    - Jump ball win: winning team starts a new possession.
    - Shooting foul: emits poss_ending_ft_trip at the foul timestamp.
    """
    result = list(events)
    derived: List[PBPEvent] = []

    if not events:
        return result

    def _opp(team_id: str) -> str:
        return away_team_id if team_id == home_team_id else home_team_id

    n = len(events)
    current_poss: str = ""

    for i, event in enumerate(events):
        ev = event["event"]
        team = event["team_id"]
        player = event["player_id"]
        secs = event["secs"]

        # --- Period boundaries ---

        if ev == "period_start":
            # Infer possession from the first definitive team event
            # after period_start.
            for j in range(i + 1, n):
                nx = events[j]
                if nx["team_id"] and nx["event"] in POSSESSION_EVENTS:
                    derived.append(_mk_derived(
                        result, "poss_start", secs, nx["team_id"]))
                    current_poss = nx["team_id"]
                    break

        elif ev == "period_end":
            if current_poss:
                derived.append(_mk_derived(
                    result, "poss_end", secs, current_poss))
                current_poss = ""

        # --- Made FG -> possession changes (unless and-one follows) ---

        elif ev in FG_MAKE_EVENTS:
            # And-one check: does a foul + FT by this team follow at the
            # same secs?  If so, the FG + bonus FT is one possession.
            has_and_one = False
            for j in range(i + 1, n):
                nx = events[j]
                if nx["secs"] != secs:
                    break
                if nx["event"] == "foul":
                    # Look ahead from the foul for FTs by this team.
                    for k in range(j + 1, n):
                        fk = events[k]
                        if fk["secs"] != secs:
                            break
                        if fk["event"] in ("ft1_make", "ft1_miss") and fk["team_id"] == team:
                            has_and_one = True
                            break
                    if has_and_one:
                        break
            if not has_and_one:
                derived.append(_mk_derived(result, "poss_end", secs, team))
                derived.append(_mk_derived(result, "poss_start", secs, _opp(team)))
                current_poss = _opp(team)

        # --- Defensive rebound -> possession changes ---

        elif ev == "d_reb":
            opp = _opp(team)
            derived.append(_mk_derived(result, "poss_end", secs, opp))
            derived.append(_mk_derived(result, "poss_start", secs, team))
            current_poss = team

        # --- Turnover -> possession changes ---

        elif ev == "turnover":
            derived.append(_mk_derived(result, "poss_end", secs, team))
            derived.append(_mk_derived(result, "poss_start", secs, _opp(team)))
            current_poss = _opp(team)

        # --- Made FT: last FT of trip followed by other team? ---

        elif ev == "ft1_make":
            # Is this the last FT of the trip?
            if i + 1 < n and events[i + 1]["event"] in ("ft1_make", "ft1_miss"):
                continue
            # Last FT of trip: scan for the next definitive possession
            # event.  Skip fouls and other non-possession events.
            for j in range(i + 1, n):
                nx = events[j]
                if nx["event"] in ("ft1_make", "ft1_miss"):
                    continue
                if nx["event"] not in POSSESSION_EVENTS:
                    continue
                if not nx["team_id"]:
                    continue
                if nx["team_id"] != team:
                    # Other team has the next definitive event.
                    derived.append(_mk_derived(
                        result, "poss_end", secs, team))
                    derived.append(_mk_derived(
                        result, "poss_start", secs, nx["team_id"]))
                    current_poss = nx["team_id"]
                # If same team has the next event, possession continued
                # (e.g. o_reb after missed FT) -- no change needed.
                break

        # --- Foul leading to FTs -> poss_ending_ft_trip ---

        elif ev == "foul":
            ft_idx = -1
            for j in range(i + 1, n):
                nx = events[j]
                if nx["secs"] != secs:
                    break
                if nx["event"] in ("ft1_make", "ft1_miss"):
                    ft_idx = j
                    break
            if ft_idx < 0:
                continue

            ft_event = events[ft_idx]
            ft_secs = ft_event["secs"]
            ft_team = ft_event["team_id"]
            ft_shooter = ft_event["player_id"]

            # Find the last FT at this timestamp.
            ft_end = ft_idx
            for j in range(ft_idx + 1, n):
                nx = events[j]
                if nx["secs"] != ft_secs:
                    break
                if nx["event"] in ("ft1_make", "ft1_miss"):
                    ft_end = j

            # Rule 1: and-one? Made FG by FT team at FT's secs.
            is_and_one = any(
                events[k]["event"] in FG_MAKE_EVENTS
                and events[k]["team_id"] == ft_team
                and events[k]["secs"] == ft_secs
                for k in range(max(0, ft_idx - 5), ft_idx)
            )
            if is_and_one:
                continue

            # Rule 2: FT team keeps possession after the FTs?
            same_team_after = False
            for j in range(ft_end + 1, n):
                nx = events[j]
                if nx["secs"] != ft_secs:
                    break
                if nx["event"] in ("ft1_make", "ft1_miss"):
                    continue
                if nx["team_id"] == ft_team:
                    same_team_after = True
                break
            if same_team_after:
                continue

            # Rule 3: period_end is the next event (any secs)?
            if ft_end + 1 < n and events[ft_end + 1]["event"] == "period_end":
                continue

            derived.append(_mk_derived(
                result, "poss_ending_ft_trip", ft_secs, ft_team, ft_shooter))

    result.extend(derived)
    return result
