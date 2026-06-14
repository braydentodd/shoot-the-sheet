"""
Shoot the Sheet - Sheets Source Configuration

Pure data definitions for the ``shoot_the_sheet`` source: metadata for
syncing user-edited values from Google Sheets back to profile tables.

Unlike API sources (nba_api, pbp_stats), this is a ``writer`` source that
doesn't hold source-id columns -- it edits canonical profile data via
sts_id anchor column.
"""

from typing import Any, Dict, Union

# ==========================================================================
# RATE LIMITS
# ==========================================================================

RATE_LIMITS: Dict[str, Union[float, int]] = {
    "requests_per_second": 1.0,
    "max_retries": 3,
    "backoff_base": 30,
    "timeout_default": 30,
    "timeout_bulk": 120,
    "max_consecutive_failures": 5,
}
