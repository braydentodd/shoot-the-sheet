"""
Shoot the Sheet - PBP Derivation Error Model

The derivation engine accumulates ALL errors for a game and returns
them (finish-the-game-first); the orchestrator records each one in
``core.errors`` and marks the game errored.

This is a pure data model -- no I/O, no logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PbpError:
    """A single derivation error or invariant violation.

    Attributes:
        rule: The ``INVARIANTS`` key or chain rule that fired.
        message: Human-readable description.
        game_id: External game id.
        event_id: Id of the offending event (source id or derived id).
        seq: Sequence position of the offending event.
        event: Canonical event name of the offending event.
        team_id: Team id of the offending event.
        player_id: Player id of the offending event.
    """

    rule: str
    message: str
    game_id: str = ""
    event_id: str | None = None
    seq: int | None = None
    event: str | None = None
    team_id: str | None = None
    player_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_log_payload(self) -> dict[str, Any]:
        """Return the ``log_error`` keyword arguments for this error."""
        return {
            "message": self.message,
            "ext_game_id": self.game_id or None,
            "event_id": self.event_id,
            "seq": self.seq,
            "event": self.event,
        }
