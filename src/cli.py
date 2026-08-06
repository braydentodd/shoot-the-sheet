"""
Shoot the Sheet - ETL CLI

Entry point for ETL pipeline and PBP discovery.

Usage:
    python -m src.cli etl --league nba
    python -m src.cli etl --league nba --stage ingest
    python -m src.cli discover-pbp nba_id.pbp_stats
    python -m src.cli discover-pbp nba_id.pbp_stats --season 2024-25
    python -m src.cli discover-pbp
"""

from dotenv import load_dotenv

load_dotenv()

import logging
import sys

from src.definitions.leagues import LEAGUES
from src.lib.console_logger import setup_logging
from src.lib.error_recorder import log_error
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
    """Build argument parser with subcommands for ETL and discovery."""
    parser = make_base_parser(
        prog="python -m src.cli",
        description="Shoot the Sheet -- ETL pipeline",
    )
    parser.formatter_class = HelpFormatter

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
    )

    # ── etl ────────────────────────────────────────────────────────────
    etl = subparsers.add_parser(
        "etl",
        help="Run the ETL pipeline",
        formatter_class=HelpFormatter,
    )
    etl.add_argument(
        "--league",
        type=str,
        default=None,
        choices=sorted(LEAGUES),
        help="League key. If omitted, all leagues are executed consecutively.",
    )
    etl.add_argument(
        "--stage",
        type=str,
        default=None,
        choices=["ingest", "promote"],
        help="Run only a subset of the pipeline. "
             "'ingest' = data into staging. "
             "'promote' = staging to core + cleanup. "
             "Omit for full run.",
    )

    # ── discover-pbp ───────────────────────────────────────────────────
    discover = subparsers.add_parser(
        "discover-pbp",
        help="Discover PBP event types from raw source data",
        formatter_class=HelpFormatter,
    )
    discover.add_argument(
        "target",
        nargs="?",
        default="__all__",
        metavar="IDENTITY.DATASET",
        help="Dataset to discover from (e.g. nba_id.pbp_stats). "
             "If omitted, discovers all PBP datasets.",
    )
    discover.add_argument(
        "--season",
        type=str,
        default=None,
        help="Limit discovery to a single season (e.g. 2024-25).",
    )

    return parser


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _run_etl(args) -> int:
    """Run the ETL pipeline."""
    from src.lib.config_validation import validate_all

    print_banner(
        "Shoot the Sheet -- ETL",
        f"league={args.league or 'all'} stage={args.stage or 'full'}",
    )
    print_summary(
        {"league": args.league or "all", "stage": args.stage or "full"},
        title="Run parameters",
    )

    try:
        validate_all()
    except RuntimeError as exc:
        logger.error("Config validation failed: %s", exc)
        return 2

    try:
        run_etl(league_code=args.league, stage=args.stage)
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception:
        logger.exception("ETL run failed.")
        try:
            log_error(
                phase="main",
                message="ETL run failed at top level -- see traceback above",
            )
        except (ConnectionError, OSError, RuntimeError) as exc:
            logger.debug("log_error failed: %s", exc)
        return 1


def _run_discovery(args) -> int:
    """Run PBP event discovery."""
    from src.definitions.leagues import LEAGUES
    from src.lib.pbp_discovery import discover
    from src.lib.postgres import db_connection
    from src.lib.schema_builder import bootstrap_schema

    # Ensure schema exists before discovery
    for league_code in LEAGUES:
        with db_connection() as conn:
            bootstrap_schema(league_code, conn=conn)

    target = args.target
    if target == "__all__":
        from src.definitions.datasets import DATASETS
        targets = []
        for identity, datasets in DATASETS.items():
            for ds_name, ds_cfg in datasets.items():
                if ds_cfg.get("phase") == "maintain_pbp":
                    targets.append((identity, ds_name))
        if not targets:
            logger.error("No PBP datasets found in config.")
            return 1
    else:
        parts = target.split(".", 1)
        if len(parts) != 2:
            logger.error(
                "Invalid target format. Expected IDENTITY.DATASET, got %r",
                target)
            return 1
        targets = [(parts[0], parts[1])]

    total_new = 0
    for identity_code, dataset_name in targets:
        logger.info("Discovering events for %s.%s ...", identity_code, dataset_name)
        try:
            with db_connection() as conn:
                summary = discover(
                    conn,
                    identity_code=identity_code,
                    dataset_name=dataset_name,
                    season=args.season,
                )
            logger.info(
                "%s.%s: %d games, %d events, %d new entries, %.1f%% classified",
                identity_code, dataset_name,
                summary["games_processed"], summary["total_events"],
                summary["new_entries"], summary["classified_pct"],
            )
            total_new += summary["new_entries"]
        except Exception:
            logger.exception(
                "Discovery failed for %s.%s", identity_code, dataset_name)
            return 1

    logger.info(
        "Discovery complete. %d new event types added across %d dataset(s). "
        "Review core.pbp_events and set handling to a PBPEventType or 'ignore'.",
        total_new, len(targets))
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Dispatch to the appropriate subcommand."""
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if args.command == "discover-pbp":
        return _run_discovery(args)
    # Default: etl (also handles explicit "etl" and missing subcommand)
    return _run_etl(args)


if __name__ == "__main__":
    sys.exit(main())
