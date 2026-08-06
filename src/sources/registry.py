"""Source module registry.

Maps source code (e.g. ``"nba_api"``) to its ``(config, client)`` module
pair.  Every source must register both modules here.

Consumed by ``orchestrator._load_source``, ``rate_limiter.get_rate_limiter``,
and ``season_detector`` (for ``detect_recent_games`` dispatch).

Per-source module layout (the standard every source follows):

``config.py``
    Declarative definitions only -- constants, mappings, defaults.  No
    I/O, no lib imports, no side effects.

``client.py``
    I/O orchestration and the public entry points the orchestrator
    dispatches by attribute (``make_fetcher``, ``fetch_game_pbp``,
    ``fetch_raw_rows``, ``cleanup_season_files``, ``detect_recent_games``).
    Re-exports source-specific builders lib code consumes by generic name
    (e.g. nba_data re-exports ``build_signature`` / ``build_event_key``
    for PBP discovery).

Additional pure-concern modules
    One module per distinct pure or protocol implementation (e.g.
    ``match_strategy.py``, ``normalizer.py`` for nba_data), kept out of
    ``client.py`` so they stay side-effect free and independently
    testable.  ``client.py`` imports from them.

A single-concern source (e.g. the nba_api HTTP wrapper) stays one
``client.py``; it splits only when a distinct pure layer emerges.
"""

from typing import Any

from src.sources.nba_api import client as nba_client
from src.sources.nba_api import config as nba_config
from src.sources.nba_data import client as nba_data_client
from src.sources.nba_data import config as nba_data_config

SOURCE_MODULES: dict[str, tuple[Any, Any]] = {
    "nba_api": (nba_config, nba_client),
    "nba_data": (nba_data_config, nba_data_client),
}


def get_source_modules(source_code: str) -> tuple[Any, Any]:
    if source_code not in SOURCE_MODULES:
        raise ValueError(f"Source modules for {source_code!r} not registered.")
    return SOURCE_MODULES[source_code]
