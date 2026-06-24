"""
Shoot the Sheet — Source-Agnostic PBP Parser

Takes a list of play-by-play events in canonical form (dicts with
``actionType``, ``personId``, ``teamId``, ``subType``, etc.) and computes
derived per-player and per-team statistics.

Every computation is a pure function registered in ``PBP_METRICS``.
Adding a new metric means writing a function + one line in the registry.

Source-specific normalizers (e.g. in ``src/etl/sources/nba_api/client.py``)
convert raw API responses into this canonical event format.  The parser
itself has zero knowledge of any particular data source.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical event type (output of a source normalizer)
# ---------------------------------------------------------------------------

PbpEvent = Dict[str, Any]

# ---------------------------------------------------------------------------
# Metric computer type
# ---------------------------------------------------------------------------

MetricFn = Callable[[List[PbpEvent]], Dict[int, Any]]

# ---------------------------------------------------------------------------
# Metric registry — add new metrics here
# ---------------------------------------------------------------------------


def _compute_possessions(events: List[PbpEvent]) -> Dict[int, int]:
    """Count possessions per team from PBP events.

    A possession ends on: made shot, defensive rebound, turnover,
    end of period.  Free throws that end a possession are included.
    """
    team_poss: Dict[int, int] = {}
    current_poss_team: int | None = None

    for e in events:
        action = e.get("actionType", "")
        team_id = e.get("teamId", 0)

        if action == "period":
            # New period starts — first possession goes to the period's team
            current_poss_team = team_id

        elif action == "Jump Ball":
            current_poss_team = team_id

        elif action in ("Made Shot",):
            if current_poss_team is not None:
                team_poss[current_poss_team] = team_poss.get(current_poss_team, 0) + 1
            # Possession changes — the other team gets the next one
            current_poss_team = None  # determined by who gets the rebound

        elif action == "Rebound":
            sub = e.get("subType", "")
            if sub and "Def" in str(sub):
                # Defensive rebound — this team now has possession
                current_poss_team = team_id

        elif action == "Turnover":
            if current_poss_team is not None:
                team_poss[current_poss_team] = team_poss.get(current_poss_team, 0) + 1
            # Other team gets possession
            current_poss_team = None

        elif action == "Free Throw":
            sub = e.get("subType", "")
            shot_result = e.get("shotResult", "")
            # Last free throw in a trip ends the possession
            if "2 of 2" in str(sub) or "3 of 3" in str(sub) or "1 of 1" in str(sub):
                if current_poss_team is not None:
                    team_poss[current_poss_team] = (
                        team_poss.get(current_poss_team, 0) + 1
                    )
                if shot_result == "Made":
                    current_poss_team = None  # other team inbounds
                else:
                    current_poss_team = None  # rebound determines

        elif action == "Timeout":
            pass  # doesn't change possession

        elif action == "Substitution":
            pass  # doesn't change possession

        elif action == "Violation":
            pass  # handled by the resulting change of possession

        elif action == "Foul":
            pass  # possession may or may not change

        elif action == "Missed Shot":
            pass  # possession determined by rebound

    return team_poss


def _compute_o_fouls_drawn(events: List[PbpEvent]) -> Dict[int, int]:
    """Count offensive fouls drawn per player."""
    drawn: Dict[int, int] = {}
    for e in events:
        if e.get("actionType") != "Foul":
            continue
        sub = e.get("subType", "")
        if "Offensive" not in str(sub):
            continue
        # The player who was fouled (drew the offensive foul) isn't directly
        # listed.  Offensive fouls are on the offense, so the defense draws them.
        # We approximate by crediting the opposing team's player on the floor.
        # For now, return empty — this needs lineup context.
    return drawn


def _compute_assist_points(events: List[PbpEvent]) -> Dict[int, int]:
    """Sum points created via assists per player.

    Parses the ``description`` field for patterns like "(Russell 1 AST)".
    """
    import re

    assist_pts: Dict[int, int] = {}
    # Build a personId → playerName mapping from the events
    names: Dict[int, str] = {}
    for e in events:
        pid = e.get("personId")
        name = e.get("playerName", "")
        if pid and name and pid not in names:
            names[pid] = name.split()[0]  # first name only for matching

    for e in events:
        if e.get("actionType") not in ("Made Shot",):
            continue
        if e.get("isFieldGoal") != 1:
            continue
        desc = e.get("description", "")
        pts = e.get("shotValue", 0)
        # Find "(Name N AST)" pattern
        match = re.search(r"\((\w+)\s+\d+\s+AST\)", desc)
        if match:
            first_name = match.group(1)
            for pid, fname in names.items():
                if fname == first_name:
                    assist_pts[pid] = assist_pts.get(pid, 0) + int(pts)
                    break
    return assist_pts


PBP_METRICS: Dict[str, MetricFn] = {
    "assist_points": _compute_assist_points,
    # Team-level metrics (return teamId keys — need target-aware routing):
    # "possessions": _compute_possessions,
    # Player-level metrics (need lineup context for attribution):
    # "o_fouls_drawn": _compute_o_fouls_drawn,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_pbp(
    events: List[PbpEvent],
    metrics: List[str],
) -> Dict[int, Dict[str, Any]]:
    """Compute per-player derived stats from PBP events.

    Args:
        events: Canonical PBP events from a single game.
        metrics: Names of metrics to compute (must be keys in ``PBP_METRICS``).

    Returns:
        ``{personId: {metric_name: value, ...}, ...}``
    """
    if not events or not metrics:
        return {}

    result: Dict[int, Dict[str, Any]] = {}

    for metric_name in metrics:
        fn = PBP_METRICS.get(metric_name)
        if fn is None:
            logger.warning("Unknown PBP metric: %s", metric_name)
            continue
        try:
            metric_values = fn(events)
            for pid, value in metric_values.items():
                result.setdefault(pid, {})[metric_name] = value
        except Exception:
            logger.exception("PBP metric %s failed", metric_name)

    return result
