"""
Shoot the Sheet - nba_data PBP Client

Downloads nbastats .tar.xz archives from GitHub releases on first use,
extracts CSVs, and returns normalized PBPEvent rows via the normalizer.

Exposes ``fetch_game_pbp`` as the standard entry point called by the
orchestrator's ``_maintain_pbp`` handler, and ``cleanup_season_files``
for post-processing file cleanup.
"""

import csv
import logging
import os
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from typing import Any, Dict, List

from src.definitions.pbp import PBPEvent
from src.lib.error_recorder import log_error_simple
from src.lib.rate_limiter import get_rate_limiter
from src.sources.nba_data.config import (
    ARCHIVE_DIR,
    ARCHIVE_URL_TEMPLATE,
    COL,
    EXTRACTED_DIR,
)
from src.lib.entity_resolver import EntityResolver
from src.lib.pbp_classifier import EventClassifier
from src.sources.nba_data.pbp_normalizer import normalize_game

logger = logging.getLogger(__name__)

# Cache: {csv_path: {game_id: [rows]}} to avoid re-reading the full
# season CSV for every game during backfills.
_season_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}




# ============================================================================
# PUBLIC API
# ============================================================================


def fetch_game_pbp(
    game_id: str,
    season: str,
    home_team_id: str,
    away_team_id: str,
    entity_resolver: "EntityResolver",
    classifier: "EventClassifier",
    identity: str = "nba_id",
    extracted_dir: str = EXTRACTED_DIR,
    archive_dir: str = ARCHIVE_DIR,
) -> List[PBPEvent]:
    """Load and normalize PBP events for a single game.

    Extracts the nbastats CSV from its .tar.xz archive if not already
    present, then normalizes all rows for *game_id*.

    Args:
        game_id: External game ID (e.g. ``"22400001"``).
        season: Season string in ``YYYY-YY`` format (e.g. ``"2024-25"``).
        home_team_id: External home team ID.
        away_team_id: External away team ID.
        identity: Identity code for the event's ``identity`` field.
        extracted_dir: Directory for extracted CSV files.
        archive_dir: Directory for .tar.xz archives.

    Returns:
        List of PBPEvent rows, or empty list if the file is missing
        or the game has no events.
    """
    rows = fetch_raw_rows(game_id, season, extracted_dir, archive_dir)
    if not rows:
        return []

    return normalize_game(rows, game_id, home_team_id, away_team_id, entity_resolver, classifier, identity)


def fetch_raw_rows(
    game_id: str,
    season: str,
    extracted_dir: str = EXTRACTED_DIR,
    archive_dir: str = ARCHIVE_DIR,
) -> List[Dict[str, Any]]:
    """Load raw CSV rows for a single game without normalization.

    Used by discovery to inspect raw event shapes before building
    the event catalog.  Does not require entity resolution.

    Args:
        game_id: External game ID (e.g. ``"22400001"``).
        season: Season string in ``YYYY-YY`` format.
        extracted_dir: Directory for extracted CSV files.
        archive_dir: Directory for .tar.xz archives.

    Returns:
        List of raw row dicts keyed by COL constants, or empty list.
    """
    csv_path = _ensure_csv_extracted(season, extracted_dir, archive_dir)
    if not csv_path:
        return []
    return _load_game_rows(game_id, csv_path)


def cleanup_season_files(
    season: str,
    extracted_dir: str = EXTRACTED_DIR,
    archive_dir: str = ARCHIVE_DIR,
) -> int:
    """Delete all local files for a processed season.

    Called by the orchestrator after all datasets for this season have
    been processed and coverage is upserted.  Removes the archive and
    extracted CSV directory for the given season.

    Args:
        season: Season string in ``YYYY-YY`` format.
        extracted_dir: Root directory for extracted CSV files.
        archive_dir: Root directory for .tar.xz archives.

    Returns:
        Number of files/directories deleted.
    """
    deleted = 0

    # Delete extracted CSV directory
    csv_path = _csv_path_for_season(season, extracted_dir)
    csv_dir = os.path.dirname(csv_path)
    if os.path.isdir(csv_dir):
        shutil.rmtree(csv_dir)
        deleted += 1
        logger.info("Cleaned up extracted CSV directory: %s", csv_dir)

    # Delete archive file
    archive_path = _archive_path_for_season(season, archive_dir)
    if os.path.isfile(archive_path):
        os.remove(archive_path)
        deleted += 1
        logger.info("Cleaned up archive: %s", archive_path)

    # Clear in-memory cache for this season's CSV
    _season_cache.pop(csv_path, None)

    if deleted:
        logger.info("Season %s: deleted %d file(s)/dir(s)", season, deleted)
    return deleted


def clear_cache() -> None:
    """Clear the in-memory season cache.

    Useful for test teardown or when switching between seasons
    within a long-running process.
    """
    _season_cache.clear()


# ============================================================================
# INTERNAL -- PATH HELPERS
# ============================================================================


