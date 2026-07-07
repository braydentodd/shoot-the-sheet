# ruff: noqa: E402  -- load_dotenv() must run before src.* imports that read os.getenv at module load.
"""
Shoot the Sheet - ETL CLI

Entry point for ETL pipeline.

Usage:
    python -m src.cli --league nba
    python -m src.cli --league nba --stage full
"""

from dotenv import load_dotenv

load_dotenv()

import logging
import sys

from src.definitions.leagues import LEAGUES
from src.lib.console_logger import setup_logging
from src.lib.terminal import (
    HelpFormatter,
    make_base_parser,
    print_banner,
    print_summary,
)
from src.orchestrator import run_etl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser():
    """Build argument parser for ETL CLI."""
    parser = make_base_parser(
        prog="python -m src.cli",
        description="Shoot the Sheet -- ETL pipeline",
    )
    parser.formatter_class = HelpFormatter

    parser.add_argument(
        "--league",
        type=str,
        default=None,
        choices=sorted(LEAGUES),
        help="League key. If omitted, all leagues are executed consecutively in sorted order.",
    )
    parser.add_argument(
        "--stage",
        type=str,
        default=None,
        choices=["ingest", "promote"],
        help="Run only a subset of the pipeline. 'ingest' = execution_start + per_league + per_identity (data into staging). 'promote' = execution_end (staging → intermediate → core, cleanup). Omit for full run.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run ETL pipeline."""
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    from src.lib.config_validation import validate_all

    print_banner(
        "Shoot the Sheet -- ETL",
        f"league={args.league or 'all'} stage={args.stage or 'full'}",
    )
    print_summary(
        {
            "league": args.league or "all",
            "stage": args.stage or "full",
        },
        title="Run parameters",
    )

    try:
        validate_all()
    except RuntimeError as exc:
        logger.error("Config validation failed: %s", exc)
        return 2

    try:
        run_etl(
            league_code=args.league,
            stage=args.stage,
        )
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception:
        logger.exception("ETL run failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
