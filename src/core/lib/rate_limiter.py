"""
Shoot the Sheet - Centralized Rate Limiter

Source-agnostic rate limiting engine with configurable limits per source/destination.
Implements token bucket algorithm for request throttling and exponential backoff
for retries with auto-restart on consecutive failures.

Default values are defined in src.core.definitions.rate_limits and can be overridden
by sources/destinations providing their own rate_limits configuration.
"""

import logging
import time
from typing import Any, Callable, Dict, Union

from src.core.definitions.rate_limits import DEFAULT_RATE_LIMITS

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using token bucket algorithm with configurable limits.

    Args:
        config: Rate limit configuration dict. If None, uses DEFAULT_RATE_LIMITS.
        config can override any of the default values.
        source_key: Optional identifier for the source/destination (for logging).
    """

    def __init__(
        self,
        config: Union[Dict[str, Any], None] = None,
        source_key: Union[str, None] = None,
    ):
        self.config = {**DEFAULT_RATE_LIMITS, **(config or {})}
        self.source_key = source_key
        self._last_request_time = 0.0
        self._consecutive_failures = 0

    def acquire(self) -> None:
        """Block until a request can be made according to rate limits."""
        requests_per_second = self.config.get("requests_per_second", 1.0)
        if requests_per_second <= 0:
            return

        min_interval = 1.0 / requests_per_second
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            logger.debug("Rate limiting: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def record_success(self) -> None:
        """Reset consecutive failure counter on success."""
        self._consecutive_failures = 0

    def record_failure(self) -> bool:
        """Record a failure and return True if max consecutive failures reached.

        When max consecutive failures is reached and auto_restart is enabled, this
        signals that auto-restart should be triggered (e.g., the orchestrator should
        restart the pipeline). If auto_restart is disabled, returns False to allow
        normal retry behavior to continue.
        """
        self._consecutive_failures += 1
        max_failures = self.config.get("max_consecutive_failures", 5)
        if self._consecutive_failures >= max_failures:
            auto_restart = self.config.get("auto_restart", True)
            if auto_restart:
                logger.error(
                    "Max consecutive failures (%d) reached for %s - auto-restart recommended",
                    max_failures,
                    self.source_key or "unknown",
                )
                return True
            else:
                logger.warning(
                    "Max consecutive failures (%d) reached for %s - auto-restart disabled",
                    max_failures,
                    self.source_key or "unknown",
                )
                return False
        return False

    def get_timeout(self, is_bulk: bool = False) -> int:
        """Get timeout value for request type."""
        if is_bulk:
            return self.config.get("timeout_bulk", 120)
        return self.config.get("timeout_default", 30)

    def with_retry(self, func: Callable, max_retries: Union[int, None] = None) -> Any:
        """Execute func with exponential backoff on failure.

        Args:
            func: Zero-arg callable to execute.
            max_retries: Override default max_retries from config.

        Returns:
            Result of func() on first success.

        Raises:
            Last exception if all retries exhausted or auto-restart triggered.
        """
        retries = max_retries or self.config.get("max_retries", 3)
        backoff_base = self.config.get("backoff_base", 30)

        for attempt in range(1, retries + 1):
            try:
                self.acquire()
                result = func()
                self.record_success()
                return result
            except Exception as exc:
                if attempt >= retries:
                    logger.error("Retry exhausted after %d attempts", retries)
                    raise

                if self.record_failure():
                    # Auto-restart triggered
                    raise RuntimeError(
                        f"Auto-restart triggered for {self.source_key or 'unknown'} "
                        f"after {self._consecutive_failures} consecutive failures"
                    ) from exc

                wait = attempt * backoff_base
                logger.warning(
                    "Attempt %d failed, retrying in %ds: %s", attempt, wait, str(exc)
                )
                time.sleep(wait)

        raise RuntimeError(f"with_retry exhausted {retries} attempts")


def get_rate_limiter(
    source_key: str,
    config: Union[Dict[str, Any], None] = None,
    is_destination: bool = False,
) -> RateLimiter:
    """Get a RateLimiter instance for a given source or destination key.

    For sources, reads ``RATE_LIMITS`` from the source's own config module
    (e.g. ``nba_api/config.py``).  For destinations, reads from the
    ``DESTINATIONS`` registry.
    """
    if is_destination:
        from src.publish.definitions.destinations import DESTINATIONS

        registry = DESTINATIONS
        config_data = registry.get(source_key, {})
        rate_limits = config_data.get("rate_limits")
        return RateLimiter(rate_limits or config, source_key=source_key)

    # Sources: read from the source's config module
    from src.etl.sources.registry import get_source_modules

    source_config, _ = get_source_modules(source_key)
    if source_config and hasattr(source_config, "RATE_LIMITS"):
        return RateLimiter(source_config.RATE_LIMITS, source_key=source_key)
    return RateLimiter(config, source_key=source_key)
