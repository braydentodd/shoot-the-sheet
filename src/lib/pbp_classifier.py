"""
Shoot the Sheet - PBP Event Classifier

Matches raw source rows against ``core.pbp_events`` by building an
event key from the row and looking it up in the catalog.

Only rows with ``handling != 'unreviewed'`` are trusted.
"""

import logging
from typing import Any, Dict, List, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Classification:
    """Result of classifying a raw source row."""

    __slots__ = ("handling", "event_key")

    def __init__(self, handling: str, event_key: str):
        self.handling = handling
        self.event_key = event_key

    @property
    def is_track(self) -> bool:
        return self.handling not in ("unreviewed", "ignore")

    @property
    def is_ignore(self) -> bool:
        return self.handling == "ignore"


class MatchStrategy(Protocol):
    """How to build an event key from a raw source row."""

    def build_signature(self, row: Dict[str, Any]) -> dict: ...

    def build_event_key(self, signature: dict) -> str: ...


class UnclassifiedEventError(Exception):
    """Raised when a raw event doesn't match any catalog entry."""

    def __init__(self, signature: dict, raw_row: Dict[str, Any]):
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
        catalog_rows: List[Dict[str, Any]],
        strategy: MatchStrategy,
    ):
        self._classified: Dict[str, Classification] = {}
        self._unreviewed_keys: set[str] = set()

        for row in catalog_rows:
            event_key = row["event_key"]
            handling = row["handling"]
            if handling == "unreviewed":
                self._unreviewed_keys.add(event_key)
            else:
                self._classified[event_key] = Classification(
                    handling=handling, event_key=event_key,
                )

        self._strategy = strategy

    def classify(self, row: Dict[str, Any]) -> Classification:
        signature = self._strategy.build_signature(row)
        event_key = self._strategy.build_event_key(signature)

        if event_key in self._classified:
            return self._classified[event_key]
        if event_key in self._unreviewed_keys:
            raise UnclassifiedEventError(signature, row)
        raise UnclassifiedEventError(signature, row)

    @property
    def classified_count(self) -> int:
        return len(self._classified)

    @property
    def unreviewed_count(self) -> int:
        return len(self._unreviewed_keys)


# ---------------------------------------------------------------------------
# nba_data match strategy
# ---------------------------------------------------------------------------


class FieldLookupStrategy:
    """Build event keys from nba_data CSV rows."""

    def build_signature(self, row: Dict[str, Any]) -> dict:
        return {
            "EVENTMSGTYPE": _to_int(row.get("EVENTMSGTYPE")),
            "EVENTMSGACTIONTYPE": _to_int(row.get("EVENTMSGACTIONTYPE")),
        }

    def build_event_key(self, sig: dict) -> str:
        return f"MSG={sig['EVENTMSGTYPE']}_ACT={sig['EVENTMSGACTIONTYPE']}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_int(val: Any) -> int:
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0
