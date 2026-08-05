"""
Shoot the Sheet - PBP Event Classifier

Matches raw source rows against ``core.pbp_events`` by building an
event key from the row and looking it up in the catalog.

Only rows with ``handling`` equal to a canonical ``PBP_EVENTS`` key are
trusted.  ``unreviewed`` rows and rows whose handling is no longer a
canonical event (e.g. the retired ``foul``) raise
:class:`UnclassifiedEventError` -- the game fails per-game until the
catalog is reviewed.  There is no backwards compatibility.

The key-building strategy is source-specific: each source implements
:class:`MatchStrategy` in its own ``classifier`` module (see
``src/sources``) and supplies it at construction.
"""

import logging
from typing import Any, Protocol

from src.definitions.pbp import PBP_EVENTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Classification:
    """Result of classifying a raw source row."""

    __slots__ = ("event_key", "handling")

    def __init__(self, handling: str, event_key: str):
        self.handling = handling
        self.event_key = event_key

    @property
    def is_track(self) -> bool:
        return self.handling in PBP_EVENTS

    @property
    def is_ignore(self) -> bool:
        return self.handling == "ignore"


class MatchStrategy(Protocol):
    """How to build an event key from a raw source row."""

    def build_signature(self, row: dict[str, Any]) -> dict: ...

    def build_event_key(self, signature: dict) -> str: ...


class UnclassifiedEventError(Exception):
    """Raised when a raw event doesn't match a trusted catalog entry."""

    def __init__(self, signature: dict, raw_row: dict[str, Any]):
        self.signature = signature
        self.raw_row = raw_row
        super().__init__(f"Unclassified event: {signature}")


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class EventClassifier:
    """Classify raw source rows by event key lookup."""

    def __init__(
        self,
        catalog_rows: list[dict[str, Any]],
        strategy: MatchStrategy,
    ):
        self._classified: dict[str, Classification] = {}
        self._unreviewed_keys: set[str] = set()

        for row in catalog_rows:
            event_key = row["event_key"]
            handling = row["handling"]
            if handling == "ignore":
                self._classified[event_key] = Classification(
                    handling=handling, event_key=event_key,
                )
            elif handling not in PBP_EVENTS:
                # Unreviewed, or a retired handling value (e.g. ``foul``):
                # not trusted -- the row fails closed until reviewed.
                self._unreviewed_keys.add(event_key)
            else:
                self._classified[event_key] = Classification(
                    handling=handling, event_key=event_key,
                )

        self._strategy = strategy

    def classify(self, row: dict[str, Any]) -> Classification:
        signature = self._strategy.build_signature(row)
        event_key = self._strategy.build_event_key(signature)

        if event_key in self._classified:
            return self._classified[event_key]
        raise UnclassifiedEventError(signature, row)

    @property
    def classified_count(self) -> int:
        return len(self._classified)

    @property
    def unreviewed_count(self) -> int:
        return len(self._unreviewed_keys)
