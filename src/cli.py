# ruff: noqa: E402  -- load_dotenv() must run before src.* imports that read os.getenv at module load.
"""
Shoot the Sheet - Unified CLI

Single entry point for all pipeline commands.  Dispatches to ETL or
publish via subcommands so that both share the same base flags
(--verbose, --quiet, --no-color) while retaining their own distinct
arguments.

Usage:
    python -m src.cli etl --league nba
    python -m src.cli etl --league nba --phase upsert
    python -m src.cli etl --league nba --phase prune
    python -m src.cli publish --league nba
    python -m src.cli publish --league nba --view BOS --stat-rate per_minute
    python -m src.cli publish --league nba --export-config

Subcommand phases (etl):
    full        runs upsert and prune in sequence (default)
    upsert      stage and match entities, backfill and update stats
    prune       retention stats pruning and orphan profiles sweep
"""

from dotenv import load_dotenv

load_dotenv()

import logging
import sys

from src.core.lib.logging import setup_logging
from src.core.lib.terminal import (
    HelpFormatter,
    make_base_parser,
    print_banner,
    print_summary,
)
from src.etl.cli import add_subparser as add_etl_subparser
from src.etl.orchestrator import run_etl
from src.publish.cli import add_subparser as add_publish_subparser
from src.publish.orchestrator import run_publish

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def _build_parser():
    root = make_base_parser(
        prog="python -m src.cli",
        description="Shoot the Sheet -- data pipeline CLI.",
    )
    root.formatter_class = HelpFormatter
    subparsers = root.add_subparsers(dest="pipeline", metavar="PIPELINE")
    subparsers.required = True
    add_etl_subparser(subparsers)
    add_publish_subparser(subparsers)
    return root


# ---------------------------------------------------------------------------
# Dispatch handlers
# ---------------------------------------------------------------------------


def _run_etl(args) -> int:
    from src.etl.lib.config_validation import validate_all

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


def _run_publish(args) -> int:
    from src.publish.destinations.google_sheets.config_exporter import export_config
    from src.publish.lib.config_validation import validate_all

    league = args.league.lower()
    historical_config = {"mode": "seasons", "value": args.historical_timeframe}
    destination = args.destination

    print_banner(
        "Shoot the Sheet -- Publish",
        f"league={league}  stat_rate={args.stat_rate}  data_only={args.data_only}  destination={destination}",
    )
    print_summary(
        {
            "league": league,
            "stat_rate": args.stat_rate,
            "priority_sheet": args.sheet or "(none)",
            "historical_seasons": args.historical_timeframe,
            "data_only": args.data_only,
            "show_advanced": args.show_advanced,
            "export_config_only": args.export_config,
            "destination": destination,
        },
        title="Run parameters",
    )

    try:
        validate_all()
    except RuntimeError as exc:
        logger.error("Config validation failed: %s", exc)
        return 2

    # Apps Script config export is Google Sheets-specific
    if args.export_config and not args.skip_config_export:
        if destination != "google_sheets":
            logger.error(
                "--export-config is only supported for google_sheets destination"
            )
            return 2
        path = export_config(league)
        logger.info("Config exported to %s", path)
        return 0

    try:
        run_publish(
            league=league,
            stat_rate=args.stat_rate,
            show_advanced=args.show_advanced,
            historical_config=historical_config,
            data_only=args.data_only,
            priority_sheet=args.sheet,
            config_export=not args.skip_config_export,
            destination=destination,
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception:
        logger.exception("Publish run failed.")
        return 1
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    if args.pipeline == "etl":
        return _run_etl(args)
    return _run_publish(args)


if __name__ == "__main__":
    sys.exit(main())
