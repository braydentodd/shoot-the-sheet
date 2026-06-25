"""
Shoot the Sheet — PBP Parser  (config-driven, source-agnostic)

Reads ``pbp.py`` for accumulation rules and ``db_columns.py`` to discover
which stats to compute.  Add a column to ``db_columns.py`` → parser picks
it up automatically.  Add a source → add ``SOURCE_NORMALIZERS`` entry.

One pass through events produces:
    {home_team_id, away_team_id, players: {id: {stat: val}}, teams: {id: {stat: val}}, segments: [...]}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from src.core.definitions.db_columns import DB_COLUMNS
from src.etl.definitions.pbp import (
    ACCUM_RULES,
    DERIVED,
    FT_TRIP_END_SUBTYPES,
    OPPONENT_MIRROR_EXCLUDE,
    POSSESSION_END,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PbpEvent = Dict[str, Any]


# ---------------------------------------------------------------------------
# Stat discovery — driven by db_columns.py
# ---------------------------------------------------------------------------


def _discover_pbp_stats() -> Dict[str, Set[str]]:
    """Find all stats that any column references via ``pbp_stats`` pipeline."""
    player: Set[str] = set()
    team: Set[str] = set()
    on_court: Set[str] = set()

    for col_name, col_meta in DB_COLUMNS.items():
        dm = col_meta.get("dataset_mapping") or {}
        for league_sources in dm.values():
            if not isinstance(league_sources, dict):
                continue
            for identity_sources in league_sources.values():
                if not isinstance(identity_sources, dict):
                    continue
                for target, datasets in identity_sources.items():
                    for ds_name, ds_cfg in datasets.items():
                        if ds_name != "pbp_stats":
                            continue
                        field = ds_cfg.get("pipeline", {}).get("field")
                        if not field:
                            continue
                        if target in ("player_games",):
                            player.add(field)
                        elif target in ("team_games",):
                            team.add(field)
                        # on_* stats come from on_court accumulation in player_games
                        if field.startswith("on_"):
                            on_court.add(field)

    return {"PLAYER": player, "TEAM": team, "ON_COURT": on_court}


# Cached at module load — columns don't change at runtime.
_PBP_STATS: Dict[str, Set[str]] = _discover_pbp_stats()


# ---------------------------------------------------------------------------
# Value resolver — converts special tokens to integers
# ---------------------------------------------------------------------------


def _resolve_value(token: Any, event: PbpEvent) -> int:
    """Convert a rule's ``value`` to an integer using the event context."""
    if isinstance(token, int):
        return token
    if token == "shot_value_2":
        return 1 if event.get("shot_value") == 2 else 0
    if token == "shot_value_3":
        return 1 if event.get("shot_value") == 3 else 0
    if token == "shot_value":
        return int(event.get("shot_value") or 0)
    if token == "shot_made_1":
        return 1 if event.get("shot_made") else 0
    if token == "rebound_offensive":
        return 1 if event.get("rebound_type") == "offensive" else 0
    if token == "rebound_defensive":
        return 1 if event.get("rebound_type") == "defensive" else 0
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_clock(clock_str: str) -> float:
    import re

    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + float(m.group(2))


def _init_player_stats() -> Dict[str, Any]:
    return {s: 0 for s in _PBP_STATS["PLAYER"]}


def _init_team_stats() -> Dict[str, Any]:
    base = {s: 0 for s in _PBP_STATS["TEAM"]}
    # Also add opp_ variants for everything except excluded
    for s in _PBP_STATS["TEAM"]:
        if s not in OPPONENT_MIRROR_EXCLUDE:
            base[f"opp_{s}"] = 0
    return base


