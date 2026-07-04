"""
Shoot the Sheet - NBA API Play-by-Play Normalizer

Converts NBA API playbyplayv3 format to standard PBP events.

NBA API V3 Format:
    - actionType: String ("Made Shot", "Missed Shot", "Free Throw", etc.)
    - subType: String with shot details ("2PT", "3PT", "Driving Layup", etc.)
    - shotResult: "Made" or "Missed"
    - isFieldGoal: 1 for FG, 0 for other
    - clock: PT10M27.00S (period time remaining, resets each period)

Standard Event Format:
    - identity: "nba_id"
    - ext_game_id: str
    - event_id: int (sequential)
    - secs: int (cumulative from game start)
    - event_type: EventType (from pbp_events.py)
    - pbp_ext_team_id: Optional[str]
    - pbp_ext_player_id: Optional[str]
"""

import logging
import re
from typing import Dict, List, Optional

from src.definitions.pbp_events import EventType

logger = logging.getLogger(__name__)

# ============================================================================
# TIMESTAMP PARSING
# ============================================================================

PERIOD_DURATIONS_SECS = {
    1: 720,  # Q1: 12 minutes
    2: 720,  # Q2: 12 minutes
    3: 720,  # Q3: 12 minutes
    4: 720,  # Q4: 12 minutes
    # OT periods: 300 seconds (5 minutes) each
}


def parse_nba_clock(clock_str: str) -> int:
    """Parse NBA API clock format to seconds remaining in period.

    Args:
        clock_str: Clock string in format "PT10M27.00S"

    Returns:
        Seconds remaining in period as integer
    """
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", clock_str)
    if not match:
        logger.warning("Could not parse clock string: %s", clock_str)
        return 0

    minutes = int(match.group(1) or 0)
    seconds = float(match.group(2) or 0)

    return int(minutes * 60 + seconds)


def calc_cumulative_secs(period: int, clock_remaining_secs: int) -> int:
    """Calculate cumulative game seconds from period and remaining time.

    Args:
        period: Period number (1-4 for regulation, 5+ for OT)
        clock_remaining_secs: Seconds remaining in current period

    Returns:
        Cumulative seconds from game start
    """
    period_start_secs = 0
    for p in range(1, period):
        if p <= 4:
            period_start_secs += PERIOD_DURATIONS_SECS[p]
        else:
            period_start_secs += 300  # OT periods are 5 minutes

    # Current period duration
    if period <= 4:
        period_duration = PERIOD_DURATIONS_SECS[period]
    else:
        period_duration = 300

    elapsed_in_period = period_duration - clock_remaining_secs
    return period_start_secs + elapsed_in_period


# ============================================================================
# EVENT TYPE DETECTION
# ============================================================================


def detect_event_type(action: Dict) -> Optional[EventType]:
    """Determine standard event type from NBA API action.

    Args:
        action: NBA API action dict with actionType, subType, shotResult, etc.

    Returns:
        Standard EventType or None if unmapped
    """
    action_type = action.get("actionType", "").lower()
    sub_type = action.get("subType", "").lower()
    shot_result = action.get("shotResult", "").lower()
    description = action.get("description", "").lower()

    # Shots (distinguish 2PT vs 3PT from subType)
    if action_type == "made shot" or (
        shot_result == "made" and action.get("isFieldGoal")
    ):
        if "3pt" in sub_type or "three point" in description:
            return "fg3_make"
        else:
            return "fg2_make"

    if action_type == "missed shot" or (
        shot_result == "missed" and action.get("isFieldGoal")
    ):
        if "3pt" in sub_type or "three point" in description:
            return "fg3_miss"
        else:
            return "fg2_miss"

    # Free throws
    if action_type == "free throw" or "free throw" in description:
        if shot_result == "made":
            return "ft_make"
        elif shot_result == "missed":
            return "ft_miss"
        # If no shotResult, check description
        elif "makes" in description or "1 of 1" in description:
            return "ft_make"
        elif "misses" in description:
            return "ft_miss"

    # Rebounds (distinguish offensive vs defensive from subType or teamId comparison)
    if action_type == "rebound":
        if "offensive" in sub_type:
            return "o_reb"
        elif "defensive" in sub_type:
            return "d_reb"

    # Turnovers
    if action_type == "turnover" or "turnover" in description:
        return "turnover"

    # Blocks
    if action_type == "block" or "block" in description:
        return "block"

    # Steals
    if action_type == "steal" or "steal" in description:
        return "steal"

    # Substitutions
    if action_type == "substitution":
        # NBA API represents sub as single action with subType "IN" or "OUT"
        if "in" in sub_type:
            return "sub_in"
        elif "out" in sub_type:
            return "sub_out"

    # Jump balls
    if action_type == "jump ball" or "jump ball" in description:
        # Winner vs loser determined by teamId/personId in context
        # We'll generate both events in post-processing
        return None  # Handled specially in normalize_nba_pbp_events

    # Period start/end
    if action_type == "period start" or "start period" in description:
        return "period_start"

    if action_type == "period end" or "end period" in description:
        return None  # Not accumulating period_end events

    # Timeouts, violations, fouls - not accumulated
    if action_type in ["timeout", "violation", "foul"]:
        return None

    logger.debug("Unmapped NBA action type: %s (subType=%s)", action_type, sub_type)
    return None


