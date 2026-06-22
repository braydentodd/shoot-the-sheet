"""
Shoot the Sheet - NBA API Client

Wraps the nba_api library with browser header patching, dynamic dataset
loading, retry logic, and parameter building.  Abstracts NBA-specific
HTTP concerns so the core pipeline never touches requests directly.

No classes -- all functions operate on plain data.
"""

import importlib
import inspect
import logging
import warnings
from typing import Any, Callable, Dict, Union

from src.core.definitions.leagues import LEAGUES
from src.core.lib.rate_limiter import get_rate_limiter
from src.core.lib.season_resolver import format_season_param, parse_season_end_year
from src.etl.definitions.datasets import DATASETS
from src.etl.lib.source_resolver import (
    get_source_league_id,
    get_source_league_season_param_format,
)
from src.etl.sources.nba_api.config import (
    API_CONFIG,
    REQUEST_HEADERS,
)

warnings.filterwarnings(
    "ignore",
    message="Failed to return connection to pool",
    module="urllib3",
)

logger = logging.getLogger(__name__)


# ============================================================================
# SESSION PATCHING
# ============================================================================

_session_patched = False


def _patch_nba_api_headers() -> None:
    """Apply browser-like headers to the nba_api library (idempotent)."""
    global _session_patched
    if _session_patched:
        return
    try:
        from nba_api.library import http as _base_http
        from nba_api.stats.library import http as _stats_http

        _stats_http.STATS_HEADERS = REQUEST_HEADERS
        _stats_http.NBAStatsHTTP.headers = REQUEST_HEADERS
        _stats_http.NBAStatsHTTP._session = None
        _base_http.NBAHTTP._session = None
        _session_patched = True
    except ImportError:
        logger.warning("nba_api not installed -- header patching skipped")


# ============================================================================
# DATASET CLASS LOADING
# ============================================================================

_dataset_class_cache: Dict[str, Any] = {}


def load_dataset_class(dataset_name: str) -> Union[Any, None]:
    """Dynamically import and cache an nba_api dataset class by name.

    Returns ``None`` (with a warning) if the module doesn't exist.
    """
    if dataset_name in _dataset_class_cache:
        return _dataset_class_cache[dataset_name]

    module_path = f"nba_api.stats.endpoints.{dataset_name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        logger.warning("Could not import dataset module: %s", module_path)
        return None

    # Find the dataset class: look for a class whose lowercase name matches
    cls = None
    for attr_name in dir(module):
        if attr_name.lower() == dataset_name.lower():
            candidate = getattr(module, attr_name)
            if isinstance(candidate, type):
                cls = candidate
                break

    if cls is None:
        logger.warning("No class found in %s", module_path)
        return None

    _dataset_class_cache[dataset_name] = cls
    return cls


# ============================================================================
# API CALL FACTORY
# ============================================================================


def create_api_call(
    dataset_class: Any,
    params: Dict[str, Any],
    dataset_name: str = "",
    timeout: Union[int, None] = None,
    rate_limiter: Union[Any, None] = None,
) -> Callable:
    """Build a zero-arg callable that executes an NBA API request.

    Internal params (keys starting with ``_``) are stripped before the call.
    Parameters not accepted by the dataset constructor are silently dropped.
    Returns raw JSON dict with ``resultSets``.
    """
    _patch_nba_api_headers()

    clean_params = {k: v for k, v in params.items() if not k.startswith("_")}

    # Filter to only params the dataset actually accepts
    sig = inspect.signature(dataset_class.__init__)
    accepted = set(sig.parameters.keys()) - {"self"}
    has_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if not has_kwargs:
        clean_params = {k: v for k, v in clean_params.items() if k in accepted}

    if rate_limiter:
        call_timeout = timeout or rate_limiter.get_timeout()
    else:
        call_timeout = timeout or 30

    def _call() -> Dict[str, Any]:
        result = dataset_class(**clean_params, timeout=call_timeout)
        return result.get_dict()

    return _call


# ============================================================================
# RETRY WRAPPER
# ============================================================================


def with_retry(
    func: Callable, rate_limiter: Any, max_retries: Union[int, None] = None
) -> Any:
    """Execute *func* with exponential back-off on failure using rate limiter.

    Args:
        func: Zero-arg callable to execute.
        rate_limiter: RateLimiter instance.
        max_retries: Override default max_retries from rate limiter config.

    Returns:
        The first successful result or re-raises the last exception.
    """
    return rate_limiter.with_retry(func, max_retries)


