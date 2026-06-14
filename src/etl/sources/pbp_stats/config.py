"""
Shoot the Sheet - PBP Stats Source Configuration

Pure data definitions for the ``pbp_stats`` source: season-type mapping,
rate limits, and field-name mappings.

Season types use canonical keys (e.g. ``regular_season``, ``playoffs``)
that are shared across sources.  Each entry carries a ``wire_name``
(what the API expects as the parameter value).

Dataset metadata lives in the unified registry
(:mod:`src.etl.definitions.datasets`).  This module is purely about
how to talk to the source itself.
"""

from typing import Any, Dict, TypedDict, Union


class ApiConfigDef(TypedDict):
    base_url: str
    max_consecutive_failures: int


class SeasonTypeDef(TypedDict):
    wire_name: str
    min_season: Union[str, None]


# ==========================================================================
# RATE LIMITS
# ==========================================================================

RATE_LIMITS: Dict[str, Union[float, int]] = {
    "requests_per_second": 0.5,
    "max_retries": 3,
    "backoff_base": 30,
    "timeout_default": 30,
    "timeout_bulk": 120,
    "max_consecutive_failures": 5,
}


# ==========================================================================
# SEASON TYPES
# ==========================================================================

SEASON_TYPES: Dict[str, SeasonTypeDef] = {
    "regular_season": {
        "wire_name": "Regular Season",
        "min_season": None,
    },
    "playoffs": {
        "wire_name": "Playoffs",
        "min_season": None,
    },
    "play_in": {
        "wire_name": "Play In Tournament",
        "min_season": "2020-21",
    },
    "showcase": {
        "wire_name": "Showcase Cup",
        "min_season": "2022-23",
    },
}


# ==========================================================================
# API OPERATIONAL SETTINGS
# ==========================================================================

API_CONFIG: ApiConfigDef = {
    "base_url": "https://api.pbpstats.com",
    "max_consecutive_failures": 5,
}


# ==========================================================================
# API FIELD NAME MAPPINGS
# ==========================================================================

API_FIELD_NAMES: Dict[str, Dict[str, Any]] = {
    "entity_id": {"player": "EntityId", "team": "TeamId"},
    "entity_name": {"player": "Name", "team": "Name"},
    "special_ids": {},
    "id_aliases": {"TeamId": ["EntityId"], "EntityId": ["TeamId"]},
}
