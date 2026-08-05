"""Shared helpers for PBP tests."""

from src.definitions.pbp import PBPEvent


def ev(
    event_id: str,
    event: str,
    team: str,
    player: str = "",
    *,
    secs: int | None = 0,
    period: int = 1,
    chain_id: str | None = None,
    fouled_player_id: str | None = None,
    source: str | None = None,
) -> PBPEvent:
    """Build a minimal PBPEvent row for tests."""
    return {
        "identity": "nba_id",
        "game_id": "G1",
        "event_id": event_id,
        "seq": 0,
        "secs": secs,
        "period": period,
        "team_id": team,
        "player_id": player,
        "event": event,
        "chain_id": chain_id,
        "fouled_player_id": fouled_player_id,
        "source": source or str(event_id),
    }


def untimed(event_id: str, event: str, team: str, player: str = "",
            period: int = 1, chain_id: str | None = None) -> PBPEvent:
    """Build a PBPEvent row without a clock (secs=None)."""
    return ev(event_id, event, team, player, secs=None, period=period,
              chain_id=chain_id)


def events_of(result, event: str) -> list[PBPEvent]:
    return [e for e in result.events if e["event"] == event]
