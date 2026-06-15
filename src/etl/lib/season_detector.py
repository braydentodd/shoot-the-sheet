"""Shoot the Sheet - Season Activity Detector

Checks whether a league is currently "in season" by calling the
``season_detector`` dataset defined in the league's config and looking
for game activity within the last ``GAME_LOOKBACK_DAYS`` days.

Architecture:
  Each league declares a ``season_detector`` dataset name in
  :data:`src.core.definitions.leagues.LEAGUES`.  The detector uses the
  source configured for that dataset (via
  :data:`src.etl.definitions.datasets.DATASETS`) to retrieve recent
  game records.  If any games are found within the lookback window,
  the league is considered active and the detector returns which
  source-specific season types were present among those games.

The ETL pipeline uses this to decide:
  - Whether to refresh stats columns (only when games were found).
  - Whether to refresh profile / roster columns (always).
  - Which season_types to populate coverage / staging for.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from src.core.definitions.leagues import LEAGUES
from src.core.lib.season_resolver import parse_season_end_year
from src.etl.definitions.datasets import DATASETS
from src.etl.definitions.execution import GAME_LOOKBACK_DAYS
from src.etl.lib.source_resolver import get_source_league_id

logger = logging.getLogger(__name__)

# Sentinel for "no recent activity — skip stats refresh".
_NO_ACTIVITY: List[str] = []


def _recent_game_dates(lookback_days: int) -> Optional[str]:
    """Return a date range string covering *lookback_days* days from today.

    Returns ``None`` if something goes wrong.
    """
    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)
    return f"{start.isoformat()} - {end.isoformat()}"


def _check_via_nba_api(
    league_key: str,
    dataset_name: str,
    season: str,
    identity_key: str = "nba_id",
) -> List[str]:
    """Detect recent activity via an nba_api dataset.

    Uses the dataset's configured endpoint with date filters
    restricting results to the current lookback window.
    Returns the set of season-type codes found among recent games,
    or an empty list if no games were found.
    """
    from src.core.lib.rate_limiter import get_rate_limiter
    from src.etl.sources.nba_api.client import (
        build_dataset_params,
        create_api_call,
        load_dataset_class,
        with_retry,
    )

    rate_limiter = get_rate_limiter("nba_api")
    league_cfg = LEAGUES[league_key]
    season_end_year = parse_season_end_year(season, league_cfg["season_format"])

    ds_cfg = DATASETS.get(identity_key, {}).get(dataset_name)
    if not ds_cfg:
        logger.debug(
            "No season_detector dataset config for %s/%s; assuming active",
            league_key,
            dataset_name,
        )
        return _all_canonical_keys(league_cfg)

    wire = ds_cfg.get("source_mapping", {})
    class_name = wire.get("class_name", dataset_name)
    DatasetClass = load_dataset_class(class_name)
    if DatasetClass is None:
        logger.debug("Cannot load dataset class for season detector: %s", class_name)
        return _all_canonical_keys(league_cfg)

    date_range = _recent_game_dates(GAME_LOOKBACK_DAYS)
    if date_range is None:
        return _all_canonical_keys(league_cfg)

    params = build_dataset_params(
        dataset_name,
        league_key,
        season_end_year,
        "Regular Season",
        "player",
    )

    # Narrow to the lookback window when the endpoint supports it.
    params["date_from_nullable"] = date_range.split(" - ")[0]
    params["date_to_nullable"] = date_range.split(" - ")[1]

    try:
        api_call = create_api_call(
            DatasetClass,
            params,
            dataset_name=dataset_name,
            rate_limiter=rate_limiter,
        )
        result = with_retry(api_call, rate_limiter, max_retries=1)
    except Exception:
        logger.debug(
            "Season detector call failed for %s/%s; assuming active",
            league_key,
            dataset_name,
            exc_info=True,
        )
        return _all_canonical_keys(league_cfg)

    if not result:
        return _NO_ACTIVITY

    active_types: Set[str] = set()
    for rs in result.get("resultSets", []):
        rows = rs.get("rowSet")
        if not rows:
            continue
        headers = rs.get("headers", [])
        season_type_idx = None
        for candidate in ("SEASON_TYPE", "Game_Type"):
            if candidate in headers:
                season_type_idx = headers.index(candidate)
                break

        for row in rows:
            if season_type_idx is not None:
                raw_st = row[season_type_idx]
                if raw_st:
                    active_types.add(raw_st.lower())
            else:
                active_types.add("rs")

    if not active_types:
        return _NO_ACTIVITY

    # Map raw source season types to the league's declared canonical keys.
    league_season_types = set()
    for keys in league_cfg["season_types"].values():
        league_season_types.update(keys)

    mapped: List[str] = []
    for raw in sorted(active_types):
        if raw in league_season_types:
            mapped.append(raw)
        else:
            logger.debug(
                "Unmapped season type '%s' in detector result for %s",
                raw,
                league_key,
            )

    if not mapped:
        return _NO_ACTIVITY

    logger.info(
        "Season detector %s: active types=%s (lookback=%dd)",
        league_key,
        mapped,
        GAME_LOOKBACK_DAYS,
    )
    return mapped


def _check_via_pbp_stats(
    league_key: str,
    dataset_name: str,
    season: str,
    identity_key: str = "nba_id",
) -> List[str]:
    """Detect recent activity via a pbpstats dataset.

    Returns active season types or empty list.
    """
    from src.core.lib.rate_limiter import get_rate_limiter
    from src.etl.sources.pbp_stats.config import API_CONFIG

    league_cfg = LEAGUES[league_key]
    source_league_id = get_source_league_id("pbp_stats", league_key)
    date_range = _recent_game_dates(GAME_LOOKBACK_DAYS)

    import requests

    ds_cfg = DATASETS.get(identity_key, {}).get(dataset_name)
    if not ds_cfg:
        return _all_canonical_keys(league_cfg)

    wire = ds_cfg.get("source_mapping", {})
    endpoint = wire.get("endpoint", "")
    url = f"{API_CONFIG['base_url']}/{endpoint}/{source_league_id}"

    try:
        response = requests.get(
            url,
            params={
                "Season": season,
                "SeasonType": "Regular Season",
                "DateFrom": date_range.split(" - ")[0] if date_range else "",
                "DateTo": date_range.split(" - ")[1] if date_range else "",
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.debug("PBP season detector failed for %s", league_key, exc_info=True)
        return _all_canonical_keys(league_cfg)

    rows = payload.get("multi_row_table_data") or payload.get("results") or []
    if not rows:
        return _NO_ACTIVITY

    # Infer active types from the response
    league_season_types = set()
    for keys in league_cfg["season_types"].values():
        league_season_types.update(keys)

    active_types: Set[str] = set()
    for row in rows:
        st = (row.get("SeasonType") or "").lower()
        if st in league_season_types:
            active_types.add(st)

    if not active_types:
        return _NO_ACTIVITY

    mapped = list(active_types)
    logger.info(
        "Season detector %s (pbp): active types=%s (lookback=%dd)",
        league_key,
        mapped,
        GAME_LOOKBACK_DAYS,
    )
    return mapped


def detect_active_season_types(
    league_key: str,
    season: Optional[str] = None,
) -> List[str]:
    """Return the source season-type codes that had recent game activity.

    Hits the league's ``season_detector`` dataset and filters to games
    within the last ``GAME_LOOKBACK_DAYS`` days.

    The ``season_detector`` config value is an id-prefixed reference like
    ``"nba_id.recent_games"`` — parsed into identity key + dataset name.

    Returns:
        List of source season-type codes (e.g. ``["regular_season", "playoffs"]``)
        that appeared in the recent game data.  An empty list means no
        recent activity was detected.
    """
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league_key: {league_key}")

    from src.core.lib.leagues_resolver import get_current_season

    cfg = LEAGUES[league_key]
    all_keys = _all_canonical_keys(cfg)

    detector_ref = cfg.get("season_detector")
    if not detector_ref:
        logger.debug(
            "No season_detector configured for %s; assuming active", league_key
        )
        return all_keys

    identity_key, dataset_name = _parse_dataset_ref(detector_ref)
    active_season = season or get_current_season(league_key)

    ds_cfg = DATASETS.get(identity_key, {}).get(dataset_name)
    if not ds_cfg:
        logger.debug(
            "Season detector dataset %r not registered for %s; assuming active",
            detector_ref,
            league_key,
        )
        return all_keys

    source = ds_cfg.get("source", "nba_api")

    if source == "nba_api":
        return _check_via_nba_api(league_key, dataset_name, active_season, identity_key)
    elif source == "pbp_stats":
        return _check_via_pbp_stats(
            league_key, dataset_name, active_season, identity_key
        )
    else:
        logger.debug(
            "Unsupported source %r for season detector; assuming active", source
        )
        return all_keys


def _parse_dataset_ref(ref: str) -> tuple:
    """Parse ``"identity_key.dataset_name"`` into ``(identity_key, dataset_name)``."""
    if "." in ref:
        identity_key, dataset_name = ref.split(".", 1)
        return identity_key, dataset_name
    return "nba_id", ref


def _all_canonical_keys(cfg: dict) -> List[str]:
    """Flatten a league's ``season_types`` groups into a single list."""
    all_keys: List[str] = []
    for keys in cfg["season_types"].values():
        all_keys.extend(keys)
    return all_keys


# Backward-compatible wrapper used by the orchestrator's in_season gating.
def is_league_in_season(league_key: str, season: Optional[str] = None) -> bool:
    """Return ``True`` if ANY recent game activity was detected.

    Convenience wrapper around :func:`detect_active_season_types`.
    """
    return bool(detect_active_season_types(league_key, season))