# ============================================================================
# POSS_ENDING_FT_TRIP DETECTION
# ============================================================================


def is_poss_ending_ft_trip(
    actions: List[Dict], ft_index: int, home_team_id: str, away_team_id: str
) -> bool:
    """Determine if FT is possession-ending by looking at next event.

    Args:
        actions: Full sorted list of actions
        ft_index: Index of the FT action
        home_team_id: Home team ID
        away_team_id: Away team ID

    Returns:
        True if FT is potentially possession-ending
    """
    ft_action = actions[ft_index]
    ft_team_id = ft_action.get("teamId")

    # Look ahead to next non-timeout/sub action
    for next_action in actions[ft_index + 1 :]:
        next_action_type = next_action.get("actionType", "").lower()
        next_team_id = next_action.get("teamId")

        # Skip timeouts and period end
        if next_action_type in ["timeout", "period end"]:
            continue

        # If next action is by same team, check if it's offensive rebound or made shot (and-one)
        if next_team_id == ft_team_id:
            # Offensive rebound after FT = YES (either team can get rebound)
            if (
                next_action_type == "rebound"
                and "offensive" in next_action.get("subType", "").lower()
            ):
                return True
            # Made shot immediately before FT = and-one, FT is NOT possession-ending
            # But we're looking forward, so if next action is another FT or made shot, it's flagrant/technical
            if next_action_type in ["made shot", "free throw"]:
                return False  # Team retains possession (flagrant/technical)
            # Otherwise, team retained possession somehow
            return False

        # If next action is by opponent, possession changed
        if next_team_id != ft_team_id:
            return True

        # If next action is jump ball, check outcome
        if next_action_type == "jump ball":
            # Complex - jump ball could go either way
            # For now, assume possession-ending
            return True

    # If we reach end of actions (period end), it's possession-ending
    return True


# ============================================================================
# NORMALIZATION
# ============================================================================


