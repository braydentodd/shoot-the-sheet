"""
Shoot the Sheet - Rate Limiting Configuration

Centralized rate limiting for every source and destination.
Each source/destination can declare its own overrides in the
``SOURCE_RATE_LIMITS`` dict below.  Values not overridden fall
back to ``DEFAULT_RATE_LIMITS``.

Minimal set of knobs:
- requests_per_second: Throttling (lower = slower)
- max_retries: Retry attempts before giving up
- backoff_base: Linear backoff multiplier in seconds
- max_backoff: Cap on backoff wait (0 = no cap)
- timeout_default: Request timeout (seconds)
- timeout_bulk: Timeout for bulk/long-running requests
- max_consecutive_failures: When to trigger auto-restart
- auto_restart: Whether to trigger auto-restart on consecutive failures
"""

from typing import Any, Dict

DEFAULT_RATE_LIMITS: Dict[str, Any] = {
    "requests_per_second": 2.0,
    "max_retries": 3,
    "backoff_base": 30,
    "max_backoff": 0,
    "timeout_default": 30,
    "timeout_bulk": 120,
    "max_consecutive_failures": 5,
    "auto_restart": True,
}

SOURCE_RATE_LIMITS: Dict[str, Dict[str, Any]] = {
    "nba_api": {
        "requests_per_second": 0.25,
        "max_retries": 3,
        "backoff_base": 120,
        "max_backoff": 300,
        "timeout_default": 60,
        "timeout_bulk": 120,
        "max_consecutive_failures": 5,
        "auto_restart": True,
    },
}
