"""
Shoot the Sheet - Centralized CLI Helpers

Shared argparse pieces and stdout-formatting helpers used by every CLI entry
point.  Goal: identical look-and-feel across ETL and Publish runs.

Provides:
    HelpFormatter           - widened argparse formatter (uniform metavars)
    make_base_parser()      - returns an ArgumentParser pre-loaded with the
                              flags every CLI in the codebase shares
    print_banner()          - top-of-run banner (timestamp + title)
    print_phase_separator() - lightweight phase divider for stdout
    print_summary()         - aligned key/value summary block
    progress()              - context-managed tqdm bar that plays nicely
                              with the logging stack
    style                   - ANSI escape codes (no-op when stdout is not a TTY)
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from datetime import datetime
from typing import Iterable, Iterator, Mapping, Tuple, Union

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

# ---------------------------------------------------------------------------
# Argparse formatter
# ---------------------------------------------------------------------------


class HelpFormatter(
    argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    """Wider argparse formatter that preserves description newlines and
    appends defaults to help strings.

    Width is bumped to keep long ``--option <CHOICES>`` lines on a single row
    on standard 100-column terminals.
    """

    def __init__(self, prog, indent_increment=2, max_help_position=36, width=100):
        super().__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
        )


# ---------------------------------------------------------------------------
# Base parser  (shared flags)
# ---------------------------------------------------------------------------


def make_base_parser(
    prog: str,
    description: str,
    epilog: Union[str, None] = None,
) -> argparse.ArgumentParser:
    """Return an ArgumentParser pre-loaded with the codebase's universal flags.

    Sub-CLIs add their own arguments to the returned parser.  Universal flags:

        -v / --verbose   bump root logger to DEBUG
        -q / --quiet     drop root logger to WARNING
        --no-color       disable ANSI styling on stdout
        --dry-run        forward to commands that support it (CLI-defined)
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        epilog=epilog,
        formatter_class=HelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress everything below WARNING.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI styling on stdout (auto-disabled if not a TTY).",
    )
    return parser


# ---------------------------------------------------------------------------
# ANSI styling
# ---------------------------------------------------------------------------


class _Style:
    """Tiny ANSI helper.  Acts as a no-op when stdout is not a TTY or when
    NO_COLOR is set in the environment.
    """

    def __init__(self) -> None:
        self._enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def disable(self) -> None:
        self._enabled = False

    def _wrap(self, code: str, text: str) -> str:
        if not self._enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    # Foreground colors
    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)


style = _Style()


# ---------------------------------------------------------------------------
# Stdout helpers  (kept separate from logging so banners survive --quiet)
# ---------------------------------------------------------------------------

_BAR = "=" * 78
_RULE = "-" * 78


def print_banner(title: str, subtitle: Union[str, None] = None) -> None:
    """Print a top-of-run banner with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(_BAR)
    print(f"  {style.bold(title)}")
    if subtitle:
        print(f"  {style.dim(subtitle)}")
    print(f"  {style.dim(ts)}")
    print(_BAR)


def print_phase_separator(name: str, detail: Union[str, None] = None) -> None:
    """Print a phase-boundary line that matches logging's phase_marker style."""
    label = f"PHASE :: {style.bold(name)}"
    if detail:
        label = f"{label}  {style.dim(f'({detail})')}"
    print(_RULE)
    print(label)
    print(_RULE)


def print_summary(items: Mapping[str, object], title: str = "Summary") -> None:
    """Print a key/value summary block with aligned columns."""
    if not items:
        return
    width = max(len(k) for k in items)
    print()
    print(style.bold(title))
    for k, v in items.items():
        print(f"  {k.ljust(width)}  {v}")


def print_table(rows: Iterable[Tuple[str, ...]], headers: Tuple[str, ...]) -> None:
    """Print a simple aligned table.  ``rows`` is iterable of tuples matching
    ``headers``.  Used for status/inventory output."""
    rows = list(rows)
    cols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(str(row[i])))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(style.bold(fmt.format(*headers)))
    print(style.dim("  ".join("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*(str(c) for c in row)))


# ---------------------------------------------------------------------------
# Progress bar  (tqdm + logging redirect)
# ---------------------------------------------------------------------------

_PROGRESS_BAR_FORMAT = (
    "{desc:<24} {percentage:5.1f}%|{bar}| {n_fmt}/{total_fmt} "
    "[{elapsed}<{remaining}, {rate_fmt}]"
)


@contextlib.contextmanager
def progress(
    total: Union[int, None] = None,
    *,
    desc: str = "progress",
    unit: str = "it",
    leave: bool = True,
) -> Iterator[tqdm]:
    """Context-managed tqdm progress bar with logging interop.

    Yields a tqdm instance and routes any concurrent ``logging`` records
    through ``tqdm.write`` so log lines never overwrite the bar.  When the
    stream is not a TTY (CI, piped output) tqdm auto-disables and the helper
    becomes a near no-op.

    Args:
        total: Expected number of work units.  ``0`` is allowed and produces
               an indeterminate bar.
        desc:  Short label rendered to the left of the bar.
        unit:  Unit label (e.g. ``'group'``, ``'tab'``).
        leave: Whether to leave the completed bar on screen after exit.

    Example:
        with progress(total=len(work), desc='update', unit='group') as bar:
            for item in work:
                do_work(item)
                bar.update(1)
    """
    is_tty = sys.stderr.isatty()
    root_level = logging.getLogger().level

    bar = tqdm(
        total=total,
        desc=desc,
        unit=unit,
        leave=leave,
        dynamic_ncols=True,
        bar_format=_PROGRESS_BAR_FORMAT,
        disable=not is_tty or root_level >= logging.WARNING,
        mininterval=0.1,
    )
    try:
        with logging_redirect_tqdm():
            yield bar
    finally:
        bar.close()
