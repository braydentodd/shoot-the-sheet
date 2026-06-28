"""
Shoot the Sheet — PBP Parser  (config-driven, source-agnostic)

Reads ``pbp.py`` for accumulation rules and ``db_columns.py`` to discover
which stats to compute.  Output is converted to domain-keyed ``resultSets``
so standard ``extract_columns_from_result`` can route ``domain`` + ``field``.

One pass through events produces all stats for all five domains:
    player, team, on, opp_player, opp_team
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from src.core.definitions.db_columns import DB_COLUMNS
from src.etl.definitions.pbp import ACCUM_RULES, FT_TRIP_END_SUBTYPES, POSSESSION_END

logger = logging.getLogger(__name__)

PbpEvent = Dict[str, Any]

# ---------------------------------------------------------------------------
# Stat discovery — driven by db_columns.py
# ---------------------------------------------------------------------------

_DOMAIN_RESULT_SET = {
    "player": "player",
    "team": "team",
    "on": "on",
    "opp_player": "opp_player",
    "opp_team": "opp_team",
}


def _discover_pbp_stats() -> Dict[str, Set[str]]:
    """Discover which stats to compute from ``db_columns.py`` pbp_stats entries."""
    domains: Dict[str, Set[str]] = {d: set() for d in _DOMAIN_RESULT_SET}

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
                        field = ds_cfg.get("field")
                        domain = ds_cfg.get("domain")
                        if not field or not domain:
                            continue
                        if domain in domains:
                            domains[domain].add(field)
    return domains


_PBP_STATS: Dict[str, Set[str]] = _discover_pbp_stats()


# ---------------------------------------------------------------------------
# Value resolver
# ---------------------------------------------------------------------------


def _resolve_value(token: Any, event: PbpEvent) -> int:
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


def _parse_clock(clock_str: str) -> float:
    import re

    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + float(m.group(2))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_pbp(events: List[PbpEvent]) -> Dict[str, Any]:
    """Parse canonical PBP events into per-player, per-team, and segment stats.

    Also returns domain-keyed ``resultSets`` for standard extraction.
    """
    if not events:
        return _empty_result()

    players: Dict[int, Dict[str, Any]] = {}
    teams: Dict[int, Dict[str, Any]] = {}
    segments: List[Dict[str, Any]] = []

    active: Dict[int, set] = {}
    home_team_id: int | None = None
    away_team_id: int | None = None

    current_poss_team: int | None = None
    prev_clock: float = 0.0
    game_started: bool = False

    seg_start_clock: float = 0.0
    seg_stats: Dict[int, dict] = {}

    def _player(pid: int) -> Dict[str, Any]:
        if pid not in players:
            players[pid] = {}
        return players[pid]

    def _team(tid: int) -> Dict[str, Any]:
        if tid not in teams:
            teams[tid] = {}
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
                }
            )
        seg_stats.clear()
        seg_start_clock = clock_sec

    def _accum(target: str, stat: str, value: int, tid, pid, aid):
        if target == "player" and pid:
            _player(pid)[stat] = _player(pid).get(stat, 0) + value
        elif target == "assister" and aid:
            _player(aid)[stat] = _player(aid).get(stat, 0) + value
        elif target == "team" and tid:
            _team(tid)[stat] = _team(tid).get(stat, 0) + value
        elif target == "on_court" and tid:
            for p in active.get(tid, set()):
                key = f"on_{stat}"
                _player(p)[key] = _player(p).get(key, 0) + value
        elif target == "defending_team":
            opp = next((t for t in active if t != tid), None)
            if opp:
                _team(opp)[stat] = _team(opp).get(stat, 0) + value
        elif target == "defending_on_court":
            opp = next((t for t in active if t != tid), None)
            if opp:
                for p in active.get(opp, set()):
                    key = f"opp_{stat}"
                    _player(p)[key] = _player(p).get(key, 0) + value

    for event in events:
        action = event.get("action_type", "")
        tid = event.get("team_id")
        pid = event.get("player_id")
        aid = event.get("assist_player_id")
        clock_str = event.get("clock", "PT00M00.00S")
        clock_sec = _parse_clock(clock_str)

        if home_team_id is None and tid:
            home_team_id = tid
        if away_team_id is None and tid and tid != home_team_id:
            away_team_id = tid

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

        if prev_clock > clock_sec:
            elapsed = prev_clock - clock_sec
            for pids in active.values():
                for p in pids:
                    _player(p)["SECS"] = _player(p).get("SECS", 0.0) + elapsed
            if current_poss_team is not None:
                _team(current_poss_team)["O_POSS_SECS"] = (
                    _team(current_poss_team).get("O_POSS_SECS", 0.0) + elapsed
                )
            opp = next((t for t in active if t != current_poss_team), None)
            if opp is not None:
                # d_poss_secs handled by domain mirroring (opp_team reads O_POSS_SECS)
                pass
        prev_clock = clock_sec

        # Possession tracking
        if action == "JumpBall":
            current_poss_team = tid
        elif action == "MadeShot":
            if current_poss_team is not None and current_poss_team == tid:
                _team(tid)["POSS"] = _team(tid).get("POSS", 0) + 1
            current_poss_team = None
        elif action == "Rebound" and event.get("rebound_type") == "defensive":
            current_poss_team = tid
        elif action == "Turnover":
            if current_poss_team is not None and current_poss_team == tid:
                _team(tid)["POSS"] = _team(tid).get("POSS", 0) + 1
            current_poss_team = None
        elif action == "FreeThrow":
            sub = event.get("sub_type", "")
            if sub in FT_TRIP_END_SUBTYPES:
                if current_poss_team is not None:
                    _team(current_poss_team)["POSS"] = (
                        _team(current_poss_team).get("POSS", 0) + 1
                    )
                    _team(current_poss_team)["PEFTT"] = (
                        _team(current_poss_team).get("PEFTT", 0) + 1
                    )
                current_poss_team = None

        # Apply ACCUM_RULES
        for rule in ACCUM_RULES.get(action, []):
            value = _resolve_value(rule["value"], event)
            if value:
                _accum(rule["target"], rule["stat"], value, tid, pid, aid)

        # Substitution
        if action == "Substitution":
            sub_in = event.get("substitution_in")
            sub_out = event.get("substitution_out")
            if sub_in and sub_out and tid:
                _end_segment(clock_sec)
                active.setdefault(tid, set()).discard(sub_out)
                active.setdefault(tid, set()).add(sub_in)
                seg_start_clock = clock_sec

    if events:
        last_clock = _parse_clock(events[-1].get("clock", "PT00M00.00S"))
        _end_segment(last_clock)

    # Opponent auto-mirror (driven by db_columns)
    if home_team_id and away_team_id:
        ht = teams.get(home_team_id, {})
        at = teams.get(away_team_id, {})
        for field in _PBP_STATS.get("opp_team", set()):
            if home_team_id in teams:
                teams[home_team_id][f"opp_{field}"] = at.get(field, 0)
            if away_team_id in teams:
                teams[away_team_id][f"opp_{field}"] = ht.get(field, 0)

    return _build_result(players, teams, segments, home_team_id, away_team_id)


def _empty_result() -> Dict[str, Any]:
    return {
        "resultSets": [],
        "segments": [],
        "home_team_id": None,
        "away_team_id": None,
    }


def _build_result(
    players: Dict[int, Dict[str, Any]],
    teams: Dict[int, Dict[str, Any]],
    segments: List[Dict[str, Any]],
    home_team_id: int | None,
    away_team_id: int | None,
) -> Dict[str, Any]:
    """Convert parsed stats to domain-keyed resultSets."""
    result_sets = []

    # player domain
    p_rows, p_headers = [], []
    for pid, stats in players.items():
        base = {k: v for k, v in stats.items() if not k.startswith(("on_", "opp_"))}
        row = {"player_id": pid, **base}
        if not p_headers:
            p_headers = list(row.keys())
        p_rows.append([row.get(h) for h in p_headers])
    if p_rows:
        result_sets.append({"name": "player", "headers": p_headers, "rowSet": p_rows})

    # team domain
    t_rows, t_headers = [], []
    for tid, stats in teams.items():
        base = {k: v for k, v in stats.items() if not k.startswith("opp_")}
        row = {"team_id": tid, **base}
        if not t_headers:
            t_headers = list(row.keys())
        t_rows.append([row.get(h) for h in t_headers])
    if t_rows:
        result_sets.append({"name": "team", "headers": t_headers, "rowSet": t_rows})

    # opp_team domain
    ot_rows, ot_headers = [], []
    for tid, stats in teams.items():
        opp = {k: v for k, v in stats.items() if k.startswith("opp_")}
        if not opp:
            continue
        row = {"team_id": tid, **opp}
        if not ot_headers:
            ot_headers = list(row.keys())
        ot_rows.append([row.get(h) for h in ot_headers])
    if ot_rows:
        result_sets.append(
            {"name": "opp_team", "headers": ot_headers, "rowSet": ot_rows}
        )

    # on domain
    on_rows, on_headers = [], []
    for pid, stats in players.items():
        on_stats = {k: v for k, v in stats.items() if k.startswith("on_")}
        if not on_stats:
            continue
        row = {"player_id": pid, **on_stats}
        if not on_headers:
            on_headers = list(row.keys())
        on_rows.append([row.get(h) for h in on_headers])
    if on_rows:
        result_sets.append({"name": "on", "headers": on_headers, "rowSet": on_rows})

    # opp_player domain
    op_rows, op_headers = [], []
    for pid, stats in players.items():
        opp = {k: v for k, v in stats.items() if k.startswith("opp_")}
        if not opp:
            continue
        row = {"player_id": pid, **opp}
        if not op_headers:
            op_headers = list(row.keys())
        op_rows.append([row.get(h) for h in op_headers])
    if op_rows:
        result_sets.append(
            {"name": "opp_player", "headers": op_headers, "rowSet": op_rows}
        )

    return {
        "resultSets": result_sets,
        "segments": segments,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
    }
