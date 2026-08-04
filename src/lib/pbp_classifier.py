"""
Shoot the Sheet - PBP Event Classifier

Matches raw source rows against ``core.pbp_events`` by building an
event key from the row and looking it up in the catalog.

Only rows with ``handling`` equal to a canonical ``PBP_EVENTS`` key are
trusted.  ``unreviewed`` rows and rows whose handling is no longer a
canonical event (e.g. the retired ``foul``) raise
:class:`UnclassifiedEventError` -- the game fails per-game until the
catalog is reviewed.  There is no backwards compatibility.
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


# ---------------------------------------------------------------------------
# nba_data match strategy
# ---------------------------------------------------------------------------

# For FG (MSG 1/2) the description distinguishes 2pt from 3pt; for FT
# (MSG 3) it distinguishes makes from misses.  The same key-building
# logic must be used by discovery and by the classifier or the two
# never agree.


def build_nba_signature(row: dict[str, Any]) -> dict:
    """Build the discovery/classification signature for an nba_data row.

    FG rows (MSG 1/2) are keyed by the 2pt/3pt distinction; FT rows
    (MSG 3) by the make/miss distinction.  This must match the discovery
    key builder or catalog rows are never found at classify time.
    """
    msgtype = _to_int(row.get("EVENTMSGTYPE"))
    actiontype = _to_int(row.get("EVENTMSGACTIONTYPE"))
    sig: dict[str, Any] = {"EVENTMSGTYPE": msgtype, "EVENTMSGACTIONTYPE": actiontype}
    desc = _description(row).upper()
    if msgtype in (1, 2):
        if "3PT" in desc:
            sig["text_contains"] = "3PT"
        else:
            sig["text_not_contains"] = "3PT"
    elif msgtype == 3:
        if "MISS" in desc:
            sig["text_contains"] = "MISS"
        else:
            sig["text_not_contains"] = "MISS"
    return sig


def build_nba_event_key(signature: dict) -> str:
    """Build the catalog event key for an nba_data signature."""
    key = f"MSG={signature['EVENTMSGTYPE']}_ACT={signature['EVENTMSGACTIONTYPE']}"
    if "text_contains" in signature:
        key += f"_HAS={signature['text_contains']}"
    elif "text_not_contains" in signature:
        key += f"_NO={signature['text_not_contains']}"
    return key


def _description(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("HOMEDESCRIPTION", "")),
        str(row.get("NEUTRALDESCRIPTION", "")),
        str(row.get("VISITORDESCRIPTION", "")),
    ]
    return " ".join(p for p in parts if p)


class FieldLookupStrategy:
    """Build event keys from nba_data CSV rows.

    Uses the same signature/key builders as discovery so catalog rows
    discovered with text keys (``_HAS=3PT``, ``_NO=MISS``, ...) are
    actually found at classify time.
    """

    def build_signature(self, row: dict[str, Any]) -> dict:
        return build_nba_signature(row)

    def build_event_key(self, signature: dict) -> str:
        return build_nba_event_key(signature)


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
