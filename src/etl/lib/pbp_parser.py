"""
Shoot the Sheet — Standard PBP Parser

Source-agnostic.  Input: standard PBP events from any source's normalizer.
Output: resultSets keyed by statistical domain.

The normalizer handles all source-specific complexity (clock parsing, lineup
tracking, possession detection, multi-event decomposition).  The parser is a
pure counting + state-tracking loop.

STANDARD EVENT FORMAT
---------------------
Every event has these columns (produced by the source normalizer):

    identity       str       — source identifier (nba_id, wnba_id, etc.)
    game_id        str       — external game ID
    secs           int       — cumulative seconds since game start
    event_id       int       — serial, per event
    team_id        int|None  — team that performed the event
    player_id      int|None  — player that performed the event
    event          str       — one of the standard event types (see below)

STANDARD EVENT TYPES
--------------------
    fg2_make, fg2_miss        — 2pt field goal made/missed
    fg3_make, fg3_miss        — 3pt field goal made/missed
    ft_make, ft_miss          — free throw made/missed
    o_reb, d_reb              — offensive/defensive rebound
    fg2_assist, fg3_assist    — assist on 2pt/3pt FG
    turnover                  — turnover (includes offensive violations)
    block, steal              — block, steal
    period_start, period_end  — regulation period boundaries
    overtime_start, overtime_end — OT period boundaries
    sub_in, sub_out           — substitution (one at 0s per period start/end)
    jump_ball_win, jump_ball_lose — jump ball result
    foul_commit               — any foul committed
    foul_draw_no_ft           — foul drawn, no FTs
    foul_draw_1_ft            — foul drawn, 1 FT
    foul_draw_2_ft            — foul drawn, 2 FTs
    foul_draw_3_ft            — foul drawn, 3 FTs
    foul_draw_tov             — foul drawn, turnover (offensive foul)
    new_poss                  — new possession for team_id

RESULT SETS (statistical domains)
--------------------------------
    team       — events where team_id == my_team_id
    player     — events where player_id == my_player_id
    opp_team   — events where team_id != my_team_id
    opp_player — events where team_id != my_team_id AND I'm on the court
    on_player  — events where team_id == my_team_id AND I'm on the court
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event → stat mapping (counting stats only)
# ---------------------------------------------------------------------------
# Each event type maps to a list of stat columns it should increment.
# Events not listed here (sub_in, sub_out, period_start, etc.) are tracking
# events, not stats.
#
# Makes and misses both increment the attempt column: fg2a = fg2_make + fg2_miss.

EVENT_STAT: Dict[str, List[str]] = {
    "fg2_make": ["fg2m", "fg2a"],
    "fg2_miss": ["fg2a"],
    "fg3_make": ["fg3m", "fg3a"],
    "fg3_miss": ["fg3a"],
    "ft_make": ["ftm", "fta"],
    "ft_miss": ["fta"],
    "o_reb": ["o_rebs"],
    "d_reb": ["d_rebs"],
    "fg2_assist": ["assists"],
    "fg3_assist": ["assists"],
    "turnover": ["turnovers"],
    "block": ["blocks"],
    "steal": ["steals"],
    "foul_commit": ["fouls"],
    "foul_draw_tov": ["o_fouls_drawn"],
    "foul_draw_2_ft": ["poss_ending_ft_trips"],
    "foul_draw_3_ft": ["poss_ending_ft_trips"],
    "new_poss": ["poss"],
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse standard PBP events into domain resultSets.

    Returns::

        {"resultSets": [
            {"name": "team",       "headers": [...], "rowSet": [...]},
            {"name": "player",     "headers": [...], "rowSet": [...]},
            {"name": "opp_team",   "headers": [...], "rowSet": [...]},
            {"name": "opp_player", "headers": [...], "rowSet": [...]},
            {"name": "on",         "headers": [...], "rowSet": [...]},
        ]}
    """
    if not events:
        return {"resultSets": []}

    # State — parser tracks two teams generically (team_a, team_b).
    # Home/away designation comes from the source normalizer, not the parser.
    team_ids: List[int] = []  # first two unique team IDs encountered
    active: Dict[int, set] = {}  # team_id → {player_ids on court}
    stints: Dict[int, float] = {}  # player_id → cumulative seconds on court
    last_sub_in: Dict[int, float] = {}  # player_id → secs of last sub_in
    last_poss: Dict[int, float] = {}  # team_id → secs of last new_poss for o_poss_secs
    team_scores: Dict[int, int] = {}  # team_id → total points
    player_teams: Dict[int, int] = {}  # player_id → team_id (set on first sub_in)
    has_ot: bool = False  # True if any overtime_start event seen

    # Accumulators: {domain: {entity_id: {stat: value}}}
    acc: Dict[str, Dict[int, Dict[str, Any]]] = {
        "team": {},
        "player": {},
        "opp_team": {},
        "opp_player": {},
        "on": {},
    }

    def _ensure(domain: str, eid: int) -> Dict[str, Any]:
        if eid not in acc[domain]:
            acc[domain][eid] = {}
        return acc[domain][eid]

    def _inc(domain: str, eid: int, stat: str, delta: int | float = 1):
        s = _ensure(domain, eid)
        s[stat] = s.get(stat, 0) + delta

    def _opponent(tid: int) -> int | None:
        """Return the other team ID if we have exactly two teams."""
        if len(team_ids) == 2:
            return team_ids[1] if tid == team_ids[0] else team_ids[0]
        return None

    for e in events:
        ev = e.get("event", "")
        tid = e.get("team_id")
        pid = e.get("player_id")
        secs = e.get("secs", 0)

        # --- Track the two teams ---
        if tid and tid not in team_ids and len(team_ids) < 2:
            team_ids.append(tid)

        # --- OT detection ---
        if ev == "overtime_start":
            has_ot = True

        # --- Lineup tracking ---
        if ev == "sub_in" and pid and tid:
            active.setdefault(tid, set()).add(pid)
            last_sub_in[pid] = secs
            player_teams.setdefault(pid, tid)

        elif ev == "sub_out" and pid and tid:
            active.setdefault(tid, set()).discard(pid)
            # Close stint: accumulate seconds on court
            if pid in last_sub_in:
                stints[pid] = stints.get(pid, 0.0) + (secs - last_sub_in[pid])
                del last_sub_in[pid]

        # --- Counting stats ---
        stats = EVENT_STAT.get(ev, [])
        opp_tid = _opponent(tid) if tid else None
        for stat in stats:
            # Team domain
            if tid:
                _inc("team", tid, stat)

            # Player domain
            if pid:
                _inc("player", pid, stat)

            # opp_team: reverse perspective
            if opp_tid:
                _inc("opp_team", opp_tid, stat)

            # on_player / opp_player: stats while player is on the court
            for team_id, players in active.items():
                for apid in players:
                    if tid == team_id:
                        _inc("on", apid, stat)
                    else:
                        _inc("opp_player", apid, stat)

        # --- Point tracking (for win) ---
        if ev == "fg2_make":
            team_scores[tid] = team_scores.get(tid, 0) + 2
        elif ev == "fg3_make":
            team_scores[tid] = team_scores.get(tid, 0) + 3
        elif ev == "ft_make":
            team_scores[tid] = team_scores.get(tid, 0) + 1

        # --- Derived: assist_points ---
        if ev == "fg2_assist" and pid:
            _inc("player", pid, "assist_points", 2)
        elif ev == "fg3_assist" and pid:
            _inc("player", pid, "assist_points", 3)

        # --- Derived: poss (from new_poss) ---
        if ev == "new_poss" and tid:
            _inc("team", tid, "poss")
            if opp_tid:
                _inc("opp_team", opp_tid, "poss")
            # Player poss: count while active
            for apid in active.get(tid, set()):
                _inc("on", apid, "poss")
            for team_id, players in active.items():
                if team_id != tid:
                    for apid in players:
                        _inc("opp_player", apid, "poss")

            # Derived: o_poss_secs
            if tid in last_poss:
                duration = secs - last_poss[tid]
                if duration > 0:
                    _inc("team", tid, "o_poss_secs", duration)
                    if opp_tid:
                        _inc("opp_team", opp_tid, "o_poss_secs", duration)
            last_poss[tid] = secs

    # --- Post-processing: secs per player ---
    for pid in stints:
        _inc("player", pid, "secs", stints[pid])
    # Team secs and points: last event's secs value + accumulated scores
    ot = has_ot
    if events:
        final_secs = events[-1].get("secs", 0)
        for tid in team_ids:
            _inc("team", tid, "secs", final_secs)
            _inc("team", tid, "total_points", team_scores.get(tid, 0))

    # --- Post-processing: win ---
    if len(team_ids) == 2:
        tid_a, tid_b = team_ids
        score_a = team_scores.get(tid_a, 0)
        score_b = team_scores.get(tid_b, 0)
        if score_a > score_b:
            _inc("team", tid_a, "win", 1)
            _inc("team", tid_b, "win", 0)
        elif score_b > score_a:
            _inc("team", tid_a, "win", 0)
            _inc("team", tid_b, "win", 1)

        # Player win: same as their team
        for pid, ptid in player_teams.items():
            if ptid == tid_a:
                _inc("player", pid, "win", 1 if score_a > score_b else 0)
            elif ptid == tid_b:
                _inc("player", pid, "win", 1 if score_b > score_a else 0)

    # --- Post-processing: o_poss_secs ---
    # (computed inline during the main loop from new_poss timestamps)

    result = _build_result_sets(acc)
    result["ot"] = ot
    return result


def _build_result_sets(
    acc: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Convert accumulators to resultSets format."""
    result_sets = []

    id_fields = {
        "team": "team_id",
        "player": "player_id",
        "opp_team": "team_id",
        "opp_player": "player_id",
        "on": "player_id",
    }

    for domain in ("team", "player", "opp_team", "opp_player", "on"):
        domain_acc = acc[domain]
        if not domain_acc:
            continue

        # Collect all stat names across all entities in this domain
        all_stats: set = set()
        for stats in domain_acc.values():
            all_stats.update(stats.keys())

        id_col = id_fields[domain]
        headers = [id_col] + sorted(all_stats)

        rows = []
        for eid, stats in sorted(domain_acc.items()):
            row = [eid] + [stats.get(s) for s in sorted(all_stats)]
            rows.append(row)

        result_sets.append(
            {
                "name": domain,
                "headers": headers,
                "rowSet": rows,
            }
        )

    return {"resultSets": result_sets}
