"""Shoot the Sheet - Season Activity Detector

Queries a ``season_detector`` dataset to find which season types had game
activity within ``GAME_LOOKBACK_DAYS``.  Used by ``current_stats_maintainer``
to decide which season types to refresh for the current season.

Datasets are discovered via the ``season_detector`` role in
:data:`src.etl.definitions.datasets.DATASETS`.

Source dispatch: ``_SEASON_DETECTORS`` maps source code → detection function.
Adding a new source requires one import + one dict entry.
"""

import logging
from typing import Any, List, Optional

from src.core.definitions.leagues import LEAGUES
from src.etl.definitions.datasets import DATASETS
from src.etl.definitions.execution import GAME_LOOKBACK_DAYS
from src.etl.sources.nba_api.client import detect_recent_games as _nba_detect_recent

logger = logging.getLogger(__name__)

_NO_ACTIVITY: List[str] = []

# Source code → detection function.
_SEASON_DETECTORS = {
    "nba_api": _nba_detect_recent,
}


# ============================================================================
# Helpers
# ============================================================================


def _all_canonical_keys(cfg: Any) -> List[str]:
    """Return the canonical season-type keys for a league."""
    return list(cfg["season_types"].keys())


# ============================================================================
# Detection
# ============================================================================


def _check_recent_games(
    identity_code: str,
    dataset_name: str,
    league_code: str,
    season: str,
) -> Optional[List[str]]:
    """Query per season type — any type with games in the lookback window
    is considered active."""
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name)
    if not ds_cfg:
        return None

    source = ds_cfg.get("source")
    detector = _SEASON_DETECTORS.get(source)

    if detector is None:
        logger.debug("No season detector for source=%r; assuming active", source)
        return None

    from src.etl.lib.source_resolver import get_source_season_type_code

    cfg = LEAGUES[league_code]
    active: List[str] = []
    lookback_days = GAME_LOOKBACK_DAYS

    for canonical_key in _all_canonical_keys(cfg):
        source_type = get_source_season_type_code(source, league_code, canonical_key)
        if not source_type:
            continue

        result = detector(
            dataset_name, league_code, season, source_type, lookback_days, identity_code
        )

        if result is None:
            logger.warning(
                "Season detector API call failed for %s/%s — assuming active",
                league_code,
                canonical_key,
            )
            active.append(canonical_key)
            continue

        for rs in result.get("resultSets", []):
            if rs.get("rowSet"):
                active.append(canonical_key)
                break

    if not active:
        logger.info(
            "Season detector %s: no recent games (lookback=%dd)",
            league_code,
            lookback_days,
        )
        return _NO_ACTIVITY

    logger.info(
        "Season detector %s: active=%s (lookback=%dd)",
        league_code,
        active,
        lookback_days,
    )
    return active


# ============================================================================
# Public API
# ============================================================================


def _parse_dataset_ref(ref: str) -> tuple:
    """Parse ``"identity_code.dataset_name"`` into ``(identity_code, dataset_name)``."""
    if "." in ref:
        identity_code, dataset_name = ref.split(".", 1)
        return identity_code, dataset_name
    return "nba_id", ref


def detect_active_season_types(
    league_code: str,
    dataset_refs: list,
    season: Optional[str] = None,
) -> List[str]:
    """Return canonical season-type keys that had recent game activity.

    *dataset_refs* is a list of ``"identity_code.dataset_name"`` strings
    built from datasets with role ``season_detector``.
    """
    if league_code not in LEAGUES:
        raise ValueError(f"Unknown league_code: {league_code}")

    from src.core.lib.leagues_resolver import get_current_season

    cfg = LEAGUES[league_code]
    all_keys = _all_canonical_keys(cfg)
    active_season = season or get_current_season(league_code)

    for ref in dataset_refs:
        identity_code, dataset_name = _parse_dataset_ref(ref)
        ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name)
        if not ds_cfg:
            continue
        result = _check_recent_games(
            identity_code,
            dataset_name,
            league_code,
            active_season,
        )
        if result is None:
            continue  # API error — try next dataset, fall back to all_keys at end
        return result  # [] or [types...]

    return all_keys


def is_league_in_season(league_code: str, season: Optional[str] = None) -> bool:
    """Return ``True`` if ANY recent game activity was detected."""
    dataset_refs = [
        f"{ic}.{ds}"
        for ic, datasets in DATASETS.items()
        for ds, ds_def in datasets.items()
        if ds_def.get("stage") == "season_detector"
    ]
    return bool(detect_active_season_types(league_code, dataset_refs, season))
