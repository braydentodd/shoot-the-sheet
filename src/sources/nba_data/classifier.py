"""
Shoot the Sheet - nba_data Match Strategy

The nba_data (nbastats CSV) implementation of the classifier's
:class:`~src.lib.pbp_classifier.MatchStrategy` protocol.  It builds the
catalog event key from a raw CSV row.

The same signature/key builders must be used by discovery and by the
classifier or the two never agree.  Discovery resolves these builders
from the source's client module (``client.build_signature`` /
``client.build_event_key``), so lib code stays source-agnostic.
"""

from typing import Any

from src.lib.transform import to_int

# ============================================================================
# Signature + key builders
# ============================================================================


def build_nba_signature(row: dict[str, Any]) -> dict:
    """Build the discovery/classification signature for an nba_data row.

    FG rows (MSG 1/2) are keyed by the 2pt/3pt distinction; FT rows
    (MSG 3) by the make/miss distinction.  This must match the discovery
    key builder or catalog rows are never found at classify time.
    """
    msgtype = to_int(row.get("EVENTMSGTYPE"))
    actiontype = to_int(row.get("EVENTMSGACTIONTYPE"))
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


# ============================================================================
# Helpers
# ============================================================================


def _description(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("HOMEDESCRIPTION", "")),
        str(row.get("NEUTRALDESCRIPTION", "")),
        str(row.get("VISITORDESCRIPTION", "")),
    ]
    return " ".join(p for p in parts if p)
