"""
Shoot the Sheet - Centralized CLI Helpers

Shared argparse pieces and stdout-formatting helpers used by every CLI entry
point.  Goal: consistent look-and-feel across ETL runs.

Provides:
    HelpFormatter    - widened argparse formatter (uniform metavars)
    make_base_parser - returns an ArgumentParser pre-loaded with the
                       --verbose / --quiet flags
    print_banner     - top-of-run banner (timestamp + title)
    print_summary    - aligned key/value summary block
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Mapping, Union

# ---------------------------------------------------------------------------
# Argparse formatter
# ---------------------------------------------------------------------------


class HelpFormatter(
    argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    """Wider argparse formatter that preserves description newlines and
    appends defaults to help strings.
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
    """Return an ArgumentParser pre-loaded with shared flags.

    Sub-CLIs add their own arguments to the returned parser.

        -v / --verbose   bump root logger to DEBUG
        -q / --quiet     drop root logger to WARNING
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
    return parser


# ---------------------------------------------------------------------------
# Stdout helpers
# ---------------------------------------------------------------------------

_BAR = "=" * 78


def print_banner(title: str, subtitle: Union[str, None] = None) -> None:
    """Print a top-of-run banner with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(_BAR)
    print(f"  {title}")
    if subtitle:
        print(f"  {subtitle}")
    print(f"  {ts}")
    print(_BAR)


def print_summary(items: Mapping[str, object], title: str = "Summary") -> None:
    """Print a key/value summary block with aligned columns."""
    if not items:
        return
    width = max(len(k) for k in items)
    print()
    print(title)
    for k, v in items.items():
        print(f"  {k.ljust(width)}  {v}")