def _init_on_court_stats() -> Dict[str, Any]:
    return {s: 0 for s in _PBP_STATS["ON_COURT"]}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_pbp(events: List[PbpEvent]) -> Dict[str, Any]:
    """Parse canonical PBP events into complete player/team/segment stats.

    Returns::

        {
            "home_team_id": 1610612743,
            "away_team_id": 1610612747,
            "players":  {player_id: {fg2m: 5, assist_points: 10, ...}, ...},
            "teams":    {team_id:   {fg3m: 10, opp_fg3m: 8, poss: 95, ...}, ...},
            "segments": [{period, start_clock, end_clock, duration_sec,
                          home_players: [...], away_players: [...],
                          home_stats: {...}, away_stats: {...}}, ...],
        }

    Opponent stats (``opp_*``) are auto-mirrored from the other team after
    all events are processed.  No manual DERIVED entries needed.
    """
    if not events:
        return {
            "home_team_id": None,
            "away_team_id": None,
            "players": {},
            "teams": {},
            "segments": [],
        }

    # State
    players: Dict[int, Dict[str, Any]] = {}
    teams: Dict[int, Dict[str, Any]] = {}
    segments: List[Dict[str, Any]] = []

    active: Dict[int, set] = {}  # team_id → {player_ids on floor}
    home_team_id: int | None = None
    away_team_id: int | None = None

    current_poss_team: int | None = None
    prev_clock: float = 0.0
    game_started: bool = False

    seg_start_clock: float = 0.0
    seg_stats: Dict[int, dict] = {}

    def _get_or_create_player(pid: int) -> Dict[str, Any]:
        if pid not in players:
            players[pid] = _init_player_stats()
        return players[pid]

    def _get_or_create_team(tid: int) -> Dict[str, Any]:
        if tid not in teams:
            teams[tid] = _init_team_stats()
        return teams[tid]

    def _end_segment(clock_sec: float):
        nonlocal seg_start_clock
        if not active or seg_start_clock == clock_sec:
            return
        duration = seg_start_clock - clock_sec
        if duration <= 0:
            seg_start_clock = clock_sec
            return
        home_pids = sorted(active.get(home_team_id, set()))
        away_pids = sorted(active.get(away_team_id, set()))
        if len(home_pids) != 5 or len(away_pids) != 5:
            seg_start_clock = clock_sec
            return
        # Merge with previous segment if same 10 players
        if (
            segments
            and segments[-1]["home_players"] == home_pids
            and segments[-1]["away_players"] == away_pids
        ):
            segments[-1]["duration_sec"] += duration
            segments[-1]["end_clock"] = clock_sec
        else:
            segments.append(
                {
                    "period": events[0].get("period", 1),
                    "start_clock": seg_start_clock,
                    "end_clock": clock_sec,
                    "duration_sec": duration,
                    "home_players": home_pids,
                    "away_players": away_pids,
                    "home_stats": seg_stats.get(home_team_id, {}),
                    "away_stats": seg_stats.get(away_team_id, {}),
                }
            )
        seg_stats.clear()
        seg_start_clock = clock_sec

    def _apply_accum(event: PbpEvent, target: str, stat: str, value: int):
        tid = event.get("team_id")
        pid = event.get("player_id")
        aid = event.get("assist_player_id")

        if target == "player" and pid:
            _get_or_create_player(pid)[stat] = (
                _get_or_create_player(pid).get(stat, 0) + value
            )
        elif target == "assister" and aid:
            _get_or_create_player(aid)[stat] = (
                _get_or_create_player(aid).get(stat, 0) + value
            )
        elif target == "team" and tid:
            _get_or_create_team(tid)[stat] = (
                _get_or_create_team(tid).get(stat, 0) + value
            )
        elif target == "on_court" and tid:
            for p in active.get(tid, set()):
                on_key = f"on_{stat}" if not stat.startswith("on_") else stat
                if on_key in _PBP_STATS["ON_COURT"]:
                    _get_or_create_player(p)[on_key] = (
                        _get_or_create_player(p).get(on_key, 0) + value
                    )
        elif target == "defending_team":
            opp = next((t for t in active if t != tid), None)
            if opp:
                _get_or_create_team(opp)[stat] = (
                    _get_or_create_team(opp).get(stat, 0) + value
                )
        elif target == "defending_on_court":
            opp = next((t for t in active if t != tid), None)
            if opp:
                for p in active.get(opp, set()):
                    on_key = f"on_{stat}" if not stat.startswith("on_") else stat
                    if on_key in _PBP_STATS["ON_COURT"]:
                        _get_or_create_player(p)[on_key] = (
                            _get_or_create_player(p).get(on_key, 0) + value
                        )

    # --- Main event loop ---
    for event in events:
        action = event.get("action_type", "")
        tid = event.get("team_id")
        clock_str = event.get("clock", "PT00M00.00S")
        clock_sec = _parse_clock(clock_str)

        # Identify home/away from first event with a team
        if home_team_id is None and tid:
            home_team_id = tid
        if away_team_id is None and tid and tid != home_team_id:
            away_team_id = tid

        # Period boundary
        if action == "Period":
            if not game_started:
                game_started = True
                prev_clock = clock_sec
                seg_start_clock = clock_sec
                continue
            _end_segment(clock_sec)
            active.clear()
            seg_start_clock = clock_sec
            prev_clock = clock_sec
            continue

        if not game_started:
            continue

        # Time accumulation
        if prev_clock > clock_sec:
            elapsed = prev_clock - clock_sec
            for pids in active.values():
                for pid in pids:
                    p = _get_or_create_player(pid)
                    p["secs"] = p.get("secs", 0.0) + elapsed
            if current_poss_team is not None:
                tm = _get_or_create_team(current_poss_team)
                tm["o_poss_secs"] = tm.get("o_poss_secs", 0.0) + elapsed
            opp = next((t for t in active if t != current_poss_team), None)
            if opp is not None:
                tm2 = _get_or_create_team(opp)
                tm2["d_poss_secs"] = tm2.get("d_poss_secs", 0.0) + elapsed
        prev_clock = clock_sec

        # Possession tracking
        if action == "JumpBall":
            current_poss_team = tid
        elif action == "MadeShot":
            if current_poss_team is not None and current_poss_team == tid:
                tm = _get_or_create_team(tid)
                tm["poss"] = tm.get("poss", 0) + 1
            current_poss_team = None
        elif action == "Rebound" and event.get("rebound_type") == "defensive":
            current_poss_team = tid
        elif action == "Turnover":
            if current_poss_team is not None and current_poss_team == tid:
                tm = _get_or_create_team(tid)
                tm["poss"] = tm.get("poss", 0) + 1
            current_poss_team = None
        elif action == "FreeThrow":
            # Check if this is the last FT of a trip
            from src.etl.definitions.pbp import FT_TRIP_END_SUBTYPES

            sub = event.get("sub_type", "")
            if sub in FT_TRIP_END_SUBTYPES:
                if current_poss_team is not None:
                    tm = _get_or_create_team(current_poss_team)
                    tm["poss"] = tm.get("poss", 0) + 1
                    tm["poss_ending_ft_trips"] = tm.get("poss_ending_ft_trips", 0) + 1
                current_poss_team = None

        # Apply ACCUM_RULES for this action_type
        rules = ACCUM_RULES.get(action, [])
        for rule in rules:
            value = _resolve_value(rule["value"], event)
            if value:
                _apply_accum(event, rule["target"], rule["stat"], value)

        # Substitution
        if action == "Substitution":
            sub_in = event.get("substitution_in")
            sub_out = event.get("substitution_out")
            if sub_in and sub_out and tid:
                _end_segment(clock_sec)
                active.setdefault(tid, set()).discard(sub_out)
                active.setdefault(tid, set()).add(sub_in)
                seg_start_clock = clock_sec

    # Finalize last segment
    if events:
        last_clock = _parse_clock(events[-1].get("clock", "PT00M00.00S"))
        _end_segment(last_clock)

    # --- Opponent auto-mirror ---
    if home_team_id and away_team_id:
        ht = teams.get(home_team_id, {})
        at = teams.get(away_team_id, {})
        for stat in _PBP_STATS["TEAM"]:
            if stat in OPPONENT_MIRROR_EXCLUDE:
                continue
            opp_key = f"opp_{stat}"
            if opp_key in _init_team_stats():
                if home_team_id in teams:
                    teams[home_team_id][opp_key] = at.get(stat, 0)
                if away_team_id in teams:
                    teams[away_team_id][opp_key] = ht.get(stat, 0)

    return {
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "players": players,
        "teams": teams,
        "segments": segments,
    }
