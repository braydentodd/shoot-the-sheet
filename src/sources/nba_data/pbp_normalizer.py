"""
Shoot the Sheet - nbastats CSV PBP Normalizer

Converts raw nbastats CSV rows into source-agnostic :class:`PBPEvent`
rows consumed by the accumulator.

Event classification is driven by ``core.pbp_events`` via the
:class:`~src.lib.pbp_classifier.EventClassifier`.  The classifier
replaces the previous hardcoded ``if msgtype == ...`` chain.

Pure functions -- no side effects, no I/O.
"""

import logging
from typing import Any

from src.definitions.pbp import PBPEvent
from src.lib.entity_resolver import EntityResolver
from src.lib.pbp_classifier import EventClassifier, UnclassifiedEventError
from src.sources.nba_data.config import (
    COL,
    MSG,
    OFFENSIVE_FOUL_ACTION_TYPES,
    PERSON_NONE,
)

logger = logging.getLogger(__name__)


# ============================================================================
# PUBLIC ENTRY POINT
# ============================================================================


def normalize_game(
    rows: list[dict[str, Any]],
    game_id: str,
    home_team_id: str,
    away_team_id: str,
    entity_resolver: EntityResolver,
    classifier: EventClassifier,
    identity: str = "nba_id",
) -> list[PBPEvent]:
    """Normalize nbastats CSV rows into standard PBPEvent rows.

    Args:
        rows: Raw CSV rows for a single game (list of dicts keyed by
              COL constants).  Must be sorted by EVENTNUM ascending.
        game_id: External game ID (e.g. ``"22400001"``).
        home_team_id: External home team ID.
        away_team_id: External away team ID.
        entity_resolver: Callable for staging-table entity lookup.
        classifier: EventClassifier loaded from ``core.pbp_events``.
        identity: Identity code for the event's ``identity`` field.

    Returns:
        List of PBPEvent rows sorted by (secs, event_id).
    """
    events: list[PBPEvent] = []

    reg_len, ot_len = _infer_period_lengths(rows)

    last_shot_team: str | None = None

    for row in rows:
        eventnum = _to_int(row.get(COL["EVENTNUM"]))
        period = _to_int(row.get(COL["PERIOD"]))
        pctime = _to_str(row.get(COL["PCTIMESTRING"]))

        p1_id = _to_str(row.get(COL["PLAYER1_ID"]))
        p1_type = _to_int(row.get(COL["PERSON1TYPE"]))
        p2_id = _to_str(row.get(COL["PLAYER2_ID"]))
        p2_type = _to_int(row.get(COL["PERSON2TYPE"]))
        p3_id = _to_str(row.get(COL["PLAYER3_ID"]))
        p3_type = _to_int(row.get(COL["PERSON3TYPE"]))
        p3_team = _to_str(row.get(COL["PLAYER3_TEAM_ID"]))

        actiontype = _to_int(row.get(COL["EVENTMSGACTIONTYPE"]))

        secs = _pctime_to_secs(period, pctime, reg_len, ot_len)

        # Classify first -- system events don't need entity resolution.
        try:
            classification = classifier.classify(row)
        except UnclassifiedEventError:
            continue

        if classification.is_ignore:
            continue

        handling = classification.handling

        # Resolve entity via staging lookup (skip for system events).
        if handling in ("period_start", "period_end"):
            entity_type = "system"
            resolved_team = ""
            player_team = ""
        else:
            entity_type, resolved_team = entity_resolver(p1_id)
            if entity_type is None or resolved_team is None:
                logger.debug(
                    "Unknown entity %r (PERSON1TYPE=%s) in game %s event %s",
                    p1_id, p1_type, game_id, eventnum,
                )
                continue
            player_team = resolved_team

        # ── Context-dependent pseudo-types ────────────────────────────

        if handling == "rebound":
            is_offensive = (last_shot_team is not None
                            and player_team == last_shot_team)
            evt = "o_reb" if is_offensive else "d_reb"
            reb_player_id = "" if entity_type == "team" else p1_id
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, reb_player_id, evt))

        elif handling == "substitution":
            if p2_id and p2_id != "0":
                events.append(_mk(identity, game_id, secs, eventnum,
                                  player_team, p2_id, "player_in"))
            if p1_id and p1_id != "0":
                events.append(_mk(identity, game_id, secs, eventnum,
                                  player_team, p1_id, "player_out"))

        # ── Direct event types ────────────────────────────────────────

        elif handling == "turnover":
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, "turnover"))
            if p2_type != PERSON_NONE and p2_id:
                opp_team = _opponent(player_team, home_team_id, away_team_id)
                events.append(_mk(identity, game_id, secs, eventnum,
                                  opp_team, p2_id, "steal"))

        elif handling == "foul":
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, "foul"))
            if actiontype in OFFENSIVE_FOUL_ACTION_TYPES:
                opp_team = _opponent(player_team, home_team_id, away_team_id)
                o_foul_player = p2_id if p2_id and p2_id != "0" else ""
                events.append(_mk(identity, game_id, secs, eventnum,
                                  opp_team, o_foul_player, "o_foul_draw"))

        elif handling == "jump_ball_win":
            if p3_id and p3_id != "0":
                _, tip_team = entity_resolver(p3_id)
                tip_team = p3_team or tip_team
                if tip_team:
                    events.append(_mk(identity, game_id, secs, eventnum,
                                      tip_team, "", "jump_ball_win"))

        elif handling in ("period_start", "period_end"):
            events.append(_mk(identity, game_id, secs, eventnum,
                              "", "", handling))

        # ── FG/FT: emit directly, track last_shot_team, handle secondaries ──

        elif handling in ("fg2_make", "fg3_make"):
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, handling))
            last_shot_team = player_team
            if p2_type != PERSON_NONE and p2_id:
                assist_evt = "fg3_assist" if handling == "fg3_make" else "fg2_assist"
                events.append(_mk(identity, game_id, secs, eventnum,
                                  player_team, p2_id, assist_evt))

        elif handling in ("fg2_miss", "fg3_miss"):
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, handling))
            last_shot_team = player_team
            if p3_type != PERSON_NONE and p3_id:
                blocker_team = p3_team or _opponent(player_team,
                                                    home_team_id,
                                                    away_team_id)
                events.append(_mk(identity, game_id, secs, eventnum,
                                  blocker_team, p3_id, "block"))

        elif handling in ("ft1_make", "ft1_miss"):
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, handling))
            last_shot_team = player_team

        else:
            # All other direct PBPEventType values -- emit as-is
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, handling))

    events.sort(key=lambda e: (e["secs"], e["event_id"]))
    events = _filter_intra_ft_rebounds(events)
    return events


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _parse_pctime(pctimestring: str) -> int:
    """Parse a PCTIMESTRING (e.g. ``"12:00"``) into raw seconds.

    Returns 0 on parse failure.
    """
    try:
        parts = pctimestring.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 0