# ============================================================================
# PARAMETER BUILDER
# ============================================================================


def build_dataset_params(
    dataset_name: str,
    league_key: str,
    season_end_year: int,
    season_type_name: str,
    entity: str,
    identity_key: str = "nba_id",
    extra_params: Union[Dict[str, Any], None] = None,
) -> Dict[str, Any]:
    """Assemble the full parameter dict for an NBA API call.

    Merges standard parameters (season, league_id, per_mode, season_type)
    with dataset-specific defaults and caller-supplied overrides.

    Any key in ``source_mapping`` that is not a recognised metadata field
    (class_name, result_set, season_type_param, per_mode_param, season_param,
    endpoint) is forwarded directly as an API parameter.
    """
    ds_cfg = DATASETS.get(identity_key, {}).get(dataset_name, {})
    wire = ds_cfg.get("source_mapping", {})
    league_cfg = LEAGUES[league_key]
    source_league_id = get_source_league_id("nba_api", league_key)

    # Known meta-keys consumed by this builder; everything else in source_mapping
    # is forwarded directly as an API parameter.
    _META_KEYS = {
        "class_name",
        "result_set",
        "season_type_param",
        "per_mode_param",
        "season_param",
        "season_param_format",
        "context_measure_param",
        "endpoint",
    }

    # Season parameter format: source config > dataset override > auto-inferred
    source_format = get_source_league_season_param_format("nba_api", league_key)
    param_format = wire.get("season_param_format", source_format)

    # Season parameter — format according to source's token spec
    season_param = wire.get("season_param", "season")
    if season_param == "season_year":
        # Start year (season year) for datasets that need an integer
        start_year = (
            season_end_year - 1
            if league_cfg["season_format"] == "split_year"
            else season_end_year
        )
        params: Dict[str, Any] = {season_param: start_year}
    else:
        params: Dict[str, Any] = {
            season_param: format_season_param(
                season_end_year, param_format, league_cfg["season_format"]
            )
        }

    # Season type
    st_param = wire.get("season_type_param")
    if st_param:
        params[st_param] = season_type_name

    # Per-mode
    pm_param = wire.get("per_mode_param")
    if pm_param and pm_param in API_CONFIG:
        params[pm_param] = API_CONFIG[pm_param]

    # Context measure (e.g. for shot charts)
    cm_param = wire.get("context_measure_param")
    if cm_param and cm_param in API_CONFIG:
        params[cm_param] = API_CONFIG[cm_param]

    # League ID — add both variants; signature filtering in create_api_call
    # will keep only the one the dataset accepts.
    params["league_id"] = source_league_id
    params["league_id_nullable"] = source_league_id

    # Forward any source_mapping entries that are not known meta-keys.
    for key, value in wire.items():
        if key not in _META_KEYS:
            params[key] = value

    # Caller overrides win
    if extra_params:
        params.update(extra_params)

    return params


# ============================================================================
# FETCHER FACTORY
# ============================================================================


def make_fetcher(
    league_key: str,
    season_end_year: int,
    season_type_name: str,
    entity: str,
    identity_key: str = "nba_id",
) -> Callable:
    """Create an api_fetcher closure for the given league, season, type, and entity.

    Returns a function that accepts (dataset, extra_params) and executes
    a fully parameterized NBA API call with retry logic.
    """
    rate_limiter = get_rate_limiter("nba_api")

    def fetch(
        dataset: str, extra_params: Union[Dict[str, Any], None] = None
    ) -> Union[Dict, None]:
        ds_cfg = DATASETS.get(identity_key, {}).get(dataset, {})
        class_name = ds_cfg.get("source_mapping", {}).get("class_name", dataset)
        DatasetClass = load_dataset_class(class_name)
        if DatasetClass is None:
            return None
        full_params = build_dataset_params(
            dataset,
            league_key,
            season_end_year,
            season_type_name,
            entity,
            extra_params=extra_params or {},
        )
        api_call = create_api_call(
            DatasetClass, full_params, dataset_name=dataset, rate_limiter=rate_limiter
        )
        return with_retry(api_call, rate_limiter)

    return fetch
