import logging
from typing import Any, Dict, List, Tuple

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.datasets import DATASETS

logger = logging.getLogger(__name__)


# ============================================================================
# Dataset-level season detector discovery
# ============================================================================

def _find_season_detector_datasets(league_key: str) -> List[Tuple[str, str]]:
    """Return [(source_key, dataset_name), ...] for datasets tagged as season_detector."""
    matches: List[Tuple[str, str]] = []
    for source_key, datasets in DATASETS.items():
        for dataset_name, ds_cfg in datasets.items():
            if ds_cfg.get('role') == 'season_detector' and league_key in ds_cfg.get('leagues', []):
                matches.append((source_key, dataset_name))
    return matches


def is_league_in_season(league_key: str) -> bool:
    """Check if a league is currently 'in season' based on recent activity.

    Discovers the season_detector dataset from :data:`DATASETS`.  Delegates
    to the source client's ``check_activity`` function if one is registered;
    defaults to ``True`` if none exists.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league_key: {league_key}")

    detectors = _find_season_detector_datasets(league_key)
    if not detectors:
        logger.warning(
            "No season_detector dataset for league='%s'. Defaulting to in_season=True",
            league_key,
        )
        return True

    source_key, dataset = detectors[0]
    activity_window_days = 8

    import importlib

    try:
        client_module = importlib.import_module(f"src.etl.sources.{source_key}.client")
        if hasattr(client_module, 'check_activity'):
            return client_module.check_activity(dataset, activity_window_days)
        logger.warning(
            "season_detector not implemented for source '%s'. Defaulting to in_season=True",
            source_key,
        )
        return True
    except ImportError as e:
        logger.error("Could not import client module for source '%s': %s", source_key, e)
        return True
    except Exception as e:
        logger.error("Failed to run season_detector for '%s': %s", source_key, e)
        return True