def normalize_nba_pbp_events(
    raw_actions: List[Dict],
    ext_game_id: str,
    home_team_id: str,
    away_team_id: str,
    identity: str = "nba_id",
) -> List[Dict]:
    """Convert NBA API playbyplayv3 actions to standard PBP events.

    Args:
        raw_actions: List of actions from NBA API playbyplayv3
        ext_game_id: External game ID
        home_team_id: Home team external ID
        away_team_id: Away team external ID
        identity: Identity code (default: "nba_id")

    Returns:
        List of standardized PBP event dicts ready for pbp_events_staging
    """
    events: List[Dict] = []
    event_id = 0

    # Sort actions by actionNumber to ensure chronological order
    sorted_actions = sorted(raw_actions, key=lambda x: x.get("actionNumber", 0))

    # Track players on court per team for synthetic sub_in backfilling
    on_court_players: Dict[str, set] = {home_team_id: set(), away_team_id: set()}
    period_tracker: Dict[int, bool] = {}  # period -> whether we've seen events yet

    for idx, action in enumerate(sorted_actions):
        action_type_str = action.get("actionType", "").lower()
        period = action.get("period", 1)
        clock_str = action.get("clock", "PT12M00.00S")
        team_id = str(action.get("teamId")) if action.get("teamId") else None
        person_id = str(action.get("personId")) if action.get("personId") else None

        # Parse timestamp
        clock_remaining = parse_nba_clock(clock_str)
        secs = calc_cumulative_secs(period, clock_remaining)

        # Detect standard event type
        event_type = detect_event_type(action)

        # Special handling: Jump balls generate win/lose events
        if action_type_str == "jump ball":
            # Jump ball involves two players, winner gets possession
            # NBA API may indicate winner via subType or description
            # For now, log and skip (needs more research for proper implementation)
            logger.debug("Jump ball detected in game %s, skipping for now", ext_game_id)
            continue

        # Special handling: Generate new_poss events
        # These are derived from turnovers, defensive rebounds, period starts
        if event_type == "turnover":
            # Turnover = opponent gets new possession
            opp_team_id = away_team_id if team_id == home_team_id else home_team_id
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": event_type,
                    "pbp_ext_team_id": team_id,
                    "pbp_ext_player_id": person_id,
                }
            )
            event_id += 1
            # Generate new_poss for opponent
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": "new_poss",
                    "pbp_ext_team_id": opp_team_id,
                    "pbp_ext_player_id": None,
                }
            )
            event_id += 1
            continue

        if event_type == "d_reb":
            # Defensive rebound = rebounding team gets new possession
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": event_type,
                    "pbp_ext_team_id": team_id,
                    "pbp_ext_player_id": person_id,
                }
            )
            event_id += 1
            # Generate new_poss for rebounding team
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": "new_poss",
                    "pbp_ext_team_id": team_id,
                    "pbp_ext_player_id": None,
                }
            )
            event_id += 1
            continue

        if event_type == "period_start":
            # Period start = new possessions for both teams (jump ball determines who gets first)
            # For simplicity, generate new_poss for home team (actual logic needs jump ball result)
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": event_type,
                    "pbp_ext_team_id": None,
                    "pbp_ext_player_id": None,
                }
            )
            event_id += 1
            # Generate new_poss for home team (placeholder)
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": secs,
                    "event_type": "new_poss",
                    "pbp_ext_team_id": home_team_id,
                    "pbp_ext_player_id": None,
                }
            )
            event_id += 1
            period_tracker[period] = True
            continue

        # Special handling: poss_ending_ft_trip
        if event_type in ["ft_make", "ft_miss"]:
            # Check if this FT is possession-ending
            if is_poss_ending_ft_trip(sorted_actions, idx, home_team_id, away_team_id):
                events.append(
                    {
                        "identity": identity,
                        "ext_game_id": ext_game_id,
                        "event_id": event_id,
                        "secs": secs,
                        "event_type": "poss_ending_ft_trip",
                        "pbp_ext_team_id": team_id,
                        "pbp_ext_player_id": person_id,
                    }
                )
                event_id += 1

        # Track substitutions for backfilling
        if event_type == "sub_in" and team_id and person_id:
            on_court_players[team_id].add(person_id)
        elif event_type == "sub_out" and team_id and person_id:
            on_court_players[team_id].discard(person_id)

        # Backfill synthetic sub_in if player has event but wasn't subbed in
        if (
            event_type
            and event_type not in ["sub_in", "sub_out", "period_start"]
            and person_id
            and team_id
        ):
            if person_id not in on_court_players[team_id] and period in period_tracker:
                # Player had event but wasn't subbed in - inject synthetic sub_in at period start
                period_start_secs = calc_cumulative_secs(
                    period, PERIOD_DURATIONS_SECS.get(period, 720)
                )
                events.append(
                    {
                        "identity": identity,
                        "ext_game_id": ext_game_id,
                        "event_id": event_id,
                        "secs": period_start_secs,
                        "event_type": "sub_in",
                        "pbp_ext_team_id": team_id,
                        "pbp_ext_player_id": person_id,
                    }
                )
                event_id += 1
                on_court_players[team_id].add(person_id)

        # Skip unmapped events
        if not event_type:
            continue

        # Build standard event
        events.append(
            {
                "identity": identity,
                "ext_game_id": ext_game_id,
                "event_id": event_id,
                "secs": secs,
                "event_type": event_type,
                "pbp_ext_team_id": team_id,
                "pbp_ext_player_id": person_id,
            }
        )
        event_id += 1

    # Generate sub_out events at end of game for all on-court players
    final_secs = events[-1]["secs"] if events else 2880  # Default to end of regulation
    for team_id, players in on_court_players.items():
        for player_id in players:
            events.append(
                {
                    "identity": identity,
                    "ext_game_id": ext_game_id,
                    "event_id": event_id,
                    "secs": final_secs,
                    "event_type": "sub_out",
                    "pbp_ext_team_id": team_id,
                    "pbp_ext_player_id": player_id,
                }
            )
            event_id += 1

    logger.info(
        "Normalized %d NBA API actions to %d standard events for game %s",
        len(raw_actions),
        len(events),
        ext_game_id,
    )

    return events
