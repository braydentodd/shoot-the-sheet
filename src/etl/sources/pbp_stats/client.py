"""
Shoot the Sheet - PBP Stats Client

Wraps pbpstats.com public API endpoints behind the same fetcher contract used
by the ETL execution engine.
"""

import logging
from typing import Any, Callable, Dict, List, Union

import requests

from src.core.definitions.leagues import LEAGUES
from src.core.lib.rate_limiter import get_rate_limiter
from src.core.lib.season_resolver import format_season_param
from src.etl.definitions.datasets import DATASETS
from src.etl.lib.source_resolver import (
    get_source_league_id,
    get_source_league_season_param_format,
)
from src.etl.sources.pbp_stats.config import API_CONFIG

logger = logging.getLogger(__name__)


def _extract_rows(
    payload: Dict[str, Any], is_on_off: bool = False
) -> List[Dict[str, Any]]:
    """Normalize known pbpstats payload shapes into a list of row dicts."""
    rows = payload.get("multi_row_table_data")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]

    rows = payload.get("results")
    if isinstance(rows, list):
        if is_on_off and rows and "Stat" in rows[0]:
            return _transform_on_off_results(rows)
        return [row for row in rows if isinstance(row, dict)]

    single_row = payload.get("single_row_table_data")
    if isinstance(single_row, dict):
        return [single_row]

    return []


def _transform_on_off_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform on-off results from stat-per-row to single row with all stats."""
    if not results:
        return []

    row = {}
    for stat_entry in results:
        stat_name = stat_entry.get("Stat", "")
        on_value = stat_entry.get("On")
        off_value = stat_entry.get("Off")
        if stat_name and on_value is not None:
            row[f"{stat_name} - On"] = on_value
        if stat_name and off_value is not None:
            row[f"{stat_name} - Off"] = off_value

    return [row] if row else []


def _to_result_set(
    rows: List[Dict[str, Any]],
    result_set_name: str,
) -> Dict[str, Any]:
    """Convert row dicts into NBA-style ``resultSets`` payload."""
    if not rows:
        return {
            "resultSets": [
                {
                    "name": result_set_name,
                    "headers": [],
                    "rowSet": [],
                },
            ],
        }

    headers = list(rows[0].keys())
    row_set = [[row.get(header) for header in headers] for row in rows]
    return {
        "resultSets": [
            {
                "name": result_set_name,
                "headers": headers,
                "rowSet": row_set,
            },
        ],
    }


def _build_dataset_params(
    league_key: str,
    season_end_year: int,
    season_type_name: str,
    entity: str,
    extra_params: Union[Dict[str, Any], None] = None,
    wire: Union[Dict[str, Any], None] = None,
    endpoint: Union[str, None] = None,
) -> Dict[str, Any]:
    """Build query params for pbpstats requests."""
    league_cfg = LEAGUES[league_key]
    source_format = get_source_league_season_param_format("pbp_stats", league_key)
    param_format = wire.get("season_param_format", source_format)
    season_label = format_season_param(
        season_end_year, param_format, league_cfg["season_format"]
    )

    params: Dict[str, Any] = {
        "Season": season_label,
        "SeasonType": season_type_name,
    }

    if extra_params:
        for k, v in extra_params.items():
            if k == "team_id":
                params["TeamId"] = v
            elif k == "player_id":
                params["PlayerId"] = v
            else:
                params[k] = v

    # get-on-off endpoint doesn't use Type parameter
    if endpoint != "get-on-off" and "Type" not in params:
        params["Type"] = "Team" if entity == "team" else "Player"

    return params


def make_fetcher(
    league_key: str, season_end_year: int, season_type_name: str, entity: str
) -> Callable:
    """Create an API fetcher closure for pbpstats datasets."""
    rate_limiter = get_rate_limiter("pbp_stats")

    def fetch(
        dataset: str,
        extra_params: Union[Dict[str, Any], None] = None,
    ) -> Union[Dict[str, Any], None]:
        ds_cfg = DATASETS.get("pbp_stats", {}).get(dataset)
        if ds_cfg is None:
            logger.warning("Unknown pbp_stats dataset: %s", dataset)
            return None

        wire = ds_cfg.get("source_mapping", {})
        endpoint = wire.get("endpoint", "")
        url_suffix = wire.get("url_suffix") or ""
        source_league_id = get_source_league_id("pbp_stats", league_key)
        url = f"{API_CONFIG['base_url']}/{endpoint}/{source_league_id}{url_suffix}"
        params = _build_dataset_params(
            league_key,
            season_end_year,
            season_type_name,
            entity,
            extra_params,
            wire=wire,
            endpoint=endpoint,
        )

        def _call() -> Dict[str, Any]:
            response = requests.get(
                url,
                params=params,
                timeout=rate_limiter.get_timeout(is_bulk=True),
            )
            response.raise_for_status()

            payload = response.json()
            if isinstance(payload, dict) and payload.get("detail"):
                raise RuntimeError(f"PBP API error for {dataset}: {payload['detail']}")

            is_on_off = endpoint == "get-on-off"
            rows = _extract_rows(payload, is_on_off=is_on_off)
            return _to_result_set(rows, wire.get("result_set", "Results"))

        return rate_limiter.with_retry(_call)

    return fetch
