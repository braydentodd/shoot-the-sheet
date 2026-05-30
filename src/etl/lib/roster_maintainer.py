"""The Glass - Roster Stager

Roster snapshots are merged into the transient staging schema. Promotion into
core profile and roster tables happens in the entity matching phase.
"""

import logging
from typing import Any, Dict, Iterable, List, Tuple

from src.etl.lib.load import merge_staged_entity_rows
from src.etl.lib.sources_resolver import get_rosters_fields

logger = logging.getLogger(__name__)


def _normalize_roster_snapshot(
    roster_pairs: Iterable[Tuple[Any, ...]],
) -> List[Tuple[Any, Any, Tuple[Any, ...]]]:
    """Normalize roster snapshots to ``(team_source_id, player_source_id, extra_fields)``."""
    normalized: List[Tuple[Any, Any, Tuple[Any, ...]]] = []
    for entry in roster_pairs:
        if not isinstance(entry, (tuple, list)):
            continue
        if len(entry) < 2:
            continue
        team_source_id, player_source_id = entry[0], entry[1]
        extra_fields = entry[2:] if len(entry) > 2 else ()
        if team_source_id is None or player_source_id is None:
            continue
        normalized.append((team_source_id, player_source_id, extra_fields))
    return normalized


def stage_rosters(
    league_key: str,
    source_key: str,
    roster_pairs: Iterable[Tuple[Any, ...]],
    season: str = None,
) -> Dict[str, int]:
    """Merge roster snapshots into ``staging.teams`` and ``staging.players``."""
    pairs = _normalize_roster_snapshot(roster_pairs)
    rosters_fields = get_rosters_fields(league_key, source_key)
    rosters_col_names = list(rosters_fields.keys())

    team_rows: Dict[Any, Dict[str, Any]] = {}
    player_rows: Dict[Any, Dict[str, Any]] = {}

    for team_source_id, player_source_id, extra_fields in pairs:
        team_rows.setdefault(team_source_id, {})
        player_data: Dict[str, Any] = {
            'team_source_id': str(team_source_id),
        }
        for idx, col_name in enumerate(rosters_col_names):
            if idx < len(extra_fields):
                val = extra_fields[idx]
                if val is not None:
                    player_data[col_name] = val
        player_rows[player_source_id] = player_data

    teams_staged = merge_staged_entity_rows('team', team_rows, league_key, source_key)
    players_staged = merge_staged_entity_rows('player', player_rows, league_key, source_key)

    counts = {
        'teams_staged': teams_staged,
        'players_staged': players_staged,
    }
    logger.info(
        'Roster stage %s/%s: teams staged=%d | players staged=%d',
        league_key, source_key,
        counts['teams_staged'], counts['players_staged'],
    )
    return counts