def _infer_period_lengths(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Infer regulation and overtime period lengths from the data.

    Reads PCTIMESTRING from period_start events (EVENTMSGTYPE=12).
    Falls back to max PCTIMESTRING seen in period 1 / first OT period.
    """
    reg_len = 0
    ot_len = 0
    for row in rows:
        msgtype = _to_int(row.get(COL["EVENTMSGTYPE"]))
        period = _to_int(row.get(COL["PERIOD"]))
        pctime = _to_str(row.get(COL["PCTIMESTRING"]))
        secs = _parse_pctime(pctime)
        if secs == 0:
            continue
        if msgtype == MSG.PERIOD_START:
            if period == 1:
                reg_len = secs
            elif period >= 5 and ot_len == 0:
                ot_len = secs
        elif period == 1 and secs > reg_len:
            reg_len = secs
        elif period >= 5 and secs > ot_len:
            ot_len = secs
    if reg_len == 0:
        reg_len = 720
    if ot_len == 0:
        ot_len = 300
    return reg_len, ot_len


def _pctime_to_secs(
    period: int, pctimestring: str, reg_len: int, ot_len: int,
) -> int:
    """Convert PERIOD + PCTIMESTRING to elapsed game-clock seconds."""
    remaining = _parse_pctime(pctimestring)

    if period <= 4:
        base = (period - 1) * reg_len
        elapsed_in_period = reg_len - remaining
    else:
        base = 4 * reg_len + (period - 5) * ot_len
        elapsed_in_period = ot_len - remaining

    return base + elapsed_in_period


def _filter_intra_ft_rebounds(
    events: list[PBPEvent],
) -> list[PBPEvent]:
    """Remove team offensive rebounds sandwiched between FT attempts."""
    n = len(events)
    keep = [True] * n
    for i in range(1, n - 1):
        e = events[i]
        if e["event"] != "o_reb" or e["player_id"] != "":
            continue
        prev_ev = events[i - 1]["event"]
        next_ev = events[i + 1]["event"]
        if (prev_ev in ("ft1_make", "ft1_miss")
                and next_ev in ("ft1_make", "ft1_miss")
                and events[i - 1]["team_id"] == e["team_id"]
                and events[i - 1]["secs"] == e["secs"]):
            keep[i] = False
    return [e for i, e in enumerate(events) if keep[i]]


def _mk(
    identity: str,
    game_id: str,
    secs: int,
    event_id: int,
    team_id: str,
    player_id: str,
    event: str,
) -> PBPEvent:
    """Build a single PBPEvent row."""
    return {
        "identity": identity,
        "game_id": game_id,
        "secs": secs,
        "event_id": event_id,
        "team_id": team_id,
        "player_id": player_id,
        "event": event,
    }


def _opponent(
    team_id: str,
    home_team_id: str,
    away_team_id: str,
) -> str:
    """Return the opposing team ID."""
    if team_id == home_team_id:
        return away_team_id
    if team_id == away_team_id:
        return home_team_id
    return ""


def _to_int(val: Any) -> int:
    """Coerce a value to int, returning 0 for empty/missing."""
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _to_str(val: Any) -> str:
    """Coerce a value to str, returning '' for None."""
    if val is None:
        return ""
    return str(val)
