"""
Shoot the Sheet - Play-by-Play Accumulator

Generic PBP event accumulator that transforms normalized event streams into
per-game stats for every result set domain (team, player, opp_team,
opp_player, on_player).

Input:  Normalized PBP events (identity-agnostic, produced by a source's
        normalizer, e.g. ``src.sources.nba_api.pbp_normalizer``).
Output: ``{result_set: [{"ext_team_id": ..., "fg2m": 5, ...}, ...]}``

Every stat field returned here uses its canonical (unprefixed) name --
``"fg2m"``, never ``"opp_fg2m"`` or ``"on_fg2m"``. Domain separation lives in
the dict key (team / player / opp_team / opp_player / on_player), not in the
field name. Mapping these canonical fields to concrete staging columns
(``opp_fg2m``, ``on_fg2m``, ...) is the job of the ``"pbp_data"``
dataset_mapping entries in ``src.definitions.db_columns.DB_COLUMNS`` -- the
same mechanism every other dataset uses, via
``src.lib.extract.extract_value_from_raw_dict``.

This module is source-agnostic. All source-specific normalization happens
before events reach this layer.

Not yet implemented: ``o_poss_secs`` / ``d_poss_secs`` (offensive/defensive
possession duration). These require possession-boundary duration tracking
distinct from simple event counting and have no ``dataset_mapping`` entries
yet in DB_COLUMNS; they are tracked as follow-up work.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from src.definitions.pbp_events import PBP_STAT_RULES, EventType, ResultSetType

logger = logging.getLogger(__name__)

# "poss" requires possession-boundary bookkeeping (which team currently holds
# the ball) rather than a plain per-event count, so it is handled by
# dedicated logic below and excluded from the generic count loop.
_CONTEXTUAL_STATS = frozenset({"poss"})


# ============================================================================
# EVENT CONTEXT TRACKING
# ============================================================================


class GameContext:
    """Tracks on-court players per team for on_player/opp_player filtering."""

    def __init__(self):
        self.on_court: Dict[str, set] = defaultdict(set)

    def handle_sub_in(self, team_id: str, player_id: str) -> None:
        self.on_court[team_id].add(player_id)

    def handle_sub_out(self, team_id: str, player_id: str) -> None:
        self.on_court[team_id].discard(player_id)

    def is_player_on_court(self, team_id: str, player_id: str) -> bool:
        return player_id in self.on_court.get(team_id, set())

    def get_on_court_players(self, team_id: str) -> set:
        return self.on_court.get(team_id, set()).copy()


# ============================================================================
# ACCUMULATION LOGIC
# ============================================================================


def accumulate_pbp_events(
    events: List[Dict],
    ext_game_id: str,
    ext_home_team_id: str,
    ext_away_team_id: str,
) -> Dict[ResultSetType, List[Dict]]:
    """Accumulate normalized PBP events into per-game stats for all result sets.

    Args:
        events: Normalized PBP events. Each event must have: event_type,
            pbp_ext_team_id, pbp_ext_player_id, secs.
        ext_game_id: External game ID (present in output for traceability).
        ext_home_team_id: Home team external ID.
        ext_away_team_id: Away team external ID.

    Returns:
        ``{result_set: [{"ext_team_id": ..., <canonical_field>: value, ...}, ...]}``
    """
    context = GameContext()

    team_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    player_stats: Dict[tuple, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    opp_team_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    opp_player_stats: Dict[tuple, Dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    on_player_stats: Dict[tuple, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    player_sub_in_secs: Dict[tuple, int] = {}

    for event in events:
        event_type: EventType = event["event_type"]
        team_id: Optional[str] = event.get("pbp_ext_team_id")
        player_id: Optional[str] = event.get("pbp_ext_player_id")
        secs: int = event["secs"]

        opp_team_id = None
        if team_id == ext_home_team_id:
            opp_team_id = ext_away_team_id
        elif team_id == ext_away_team_id:
            opp_team_id = ext_home_team_id

        if event_type == "sub_in" and team_id and player_id:
            context.handle_sub_in(team_id, player_id)
            player_sub_in_secs[(team_id, player_id)] = secs

        elif event_type == "sub_out" and team_id and player_id:
            context.handle_sub_out(team_id, player_id)
            key = (team_id, player_id)
            if key in player_sub_in_secs:
                player_stats[key]["secs"] += secs - player_sub_in_secs[key]
                del player_sub_in_secs[key]

        elif event_type == "new_poss" and team_id:
            team_stats[team_id]["poss"] += 1
            for on_court_player in context.get_on_court_players(team_id):
                on_player_stats[(team_id, on_court_player)]["poss"] += 1
            if opp_team_id:
                opp_team_stats[opp_team_id]["poss"] += 1
                for on_court_player in context.get_on_court_players(opp_team_id):
                    opp_player_stats[(opp_team_id, on_court_player)]["poss"] += 1

        for base_stat, rule in PBP_STAT_RULES.items():
            if base_stat in _CONTEXTUAL_STATS:
                continue
            if rule["operation"] != "count":
                continue
            if event_type not in rule["events"]:
                continue

            if "team" in rule["domains"] and team_id:
                team_stats[team_id][base_stat] += 1

            if "player" in rule["domains"] and team_id and player_id:
                player_stats[(team_id, player_id)][base_stat] += 1

            if "opp_team" in rule["domains"] and opp_team_id:
                opp_team_stats[opp_team_id][base_stat] += 1

            if (
                "opp_player" in rule["domains"]
                and team_id
                and player_id
                and opp_team_id
            ):
                for on_court_player in context.get_on_court_players(opp_team_id):
                    opp_player_stats[(opp_team_id, on_court_player)][base_stat] += 1

            if "on_player" in rule["domains"] and team_id and player_id:
                if context.is_player_on_court(team_id, player_id):
                    for on_court_player in context.get_on_court_players(team_id):
                        on_player_stats[(team_id, on_court_player)][base_stat] += 1

    return {
        "team": [
            {"ext_team_id": team_id, **stats} for team_id, stats in team_stats.items()
        ],
        "player": [
            {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
            for (team_id, player_id), stats in player_stats.items()
        ],
        "opp_team": [
            {"ext_team_id": team_id, **stats}
            for team_id, stats in opp_team_stats.items()
        ],
        "opp_player": [
            {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
            for (team_id, player_id), stats in opp_player_stats.items()
        ],
        "on_player": [
            {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
            for (team_id, player_id), stats in on_player_stats.items()
        ],
    }
