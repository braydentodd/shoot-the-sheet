"""
Shoot the Sheet - nbastats CSV PBP Normalizer

Converts raw nbastats CSV rows into source-agnostic :class:`PBPEvent`
rows consumed by the accumulator.

Implements the detection logic defined in:
``project_tracking/pbp_tracking.md`` Section 3.1.

Pure functions -- no side effects, no I/O.
"""

import logging
from typing import Any, Dict, List, Optional

from src.definitions.pbp import PBPEvent
from src.sources.nba_data.config import (
    COL,
    MSG,
    OFFENSIVE_FOUL_ACTION_TYPES,
    PERSON_NONE,
    PERSON_TEAM,
)

logger = logging.getLogger(__name__)


# ============================================================================
# PUBLIC ENTRY POINT
# ============================================================================


def normalize_game(
    rows: List[Dict[str, Any]],
    game_id: str,
    home_team_id: str,
    away_team_id: str,
    identity: str = "nba_id",
) -> List[PBPEvent]:
    """Normalize nbastats CSV rows into standard PBPEvent rows.

    Args:
        rows: Raw CSV rows for a single game (list of dicts keyed by
              COL constants).  Must be sorted by EVENTNUM ascending.
        game_id: External game ID (e.g. ``"22400001"``).
        home_team_id: External home team ID.
        away_team_id: External away team ID.
        identity: Identity code for the event's ``identity`` field.

    Returns:
        List of PBPEvent rows sorted by (secs, event_id).
    """
    events: List[PBPEvent] = []

    # Infer period lengths from period_start events in the data.
    reg_len, ot_len = _infer_period_lengths(rows)

    # --- State for offensive/defensive rebound detection ---
    last_shot_team: Optional[str] = None

    for row in rows:
        msgtype = _to_int(row.get(COL["EVENTMSGTYPE"]))
        actiontype = _to_int(row.get(COL["EVENTMSGACTIONTYPE"]))
        period = _to_int(row.get(COL["PERIOD"]))
        pctime = _to_str(row.get(COL["PCTIMESTRING"]))
        eventnum = _to_int(row.get(COL["EVENTNUM"]))

        p1_id = _to_str(row.get(COL["PLAYER1_ID"]))
        p1_team = _to_str(row.get(COL["PLAYER1_TEAM_ID"]))
        p1_type = _to_int(row.get(COL["PERSON1TYPE"]))
        p2_id = _to_str(row.get(COL["PLAYER2_ID"]))
        p2_type = _to_int(row.get(COL["PERSON2TYPE"]))
        p3_id = _to_str(row.get(COL["PLAYER3_ID"]))
        p3_type = _to_int(row.get(COL["PERSON3TYPE"]))
        p3_team = _to_str(row.get(COL["PLAYER3_TEAM_ID"]))

        # Build combined description for text-based detection
        desc = _build_desc(row)
        is_3pt = "3PT" in desc.upper()

        secs = _pctime_to_secs(period, pctime, reg_len, ot_len)

        # Resolve player team for team-level events (PERSON1TYPE=3)
        player_team = _resolve_player_team(p1_type, p1_id, p1_team)

        # ----------------------------------------------------------------
        # Made FG (MSGTYPE 1)
        # ----------------------------------------------------------------
        if msgtype == MSG.MADE_FG:
            evt = "fg3_make" if is_3pt else "fg2_make"
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, evt))
            last_shot_team = player_team

            # Assist: PERSON2TYPE != 0
            if p2_type != PERSON_NONE and p2_id:
                assist_evt = "fg3_assist" if is_3pt else "fg2_assist"
                # Assists are attributed to the shooter's team
                events.append(_mk(identity, game_id, secs, eventnum,
                                  player_team, p2_id, assist_evt))

        # ----------------------------------------------------------------
        # Missed FG (MSGTYPE 2)
        # ----------------------------------------------------------------
        elif msgtype == MSG.MISSED_FG:
            evt = "fg3_miss" if is_3pt else "fg2_miss"
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, evt))
            last_shot_team = player_team

            # Block: PERSON3TYPE != 0 indicates a blocker
            if p3_type != PERSON_NONE and p3_id:
                blocker_team = p3_team or _opponent(player_team,
                                                    home_team_id,
                                                    away_team_id)
                events.append(_mk(identity, game_id, secs, eventnum,
                                  blocker_team, p3_id, "block"))

        # ----------------------------------------------------------------
        # Free Throw (MSGTYPE 3)
        # ----------------------------------------------------------------
        elif msgtype == MSG.FREE_THROW:
            is_missed = "MISS" in desc.upper()
            evt = "ft1_miss" if is_missed else "ft1_make"
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, evt))
            last_shot_team = player_team

        # ----------------------------------------------------------------
        # Rebound (MSGTYPE 4)
        # ----------------------------------------------------------------
        elif msgtype == MSG.REBOUND:
            # Determine offensive vs defensive
            is_offensive = (last_shot_team is not None
                            and player_team == last_shot_team)
            evt = "o_reb" if is_offensive else "d_reb"

            # Team rebound: PLAYER1_ID is the team ID, no individual player
            reb_player_id = "" if p1_type == PERSON_TEAM else p1_id
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, reb_player_id, evt))

        # ----------------------------------------------------------------
        # Turnover (MSGTYPE 5)
        # ----------------------------------------------------------------
        elif msgtype == MSG.TURNOVER:
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, "turnover"))

            # Steal: PERSON2TYPE != 0
            if p2_type != PERSON_NONE and p2_id:
                opp_team = _opponent(player_team, home_team_id, away_team_id)
                events.append(_mk(identity, game_id, secs, eventnum,
                                  opp_team, p2_id, "steal"))

        # ----------------------------------------------------------------
        # Foul (MSGTYPE 6)
        # ----------------------------------------------------------------
        elif msgtype == MSG.FOUL:
            events.append(_mk(identity, game_id, secs, eventnum,
                              player_team, p1_id, "foul"))

            # Offensive foul draw: ACTIONTYPE IN (4, 26)
            if actiontype in OFFENSIVE_FOUL_ACTION_TYPES:
                opp_team = _opponent(player_team, home_team_id, away_team_id)
                # PERSON2_ID may be populated for later seasons
                o_foul_player = p2_id if p2_id and p2_id != "0" else ""
                events.append(_mk(identity, game_id, secs, eventnum,
                                  opp_team, o_foul_player, "o_foul_draw"))

        # ----------------------------------------------------------------
        # Substitution (MSGTYPE 8)
        # ----------------------------------------------------------------
        elif msgtype == MSG.SUBSTITUTION:
            # Description: "SUB: PLAYER2 FOR PLAYER1"
            #   => PLAYER2 enters, PLAYER1 leaves
            sub_team = player_team

            if p2_id and p2_id != "0":
                events.append(_mk(identity, game_id, secs, eventnum,
                                  sub_team, p2_id, "player_in"))
            if p1_id and p1_id != "0":
                events.append(_mk(identity, game_id, secs, eventnum,
                                  sub_team, p1_id, "player_out"))

        # ----------------------------------------------------------------
        # Jump Ball (MSGTYPE 10) -- used for period-start tip-offs
        # ----------------------------------------------------------------
        elif msgtype == MSG.JUMP_BALL:
            # PERSON3 is the player who received the tip
            # Their team wins possession
            if p3_id and p3_id != "0":
                tip_team = p3_team or _resolve_player_team(p3_type, p3_id, "")
                if tip_team:
                    events.append(_mk(identity, game_id, secs, eventnum,
                                      tip_team, "", "jump_ball_win"))

        # ----------------------------------------------------------------
        # Period start / end (MSGTYPE 12, 13)
        # ----------------------------------------------------------------
        elif msgtype == MSG.PERIOD_START:
            events.append(_mk(identity, game_id, secs, eventnum,
                              "", "", "period_start"))
        elif msgtype == MSG.PERIOD_END:
            events.append(_mk(identity, game_id, secs, eventnum,
                              "", "", "period_end"))

    # Sort by (secs, event_id) for consistent accumulation
    events.sort(key=lambda e: (e["secs"], e["event_id"]))
    # Filter team rebounds sandwiched between FT attempts (data artifacts).
    events = _filter_intra_ft_rebounds(events)
    return events


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _infer_period_lengths(rows: List[Dict[str, Any]]) -> tuple[int, int]:
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
        try:
            parts = pctime.split(":")
            secs = int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
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
    """Convert PERIOD + PCTIMESTRING to elapsed game-clock seconds.

    Period 1 starts at 0, period 2 at reg_len, etc.  PCTIMESTRING
    counts down within each period (e.g. "12:00" -> "00:00").
    """
    try:
        parts = pctimestring.split(":")
        remaining = int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 0

    if period <= 4:
        base = (period - 1) * reg_len
        elapsed_in_period = reg_len - remaining
    else:
        base = 4 * reg_len + (period - 5) * ot_len
        elapsed_in_period = ot_len - remaining

    return base + elapsed_in_period


def _filter_intra_ft_rebounds(
    events: List[PBPEvent],
) -> List[PBPEvent]:
    """Remove team offensive rebounds sandwiched between FT attempts.

    When a team rebound (player_id='') occurs between two FT events of
    the same team at the same timestamp, it is a dead-ball artifact
    (e.g. the ball awarded to the shooting team between FT attempts)
    rather than a real change of possession.
    """
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


def _resolve_player_team(
    person_type: int,
    player_id: str,
    player_team_id: str,
) -> str:
    """Resolve the team for an event.

    For team-level events (PERSON1TYPE=3), PLAYER1_ID *is* the team ID
    and PLAYER1_TEAM_ID may be empty.
    """
    if person_type == PERSON_TEAM:
        return player_id
    return player_team_id


def _build_desc(row: Dict[str, Any]) -> str:
    """Build combined description from home/neutral/visitor columns."""
    parts = [
        _to_str(row.get(COL["HOMEDESCRIPTION"])),
        _to_str(row.get(COL["NEUTRALDESCRIPTION"])),
        _to_str(row.get(COL["VISITORDESCRIPTION"])),
    ]
    return " ".join(p for p in parts if p)


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
