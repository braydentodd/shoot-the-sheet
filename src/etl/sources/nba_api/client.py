"""
The Glass - NBA API Client

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

from src.core.lib.rate_limiter import get_rate_limiter
from src.etl.sources.nba_api.config import (
    API_CONFIG,
    DATASETS,
)

warnings.filterwarnings(
    "ignore",
    message="Failed to return connection to pool",
    module="urllib3",
)

logger = logging.getLogger(__name__)


# ============================================================================
# BROWSER HEADERS  (required by stats.nba.com)
# ============================================================================

_NBA_STATS_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Host": "stats.nba.com",
    "Origin": "https://www.nba.com",
    "Pragma": "no-cache",
    "Referer": "https://www.nba.com/",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


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
        from nba_api.stats.library import http as _stats_http
        from nba_api.library import http as _base_http

        _stats_http.STATS_HEADERS = _NBA_STATS_HEADERS
        _stats_http.NBAStatsHTTP.headers = _NBA_STATS_HEADERS
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
    dataset_name: str = '',
    timeout: Union[int, None] = None,
    rate_limiter: Union[Any, None] = None,
) -> Callable:
    """Build a zero-arg callable that executes an NBA API request.

    Internal params (keys starting with ``_``) are stripped before the call.
    Parameters not accepted by the dataset constructor are silently dropped.
    Returns raw JSON dict with ``resultSets``.
    """
    _patch_nba_api_headers()

    clean_params = {k: v for k, v in params.items() if not k.startswith('_')}

    # Filter to only params the dataset actually accepts
    sig = inspect.signature(dataset_class.__init__)
    accepted = set(sig.parameters.keys()) - {'self'}
    has_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
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

def with_retry(func: Callable, rate_limiter: Any, max_retries: Union[int, None] = None) -> Any:
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
    season: str,
    season_type_name: str,
    entity: str,
    extra_params: Union[Dict[str, Any], None] = None,
) -> Dict[str, Any]:
    """Assemble the full parameter dict for an NBA API call.

    Merges standard parameters (season, league_id, per_mode, season_type)
    with dataset-specific defaults and caller-supplied overrides.
    """
    ds_cfg = DATASETS.get(dataset_name, {})

    # Season parameter — most datasets use 'season' (str like "2025-26"),
    # but some (e.g., draft combine) use 'season_year' (int like 2025).
    season_param = ds_cfg.get('season_param', 'season')
    if season_param == 'season_year':
        params: Dict[str, Any] = {season_param: int(season.split('-')[0])}
    else:
        params: Dict[str, Any] = {season_param: season}

    # Season type
    st_param = ds_cfg.get('season_type_param')
    if st_param:
        params[st_param] = season_type_name

    # Per-mode
    pm_param = ds_cfg.get('per_mode_param')
    if pm_param and pm_param in API_CONFIG:
        params[pm_param] = API_CONFIG[pm_param]

    # Player / Team discriminator for shared datasets
    if (
        'player' in ds_cfg.get('entity_types', [])
        and 'team' in ds_cfg.get('entity_types', [])
    ):
        if entity == 'player':
            params['player_or_team'] = 'Player'
        else:
            params['player_or_team'] = 'Team'

    # League ID — add both variants; signature filtering in create_api_call
    # will keep only the one the dataset accepts.
    params['league_id'] = API_CONFIG['league_id']
    params['league_id_nullable'] = API_CONFIG['league_id']

    # Caller overrides win
    if extra_params:
        params.update(extra_params)

    return params


# ============================================================================
# FETCHER FACTORY
# ============================================================================

def make_fetcher(season: str, season_type_name: str, entity: str) -> Callable:
    """Create an api_fetcher closure for the given season, season type, and entity.

    Returns a function that accepts (dataset, extra_params) and executes
    a fully parameterized NBA API call with retry logic.
    Virtual datasets (e.g. team_metadata) are routed to dedicated handlers.
    """
    rate_limiter = get_rate_limiter('nba_api')

    def fetch(dataset: str, extra_params: Union[Dict[str, Any], None] = None) -> Union[Dict, None]:
        ds_cfg = DATASETS.get(dataset, {})
        if ds_cfg.get('virtual'):
            return _fetch_virtual(dataset, season)

        DatasetClass = load_dataset_class(dataset)
        if DatasetClass is None:
            return None
        full_params = build_dataset_params(
            dataset, season, season_type_name, entity, extra_params or {},
        )
        api_call = create_api_call(DatasetClass, full_params, dataset_name=dataset, rate_limiter=rate_limiter)
        return with_retry(api_call, rate_limiter)
    return fetch


# ============================================================================
# VIRTUAL DATASET HANDLERS
# ============================================================================

def _fetch_virtual(dataset: str, season: str) -> Union[Dict, None]:
    """Dispatch virtual datasets to their handlers."""
    if dataset == 'team_metadata':
        return _fetch_team_metadata(season)
    logger.warning('Unknown virtual dataset: %s', dataset)
    return None


# ============================================================================
# ROSTER SNAPSHOT  (consumed by the runner's `rosters` phase)
# ============================================================================

def fetch_roster_memberships(
    league_key: str,
    season: str,
    season_type_name: str = 'Regular Season',
    roster_snapshot: Union[Dict[str, Any], None] = None,
) -> list:
    """Return ``[(team_source_id, player_source_id, jersey_num, seasons_exp), ...]``
    for every active roster slot in the league for the given season.

    The roster_snapshot config supplies the dataset and linking fields (team_id_field,
    player_id_field). Additional rosters-scoped fields (jersey_num, seasons_exp, etc.)
    are dynamically discovered from the column registry.
    
    Players whose team ID is null or zero (free agents / inactive) are dropped.
    """
    if not roster_snapshot:
        raise ValueError('roster_snapshot config is required for roster_maintainer role')

    from src.core.definitions.columns import get_rosters_fields

    dataset = roster_snapshot['dataset']
    team_id_field = roster_snapshot['team_id_field']
    player_id_field = roster_snapshot['player_id_field']
    request_params = dict(roster_snapshot.get('params', {}))
    
    # Dynamically discover rosters-scoped fields from columns.py
    rosters_fields = get_rosters_fields(league_key, 'nba_api')

    fetcher = make_fetcher(season, season_type_name, 'player')
    result = fetcher(dataset, request_params)
    if result is None:
        logger.warning(
            'Roster snapshot %s/%s returned no result from %s',
            league_key, season, dataset,
        )
        return []

    pairs: list = []
    for rs in result.get('resultSets', []):
        headers = rs.get('headers', [])
        if team_id_field not in headers or player_id_field not in headers:
            continue
        
        tid_idx = headers.index(team_id_field)
        pid_idx = headers.index(player_id_field)
        
        # Build dynamic field indices from discovered rosters fields
        field_indices = {}
        for col_name, api_field_name in rosters_fields.items():
            if api_field_name in headers:
                field_indices[col_name] = headers.index(api_field_name)
        
        for row in rs['rowSet']:
            tid = row[tid_idx]
            pid = row[pid_idx]
            if tid is None or pid is None:
                continue
            try:
                tid_val = int(tid)
            except (TypeError, ValueError):
                continue
            if tid_val == 0:
                continue
            
            # Extract rosters fields in consistent order: jersey_num, seasons_exp, ...
            extra_fields = []
            for col_name in sorted(rosters_fields.keys()):
                idx = field_indices.get(col_name)
                extra_fields.append(row[idx] if idx is not None else None)
            
            # Pair: (team_id, player_id, jersey_num, seasons_exp, ...)
            pairs.append((tid_val, pid, *extra_fields))

    logger.info(
        'Roster snapshot %s/%s: %d active rows from %s (fields: %s)',
        league_key, season, len(pairs), dataset, sorted(rosters_fields.keys()),
    )
    return pairs


def _fetch_team_metadata(season: str) -> Dict:
    """Combine static team data and LeagueStandings into a standard resultSets format.

    Returns abbreviation from nba_api static data and conference from the
    LeagueStandings API, keyed by TEAM_ID so the extract pipeline can
    process it like any other dataset.
    """
    from nba_api.stats.static import teams as static_teams
    from nba_api.stats.endpoints import leaguestandings

    rate_limiter = get_rate_limiter('nba_api')

    # Static abbreviations keyed by team ID
    abbr_map = {t['id']: t['abbreviation'] for t in static_teams.get_teams()}

    # Conference from standings
    _patch_nba_api_headers()
    standings_call = create_api_call(
        leaguestandings.LeagueStandings,
        {'season': season, 'league_id': '00'},
        dataset_name='leaguestandings',
        rate_limiter=rate_limiter,
    )
    standings = with_retry(standings_call, rate_limiter)

    conf_map: Dict[int, str] = {}
    for rs in standings.get('resultSets', []):
        if 'TeamID' not in rs.get('headers', []):
            continue
        headers = rs['headers']
        tid_idx = headers.index('TeamID')
        conf_idx = headers.index('Conference') if 'Conference' in headers else None
        if conf_idx is None:
            continue
        for row in rs['rowSet']:
            conf_map[row[tid_idx]] = row[conf_idx]

    # Build combined result in standard API format
    all_ids = sorted(set(abbr_map) | set(conf_map))
    row_set = [
        [tid, abbr_map.get(tid), conf_map.get(tid)]
        for tid in all_ids
    ]

    return {
        'resultSets': [{
            'name': 'TeamMetadata',
            'headers': ['TEAM_ID', 'TEAM_ABBREVIATION', 'TEAM_CONFERENCE'],
            'rowSet': row_set,
        }]
    }
