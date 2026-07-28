"""
Shoot the Sheet - Entity Resolver

Source-agnostic entity resolution against staging tables.

Looks up player/team IDs in staging.players and staging.teams.  PBP
sources are not identity authorities -- staging tables are the single
source of truth.

Consumers receive a resolver callable as a parameter.  In
production the orchestrator provides a DB-backed resolver; in tests a
mock resolver is injected.
"""

from typing import Callable, Optional, Tuple

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

# A resolver returns (entity_type, team_id) or (None, None) for unknown entities.
#   entity_type: "player" | "team" | None
#   team_id:     the team the entity belongs to, or None
EntityResolver = Callable[[str], Tuple[Optional[str], Optional[str]]]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_entity_resolver(conn, identity_code: str) -> EntityResolver:
    """Build a resolver callable from staging.players and staging.teams.

    Queries the DB once and returns a closure that performs O(1) dict
    lookups.  Safe to call thousands of times per game.

    Args:
        conn: A psycopg2 database connection.
        identity_code: The identity to scope queries to (e.g. ``"nba_id"``).

    Returns:
        A callable ``(entity_id: str) -> (entity_type | None, team_id | None)``.
    """
    teams: set[str] = set()
    players: dict[str, str] = {}  # player_id -> team_id

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ext_id FROM staging.teams WHERE identity = %s",
            (identity_code,),
        )
        for (ext_id,) in cur:
            teams.add(ext_id)

        cur.execute(
            "SELECT ext_id, team_id FROM staging.players WHERE identity = %s",
            (identity_code,),
        )
        for ext_id, team_id in cur:
            players[ext_id] = team_id

    def resolve(entity_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolve an entity ID to (entity_type, team_id).

        Returns (None, None) for blank, zero, or unknown IDs.
        """
        if not entity_id or entity_id == "0":
            return None, None
        if entity_id in teams:
            return ("team", entity_id)
        if entity_id in players:
            return ("player", players[entity_id])
        return None, None

    return resolve
