"""
Shoot the Sheet - Play-by-Play Accumulator

Generic PBP event accumulator that transforms normalized event streams into
per-game stats for all result set domains (team, player, opp_team, opp_player, on_player).

Input:  List of normalized PBP events from pbp_events_staging
Output: Dict of result_sets → stats dictionaries

This module is source-agnostic. All source-specific normalization happens
before events reach this layer.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from src.definitions.pbp_events import (
    DOMAIN_PREFIXES,
    PBP_STAT_RULES,
    EventType,
    ResultSetType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# EVENT CONTEXT TRACKING
# ============================================================================


class GameContext:
    """Tracks game state for contextual event filtering.

    Maintains:
    - Current on-court players per team (for on_player/opp_player filtering)
    - Last possession change timestamp (for possession duration)
    - Possession count per team
    """

    def __init__(self):
        self.on_court: Dict[str, set] = defaultdict(set)  # team_id -> set(player_ids)
        self.last_poss_secs: Dict[
            str, int
        ] = {}  # team_id -> last possession start secs
        self.poss_count: Dict[str, int] = defaultdict(
            int
        )  # team_id -> possession count

    def handle_sub_in(self, team_id: str, player_id: str):
        """Record player substitution in."""
        self.on_court[team_id].add(player_id)

    def handle_sub_out(self, team_id: str, player_id: str):
        """Record player substitution out."""
        self.on_court[team_id].discard(player_id)

    def handle_new_poss(self, team_id: str, secs: int):
        """Record new possession start and count."""
        self.last_poss_secs[team_id] = secs
        self.poss_count[team_id] += 1

    def calc_poss_duration(self, team_id: str, current_secs: int) -> int:
        """Calculate possession duration for team."""
        if team_id in self.last_poss_secs:
            return current_secs - self.last_poss_secs[team_id]
        return 0

    def is_player_on_court(self, team_id: str, player_id: str) -> bool:
        """Check if player is currently on court."""
        return player_id in self.on_court.get(team_id, set())

    def get_on_court_players(self, team_id: str) -> set:
        """Get all players currently on court for team."""
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
    """Accumulate PBP events into per-game stats for all result sets.

    Args:
        events: List of normalized PBP events from pbp_events_staging.
                Each event must have: event_type, pbp_ext_team_id, pbp_ext_player_id, secs
        ext_game_id: External game ID for grouping
        ext_home_team_id: Home team external ID
        ext_away_team_id: Away team external ID

    Returns:
        Dict mapping result_set type to list of stat records:
        {
            "team": [{"ext_team_id": "...", "fg2m": 10, ...}, ...],
            "player": [{"ext_team_id": "...", "ext_player_id": "...", "fg2m": 5, ...}, ...],
            "opp_team": [...],
            "opp_player": [...],
            "on_player": [...],
        }
    """
    context = GameContext()

    team_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    player_stats: Dict[tuple, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    opp_team_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    opp_player_stats: Dict[tuple, Dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    on_player_stats: Dict[tuple, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    player_sub_in_times: Dict[tuple, int] = {}

    for event in events:
        event_type: EventType = event["event_type"]
        team_id: Optional[str] = event.get("pbp_ext_team_id")
        player_id: Optional[str] = event.get("pbp_ext_player_id")
        secs: int = event["secs"]

        # Determine opponent team
        opp_team_id = None
        if team_id == ext_home_team_id:
            opp_team_id = ext_away_team_id
        elif team_id == ext_away_team_id:
            opp_team_id = ext_home_team_id

        if event_type == "sub_in" and team_id and player_id:
            context.handle_sub_in(team_id, player_id)
            player_sub_in_times[(team_id, player_id)] = secs
        elif event_type == "sub_out" and team_id and player_id:
            context.handle_sub_out(team_id, player_id)
            if (team_id, player_id) in player_sub_in_times:
                sub_in_secs = player_sub_in_times[(team_id, player_id)]
                player_stats[(team_id, player_id)]["secs"] += secs - sub_in_secs
                del player_sub_in_times[(team_id, player_id)]
        elif event_type == "new_poss" and team_id:
            # Calculate possession duration for opponent team (they just lost possession)
            if opp_team_id:
                poss_duration = context.calc_poss_duration(opp_team_id, secs)
                if poss_duration > 0:
                    team_stats[opp_team_id]["o_poss_secs"] += poss_duration
                    # Accumulate to all on-court players for opponent team
                    for player_id_on_court in context.get_on_court_players(opp_team_id):
                        player_stats[(opp_team_id, player_id_on_court)][
                            "o_poss_secs"
                        ] += poss_duration
                        on_player_stats[(opp_team_id, player_id_on_court)][
                            "o_poss_secs"
                        ] += poss_duration
            context.handle_new_poss(team_id, secs)
            team_stats[team_id]["poss"] += 1
            for player_id_on_court in context.get_on_court_players(team_id):
                player_stats[(team_id, player_id_on_court)]["poss"] += 1
            if opp_team_id:
                opp_team_stats[opp_team_id]["poss"] += 1
                for opp_player_on_court in context.get_on_court_players(opp_team_id):
                    opp_player_stats[(opp_team_id, opp_player_on_court)]["poss"] += 1

        for base_stat, rule in PBP_STAT_RULES.items():
            if event_type not in rule["events"]:
                continue

            if "team" in rule["domains"] and team_id:
                stat_name = DOMAIN_PREFIXES["team"] + base_stat
                team_stats[team_id][stat_name] += 1

            if "player" in rule["domains"] and team_id and player_id:
                stat_name = DOMAIN_PREFIXES["player"] + base_stat
                player_stats[(team_id, player_id)][stat_name] += 1

            if "opp_team" in rule["domains"] and opp_team_id:
                stat_name = DOMAIN_PREFIXES["opp_team"] + base_stat
                opp_team_stats[opp_team_id][stat_name] += 1

            if (
                "opp_player" in rule["domains"]
                and team_id
                and player_id
                and opp_team_id
            ):
                stat_name = DOMAIN_PREFIXES["opp_player"] + base_stat
                for my_player in context.get_on_court_players(opp_team_id):
                    opp_player_stats[(opp_team_id, my_player)][stat_name] += 1

            if "on_player" in rule["domains"] and team_id and player_id:
                if context.is_player_on_court(team_id, player_id):
                    stat_name = DOMAIN_PREFIXES["on_player"] + base_stat
                    for on_court_player in context.get_on_court_players(team_id):
                        on_player_stats[(team_id, on_court_player)][stat_name] += 1

    result_sets: Dict[ResultSetType, List[Dict]] = {}

    result_sets["team"] = [
        {"ext_team_id": team_id, **stats} for team_id, stats in team_stats.items()
    ]

    result_sets["player"] = [
        {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
        for (team_id, player_id), stats in player_stats.items()
    ]

    result_sets["opp_team"] = [
        {"ext_team_id": team_id, **stats} for team_id, stats in opp_team_stats.items()
    ]

    result_sets["opp_player"] = [
        {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
        for (team_id, player_id), stats in opp_player_stats.items()
    ]

    result_sets["on_player"] = [
        {"ext_team_id": team_id, "ext_player_id": player_id, **stats}
        for (team_id, player_id), stats in on_player_stats.items()
    ]

    return result_sets
