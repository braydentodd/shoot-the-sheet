"""
Shoot the Sheet - nba_data PBP Client

Downloads nbastats .tar.xz archives from GitHub releases on first use,
extracts CSVs, and returns normalized PBPEvent rows via the normalizer.

Exposes ``fetch_game_pbp`` as the standard entry point called by the
orchestrator's ``_maintain_pbp`` handler.
"""

import csv
import logging
import os
import tarfile
import urllib.request
from typing import Any, Dict, List

from src.definitions.pbp import PBPEvent
from src.sources.nba_data.config import (
    ARCHIVE_DIR,
    ARCHIVE_URL_TEMPLATE,
    COL,
    EXTRACTED_DIR,
)
from src.sources.nba_data.pbp_normalizer import normalize_game

logger = logging.getLogger(__name__)

# Cache: {csv_path: {game_id: [rows]}} to avoid re-reading the full
# season CSV for every game during backfills.
_season_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}


def fetch_game_pbp(
    game_id: str,
    season: str,
    home_team_id: str,
    away_team_id: str,
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
    csv_path = _ensure_csv_extracted(season, extracted_dir, archive_dir)
    if not csv_path:
        return []

    rows = _load_game_rows(game_id, csv_path)
    if not rows:
        return []

    return normalize_game(rows, game_id, home_team_id, away_team_id, identity)


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


def _ensure_csv_extracted(
    season: str,
    extracted_dir: str,
    archive_dir: str,
) -> str:
    """Ensure the season CSV exists, downloading + extracting if needed.

    Returns the path to the CSV, or empty string if the data cannot
    be acquired.
    """
    csv_path = _csv_path_for_season(season, extracted_dir)
    if os.path.isfile(csv_path):
        return csv_path

    archive_path = _archive_path_for_season(season, archive_dir)
    if not os.path.isfile(archive_path):
        archive_path = _download_archive(season, archive_dir)
        if not archive_path:
            return ""

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(path=os.path.dirname(csv_path))
        logger.info("Extracted %s -> %s", archive_path, csv_path)
    except Exception as exc:
        logger.warning("Failed to extract %s: %s", archive_path, exc)
        return ""

    return csv_path if os.path.isfile(csv_path) else ""


def _download_archive(season: str, archive_dir: str) -> str:
    """Download a season archive from GitHub releases.

    Returns the local path to the downloaded archive, or empty string
    on failure.
    """
    start_year = season[:4]
    url = ARCHIVE_URL_TEMPLATE.format(start_year=start_year)
    dir_name = _season_dir_name(season)
    dest = os.path.join(archive_dir, f"{dir_name}.tar.xz")

    os.makedirs(archive_dir, exist_ok=True)
    logger.info("Downloading %s -> %s", url, dest)
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        logger.warning("Failed to download %s: %s", url, exc)
        # Clean up partial download
        if os.path.isfile(dest):
            os.remove(dest)
        return ""

    if os.path.isfile(dest):
        logger.info("Downloaded %s", dest)
        return dest
    return ""


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
    except Exception as exc:
        logger.warning("Failed to read nbastats CSV %s: %s", csv_path, exc)
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
