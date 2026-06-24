"""
Shoot the Sheet - ETL CLI Argument Definitions

Defines the argparse subparser for the ETL pipeline.  This module owns
ETL-specific argument definitions so that adding a new pipeline never requires
modifying the main src/cli.py.
"""

from src.core.definitions.leagues import LEAGUES
from src.core.lib.terminal import HelpFormatter


def add_subparser(subparsers) -> None:
    """Add the ETL subparser to the given subparsers collection."""
    p = subparsers.add_parser(
        "etl",
        help="ETL pipeline (extract -> transform -> load).",
        formatter_class=HelpFormatter,
    )
    p.add_argument(
        "--league",
        type=str,
        default=None,
        choices=sorted(LEAGUES),
        help="League key. If omitted, all leagues are executed consecutively in sorted order.",
    )
    p.add_argument(
        "--stage",
        type=str,
        default=None,
        choices=["ingest", "promote"],
        help="Run only a subset of the pipeline. 'ingest' = execution_start + per_league + per_identity (data into staging). 'promote' = execution_end (staging → core, cleanup). Omit for full run.",
    )
