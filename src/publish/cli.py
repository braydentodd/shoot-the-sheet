"""
Shoot the Sheet - Publish CLI Argument Definitions

Defines the argparse subparser for the publish pipeline.  This module owns
publish-specific argument definitions so that adding a new pipeline never requires
modifying the main src/cli.py.
"""

from src.core.definitions.leagues import LEAGUES
from src.core.lib.terminal import HelpFormatter
from src.publish.definitions.destinations import DESTINATIONS
from src.publish.definitions.stats import STAT_RATES


def add_subparser(subparsers) -> None:
    """Add the publish subparser to the given subparsers collection."""
    p = subparsers.add_parser(
        "publish",
        help="Publish league data to destination (default: Google Sheets).",
        formatter_class=HelpFormatter,
    )
    p.add_argument(
        "--destination",
        choices=sorted(DESTINATIONS.keys()),
        default="google_sheets",
        help="Destination to publish to.",
    )
    p.add_argument(
        "--league",
        choices=sorted(LEAGUES),
        required=True,
        help="League to sync.",
    )
    p.add_argument(
        "--sheet",
        metavar="NAME",
        default=None,
        help='Sync this sheet first (team abbr like "BOS", or "all_players" / "all_teams").',
    )
    p.add_argument(
        "--stat-rate",
        choices=sorted(STAT_RATES),
        default="per_poss",
        help="Default visible stat rate.",
    )
    p.add_argument(
        "--historical-timeframe",
        type=int,
        choices=[1, 3, 5],
        default=3,
        help="Number of previous seasons to include in historical sections.",
    )
    p.add_argument(
        "--show-advanced",
        action="store_true",
        help="Render advanced stat columns visible by default.",
    )
    p.add_argument(
        "--data-only",
        action="store_true",
        help="Fast sync: skip structural formatting, only update data + colors.",
    )
    p.add_argument(
        "--export-config",
        action="store_true",
        help="Export the Apps Script config JS file and exit (Google Sheets only).",
    )
    p.add_argument(
        "--skip-config-export",
        action="store_true",
        help="Skip config build/export and clasp push (Google Sheets only).",
    )