def _season_dir_name(season: str) -> str:
    """Convert season string to nbastats directory name.

    ``"2024-25"`` -> ``"nbastats_2024"``
    """
    start_year = season[:4]
    return f"nbastats_{start_year}"


def _csv_path_for_season(season: str, extracted_dir: str) -> str:
    """Build the full path to an extracted season CSV."""
    dir_name = _season_dir_name(season)
    return os.path.join(extracted_dir, dir_name, f"{dir_name}.csv")


def _archive_path_for_season(season: str, archive_dir: str) -> str:
    """Build the full path to a season's .tar.xz archive."""
    dir_name = _season_dir_name(season)
    return os.path.join(archive_dir, f"{dir_name}.tar.xz")


# ============================================================================
# INTERNAL -- DOWNLOAD + EXTRACTION
# ============================================================================


def _ensure_csv_extracted(
    season: str,
    extracted_dir: str,
    archive_dir: str,
) -> str:
    """Ensure the season CSV exists, downloading + extracting if needed.

    Uses atomic extraction: writes to a temporary directory, then
    renames on success.  Stale temp directories from prior crashes
    are cleaned up automatically.

    Returns the path to the CSV, or empty string if the data cannot
    be acquired.
    """
    csv_path = _csv_path_for_season(season, extracted_dir)
    if os.path.isfile(csv_path):
        return csv_path

    # Clean up stale temp directory from a prior crash
    csv_dir = os.path.dirname(csv_path)
    tmp_dir = csv_dir + ".tmp"
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir)

    archive_path = _archive_path_for_season(season, archive_dir)
    if not os.path.isfile(archive_path):
        archive_path = _download_archive(season, archive_dir)
        if not archive_path:
            return ""

    # Atomic extraction: write to temp dir, then rename on success
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:xz") as tar:
            # filter="data" prevents path traversal (Python 3.12+)
            if sys.version_info >= (3, 12):
                tar.extractall(path=tmp_dir, filter="data")
            else:
                tar.extractall(path=tmp_dir)
        logger.info("Extracted %s -> %s", archive_path, tmp_dir)
    except (tarfile.TarError, OSError) as exc:
        log_error_simple(
            "maintain_pbp",
            f"Failed to extract {archive_path}",
            exc_info=exc,
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return ""

    # Atomic rename: temp dir -> final dir
    try:
        os.rename(tmp_dir, csv_dir)
    except OSError as exc:
        log_error_simple(
            "maintain_pbp",
            f"Failed to rename {tmp_dir} -> {csv_dir}",
            exc_info=exc,
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return ""

    return csv_path if os.path.isfile(csv_path) else ""


def _download_archive(season: str, archive_dir: str) -> str:
    """Download a season archive from GitHub releases.

    Uses the shared rate limiter for throttling and retry logic.
    The rate limiter handles retries with linear backoff per its
    configuration in rate_limits.py (nba_data: 3 retries, 10s base).

    Returns the local path to the downloaded archive, or empty string
    on failure.
    """
    start_year = season[:4]
    url = ARCHIVE_URL_TEMPLATE.format(start_year=start_year)
    dir_name = _season_dir_name(season)
    dest = os.path.join(archive_dir, f"{dir_name}.tar.xz")

    os.makedirs(archive_dir, exist_ok=True)

    rate_limiter = get_rate_limiter("nba_data")

    def _do_download() -> str:
        """Single download attempt using urlopen + streaming write."""
        with urllib.request.urlopen(url, timeout=rate_limiter.get_timeout()) as resp:
            with open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        return dest

    try:
        result = rate_limiter.with_retry(_do_download)
        if result and os.path.isfile(dest):
            logger.info("Downloaded %s", dest)
            return dest
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        log_error_simple(
            "maintain_pbp",
            f"Failed to download {url} after retries",
            exc_info=exc,
        )
        if os.path.isfile(dest):
            os.remove(dest)

    return ""


# ============================================================================
# INTERNAL -- CSV LOADING
# ============================================================================


def _load_game_rows(
    game_id: str,
    csv_path: str,
) -> List[Dict[str, Any]]:
    """Load CSV rows for a single game from the season file.

    Reads the full season CSV once and indexes by game_id.  Subsequent
    calls for the same season hit an in-memory cache.
    """
    if csv_path in _season_cache:
        return _season_cache[csv_path].get(game_id, [])

    indexed: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                gid = str(row.get(COL["GAME_ID"], ""))
                indexed.setdefault(gid, []).append(row)
    except (csv.Error, UnicodeDecodeError, OSError) as exc:
        log_error_simple(
            "maintain_pbp",
            f"Failed to read nbastats CSV {csv_path}",
            exc_info=exc,
        )
        _season_cache[csv_path] = {}
        return []

    # Sort each game's rows by EVENTNUM for chronological order
    for rows in indexed.values():
        rows.sort(key=lambda r: int(r.get(COL["EVENTNUM"], 0)))

    _season_cache[csv_path] = indexed
    rows = indexed.get(game_id, [])
    if not rows:
        logger.debug("No rows for game %s in %s", game_id, csv_path)
    return rows
