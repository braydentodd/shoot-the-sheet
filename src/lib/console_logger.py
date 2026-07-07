"""
Shoot the Sheet - Console Logger

Provides a single, opinionated logging configuration used by every CLI entry
point in the codebase.  Goal: consistent log format across the ETL pipeline.

Conventions:
    INFO     phase boundaries, totals, summary lines
    WARNING  recoverable skips (e.g. unresolved source IDs)
    ERROR    fatal failures (raised exceptions)
    DEBUG    per-row / per-call traces (off by default)

Usage:
    from src.lib.logger_setup import setup_logging, phase_marker
    setup_logging(verbose=False)
    logger.info(phase_marker('discover'))
"""

from __future__ import annotations

import logging
import sys
from typing import Union

# Fixed-width slots keep multi-process output aligned for human scanning.
_LEVEL_WIDTH = 7  # ' WARNING' (with leading space) is 8; longest is 'CRITICAL' (8)
_NAME_WIDTH = 28  # truncated module name
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


class _FixedWidthFormatter(logging.Formatter):
    """Pad level + logger name to fixed widths so columns line up."""

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname.ljust(_LEVEL_WIDTH)[:_LEVEL_WIDTH]
        name = record.name
        if len(name) > _NAME_WIDTH:
            # Keep the rightmost segments; they identify the source module.
            name = "..." + name[-(_NAME_WIDTH - 3) :]
        else:
            name = name.ljust(_NAME_WIDTH)
        record.levelname = level
        record.name = name
        return super().format(record)


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    *,
    stream=None,
) -> None:
    """Configure root logging once for the running process.

    Subsequent calls are no-ops so library code can defensively call this
    without clobbering an explicit setup.

    Args:
        verbose: If True, set the root level to DEBUG.
        quiet:   If True, set the root level to WARNING.
        stream:  Optional stream (defaults to ``sys.stderr``).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        _FixedWidthFormatter(
            fmt="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
            datefmt=_DATE_FMT,
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down predictable noise from third-party libraries.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

    _CONFIGURED = True


# ---------------------------------------------------------------------------
# Phase / banner helpers (return strings; callers log them at INFO)
# ---------------------------------------------------------------------------

_BAR = "=" * 78
_RULE = "-" * 78


def phase_marker(name: str, detail: Union[str, None] = None) -> str:
    """Return a single-line phase boundary string.

    Use with ``logger.info(phase_marker('rosters', 'league=nba'))``.  The
    horizontal rule lives in :func:`phase_block` for full headers.
    """
    label = f"PHASE :: {name}"
    if detail:
        label = f"{label}  ({detail})"
    return label


def phase_block(name: str, detail: Union[str, None] = None) -> str:
    """Multi-line phase header (rule + label + rule)."""
    return f"\n{_RULE}\n{phase_marker(name, detail)}\n{_RULE}"


def banner(title: str, subtitle: Union[str, None] = None) -> str:
    """Multi-line top-of-run banner."""
    out = [_BAR, f"  {title}"]
    if subtitle:
        out.append(f"  {subtitle}")
    out.append(_BAR)
    return "\n".join(out)
