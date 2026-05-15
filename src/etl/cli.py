"""
The Glass - ETL CLI Argument Definitions

Defines the argparse subparser for the ETL pipeline.  This module owns
ETL-specific argument definitions so that adding a new pipeline never requires
modifying the main src/cli.py.
"""

from src.core.lib.terminal import HelpFormatter
from src.core.definitions.leagues import LEAGUES
from src.etl.orchestrator import VALID_PHASES


def add_subparser(subparsers) -> None:
    """Add the ETL subparser to the given subparsers collection."""
    p = subparsers.add_parser(
        'etl',
        help='ETL pipeline (extract -> transform -> load).',
        formatter_class=HelpFormatter,
        epilog=(
            "Phases:\n"
            "  full        full league run\n"
            "  discover    profile rows for the current season\n"
            "  rosters     league/team and team/player roster links\n"
            "  backfill    stats for every retained season\n"
            "  update      stats for the current season only\n"
            "  prune       per-league retention pruning\n"
            "  orphan      cross-league orphan profile sweep"
        ),
    )
    p.add_argument(
        '--league', type=str, default=None, choices=sorted(LEAGUES),
        help='League key. Required for every phase except "orphan".',
    )
    p.add_argument(
        '--phase', type=str, default='full', choices=sorted(VALID_PHASES),
        help='ETL phase to run.',
    )
    p.add_argument(
        '--season', type=str, default=None,
        help="Season label (e.g. 2024-25). Defaults to the league's current season.",
    )
    p.add_argument(
        '--season-type', type=str, default='rs', choices=['rs', 'po', 'pi'],
        help='Season type code.',
    )
    p.add_argument(
        '--entity', type=str, default='all', choices=['player', 'team', 'all'],
        help='Limit to one entity type.',
    )
