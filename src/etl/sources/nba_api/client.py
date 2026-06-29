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
from typing import Any, Callable, Dict, List, Union

from src.core.definitions.leagues import LEAGUES
from src.core.lib.rate_limiter import get_rate_limiter
from src.core.lib.season_resolver import format_season_param, parse_season_end_year
from src.etl.definitions.datasets import DATASETS
from src.etl.lib.source_resolver import (
    get_source_league_id,
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


# ============================================================================
# PARAMETER BUILDER
# ============================================================================


def build_dataset_params(
    dataset_name: str,
    league_code: str,
    season_end_year: int,
    season_type_name: str,
    identity_code: str = "nba_id",
    extra_params: Union[Dict[str, Any], None] = None,
) -> Dict[str, Any]:
    """Assemble the full parameter dict for an NBA API call.

    Merges standard parameters (season, league_id, per_mode, season_type)
    with dataset-specific defaults and caller-supplied overrides.

    Any key in ``source_mapping`` that is not a recognised metadata field
    (class_name, result_set, season_type_param, per_mode_param, season_param,
    endpoint) is forwarded directly as an API parameter.
    """
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
    wire = ds_cfg.get("source_mapping", {})
    league_cfg = LEAGUES[league_code]
    source_league_id = get_source_league_id("nba_api", league_code)

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

    # Season parameter format — per-league from dataset config.
    param_format_raw = wire.get("season_param_format")
    if isinstance(param_format_raw, dict):
        param_format = param_format_raw[league_code]
    elif isinstance(param_format_raw, str):
        param_format = param_format_raw
    else:
        param_format = "SSSS-EE"

    # Season parameter — format according to source's token spec
    season_param = wire.get("season_param", "season")
    assert isinstance(season_param, str)
    params: Dict[str, Any]
    if season_param == "season_year":
        # Start year (season year) for datasets that need an integer
        start_year = (
            season_end_year - 1
            if league_cfg["season_format"] == "split_year"
            else season_end_year
        )
        params = {season_param: start_year}
    else:
        params = {
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
        if key not in _META_KEYS and value is not None:
            params[key] = value

    # Caller overrides win
    if extra_params:
        params.update(extra_params)

    # Bridge per-entity ID params to their _nullable counterparts (like we do
    # for league_id).  The create_api_call signature filter keeps whichever
    # variant the endpoint actually accepts.
    for base in ("team_id", "player_id"):
        if base in params and f"{base}_nullable" not in params:
            params[f"{base}_nullable"] = params[base]

    return params


# ============================================================================
# Row filtering
# ============================================================================


def _apply_row_filters(
    result: Dict[str, Any],
    ds_cfg: Any,
    season_end_year: int,
) -> Dict[str, Any]:
    """Apply dataset-configured row_filters to an API response.

    Each filter declares a *field*, an *op* (``lte`` / ``gte`` / ``eq``),
    and a *value_template* that may contain ``{season_end_year}``.
    Rows that fail any filter are removed from every result set.
    """
    filters = ds_cfg.get("row_filters")
    if not filters:
        return result

    template_vars = {"season_end_year": season_end_year}

    for rs in result.get("resultSets", []):
        headers = rs.get("headers", [])
        rows = rs.get("rowSet", [])
        if not rows:
            continue

        for f in filters:
            field = f["field"]
            if field not in headers:
                continue
            idx = headers.index(field)
            op = f["op"]
            raw_value = f["value_template"]
            threshold = raw_value.format(**template_vars)
            try:
                threshold = type(rows[0][idx])(threshold)
            except (ValueError, IndexError):
                pass

            if op == "lte":
                rows = [r for r in rows if r[idx] <= threshold]
            elif op == "gte":
                rows = [r for r in rows if r[idx] >= threshold]
            elif op == "eq":
                rows = [r for r in rows if r[idx] == threshold]

        rs["rowSet"] = rows

    return result


# ============================================================================
# PBP RESPONSE NORMALIZER
# ============================================================================


def _normalize_pbp_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a playbyplayv3 response to standard PBP events and parse.

    Decomposes raw NBA actions into standard events (fg2_make, turnover,
    sub_in, etc.) with cumulative seconds, then runs the source-agnostic
    parser to produce domain resultSets.
    """
    import re

    game = raw.get("game", {})
    if not isinstance(game, dict):
        return raw
    game_id = game.get("gameId", "")
    actions = game.get("actions", [])
    if not actions:
        return {"resultSets": []}

    # Extract home/away team IDs from game metadata
    home_team_id = game.get("homeTeamId") or game.get("homeTeam", {}).get("teamId")
    away_team_id = game.get("awayTeamId") or game.get("awayTeam", {}).get("teamId")

    # Build player name -> player_id lookup for assist/block/steal parsing
    name_map: Dict[str, int] = {}
    for a in actions:
        pid = a.get("personId")
        pname = a.get("playerName") or ""
        pname_i = a.get("playerNameI") or ""
        if pid:
            if pname:
                name_map[pname.lower()] = pid
            if pname_i:
                name_map[pname_i.split(". ")[-1].lower()] = pid

    std_events: List[Dict[str, Any]] = []
    event_id = 0
    current_period = 0

    def _emit(ev_type: str, tid: int | None, pid: int | None, secs: float):
        nonlocal event_id
        event_id += 1
        std_events.append(
            {
                "identity": "nba_id",
                "game_id": game_id,
                "secs": secs,
                "event_id": event_id,
                "team_id": tid,
                "player_id": pid,
                "event": ev_type,
            }
        )

    for a in actions:
        action_type = a.get("actionType", "")
        desc = a.get("description", "") or ""
        sub_type = a.get("subType", "") or ""
        person_id = a.get("personId")
        team_id = a.get("teamId")
        period = a.get("period") or 0
        shot_result = a.get("shotResult")
        shot_value = a.get("shotValue")

        # Cumulative seconds
        clock_str = a.get("clock", "PT00M00.00S")
        secs = _parse_clock(clock_str, period)

        # --- Period boundaries ---
        if period != current_period:
            if current_period > 0:
                _emit("period_end", None, None, secs)
            if period <= 4:
                _emit("period_start", None, None, secs)
                _emit("new_poss", None, None, secs)  # period start = new possession
            else:
                _emit("overtime_start", None, None, secs)
                _emit("new_poss", None, None, secs)
            current_period = period

        # --- Decompose action into standard events ---

        if action_type == "Made Shot":
            is_three = shot_value == 3
            _emit("fg3_make" if is_three else "fg2_make", team_id, person_id, secs)

            # Assist
            ast_match = re.search(r"\(([^)]+)\s+\d+\s+AST\)", desc)
            if ast_match:
                ast_name = ast_match.group(1).lower()
                ast_pid = name_map.get(ast_name)
                if ast_pid:
                    assist_type = "fg3_assist" if is_three else "fg2_assist"
                    _emit(assist_type, team_id, ast_pid, secs)

        elif action_type == "Missed Shot":
            is_three = shot_value == 3
            _emit("fg3_miss" if is_three else "fg2_miss", team_id, person_id, secs)

            # Block: "BLOCK" in description
            if "BLOCK" in desc:
                block_match = re.search(r"(\w+)\s+BLOCK", desc)
                if block_match:
                    blocker_pid = name_map.get(block_match.group(1).lower())
                    # Block is credited to the defender's team
                    _emit("block", None, blocker_pid, secs)
                else:
                    _emit("block", None, person_id, secs)

        elif action_type == "Free Throw":
            made = shot_result == "Made"
            _emit("ft_make" if made else "ft_miss", team_id, person_id, secs)

        elif action_type == "Rebound":
            is_off = "off" in sub_type.lower() or "Off" in desc
            if is_off:
                _emit("o_reb", team_id, person_id, secs)
            else:
                _emit("d_reb", team_id, person_id, secs)
                _emit("new_poss", team_id, None, secs)

        elif action_type == "Turnover":
            _emit("turnover", team_id, person_id, secs)
            _emit("new_poss", None, None, secs)

            # Steal on turnover
            if "steal" in desc.lower() or "Steal" in sub_type:
                steal_match = re.search(r"STEAL\s*\((\d+)\s+STL\)", desc)
                if steal_match:
                    _emit("steal", None, person_id, secs)

        elif action_type == "Foul":
            _emit("foul_commit", team_id, person_id, secs)

            if "offensive" in sub_type.lower() or "offensive" in desc.lower():
                _emit("foul_draw_tov", team_id, person_id, secs)
                _emit("new_poss", None, None, secs)
            elif "shooting" in sub_type.lower():
                sv = shot_value or 2
                if sv == 3:
                    _emit("foul_draw_3_ft", team_id, person_id, secs)
                elif sv == 2:
                    _emit("foul_draw_2_ft", team_id, person_id, secs)
                else:
                    _emit("foul_draw_1_ft", team_id, person_id, secs)
            else:
                _emit("foul_draw_no_ft", team_id, person_id, secs)

        elif action_type == "Substitution":
            sub_match = re.search(r"SUB:\s*(\S+)\s+FOR\s+(\S+)", desc)
            if sub_match:
                in_name = sub_match.group(1).lower()
                out_name = sub_match.group(2).lower()
                in_pid = name_map.get(in_name)
                out_pid = name_map.get(out_name)
                if out_pid:
                    _emit("sub_out", team_id, out_pid, secs)
                if in_pid:
                    _emit("sub_in", team_id, in_pid, secs)

        elif action_type == "Jump Ball":
            if "win" in desc.lower():
                _emit("jump_ball_win", team_id, person_id, secs)
            else:
                _emit("jump_ball_lose", team_id, person_id, secs)
                _emit("jump_ball_win", None, None, secs)
            _emit("new_poss", team_id, None, secs)

        elif action_type == "Steal":
            _emit("steal", team_id, person_id, secs)
            _emit("new_poss", team_id, None, secs)

        elif action_type == "Block":
            _emit("block", team_id, person_id, secs)

        elif action_type == "Violation":
            _emit("turnover", team_id, person_id, secs)
            _emit("new_poss", None, None, secs)

        elif action_type == "Ejection":
            _emit("sub_out", team_id, person_id, secs)

    # Final period end
    if current_period > 0:
        final_secs = _parse_clock(
            actions[-1].get("clock", "PT00M00.00S"),
            actions[-1].get("period") or current_period,
        )
        if current_period <= 4:
            _emit("period_end", None, None, final_secs)
        else:
            _emit("overtime_end", None, None, final_secs)

    # Parse standard events into domain resultSets
    from src.etl.lib.pbp_parser import parse

    result = parse(std_events)

    # Attach game-level metadata as a resultSet so db_columns can map
    # home_team_id / away_team_id from pbp_stats with domain "game".
    if home_team_id is not None and away_team_id is not None:
        result.setdefault("resultSets", []).append(
            {
                "name": "game",
                "headers": ["home_team_id", "away_team_id"],
                "rowSet": [[home_team_id, away_team_id]],
            }
        )

    return result


def _parse_clock(clock_str: str, period: int) -> float:
    """Convert 'PT10M27.00S' in period 1 → cumulative seconds elapsed (93.0).

    Clock counts DOWN.  A 12-minute quarter has 720s.
    Period 1: 0-720, Period 2: 720-1440, etc.
    """
    import re

    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str or "")
    if not m:
        return 0.0
    remaining = int(m.group(1)) * 60 + float(m.group(2))
    quarter_seconds = 720.0
    elapsed_in_period = quarter_seconds - remaining
    return (period - 1) * quarter_seconds + elapsed_in_period


# ============================================================================
# FETCHER FACTORY
# ============================================================================


def make_fetcher(
    league_code: str,
    season_end_year: int,
    season_type_name: str,
    identity_code: str = "nba_id",
) -> Callable:
    """Create an api_fetcher closure for the given league, season, and type.

    Returns a function that accepts (dataset, extra_params) and executes
    a fully parameterized NBA API call with retry logic.
    """
    rate_limiter = get_rate_limiter("nba_api")

    def fetch(
        dataset: str, extra_params: Union[Dict[str, Any], None] = None
    ) -> Union[Dict, None]:
        ds_cfg = DATASETS.get(identity_code, {}).get(dataset, {})
        class_name = ds_cfg.get("source_mapping", {}).get("class_name", dataset)
        DatasetClass = load_dataset_class(class_name)
        if DatasetClass is None:
            return None
        full_params = build_dataset_params(
            dataset,
            league_code,
            season_end_year,
            season_type_name,
            extra_params=extra_params or {},
        )
        api_call = create_api_call(
            DatasetClass, full_params, dataset_name=dataset, rate_limiter=rate_limiter
        )
        result = rate_limiter.with_retry(api_call)
        if result is not None:
            if class_name == "playbyplayv3":
                result = _normalize_pbp_response(result)
            result = _apply_row_filters(result, ds_cfg, season_end_year)
        return result

    return fetch


# ============================================================================
# Season detection
# ============================================================================


def detect_recent_games(
    dataset_name: str,
    league_code: str,
    season: str,
    season_type: str,
    lookback_days: int = 8,
    identity_code: str = "nba_id",
) -> Union[Dict, None]:
    """Query the NBA API for games of *season_type* within *lookback_days*.

    Returns the raw API result dict (with ``resultSets``) or ``None`` on failure.
    Used by the season detector to find active season types.
    """
    from datetime import datetime, timedelta

    rate_limiter = get_rate_limiter("nba_api")
    league_cfg = LEAGUES[league_code]
    season_end_year = parse_season_end_year(season, league_cfg["season_format"])

    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
    wire = ds_cfg.get("source_mapping", {})
    class_name = wire.get("class_name", dataset_name)
    DatasetClass = load_dataset_class(class_name)
    if DatasetClass is None:
        return None

    end = datetime.now().date()
    start = end - timedelta(days=lookback_days)

    params = build_dataset_params(
        dataset_name,
        league_code,
        season_end_year,
        season_type,
        "player",
    )
    params["date_from_nullable"] = start.isoformat()
    params["date_to_nullable"] = end.isoformat()

    try:
        api_call = create_api_call(
            DatasetClass,
            params,
            dataset_name=dataset_name,
            rate_limiter=rate_limiter,
        )
        return rate_limiter.with_retry(api_call, max_retries=1)
    except Exception as exc:
        logger.warning(
            "Season detector %s call failed for %s/%s (lookback=%dd): %s",
            dataset_name,
            league_code,
            season_type,
            lookback_days,
            exc,
        )
        return None
