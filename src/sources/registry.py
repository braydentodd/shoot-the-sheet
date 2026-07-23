"""Source module registry.

Maps source code (e.g. "nba_api") to its (config, client) module pair.
To add a new source, import its modules and register them here.

Consumed by ``orchestrator._load_source`` and ``rate_limiter.get_rate_limiter``.
"""

from typing import Any, Tuple

from src.sources.nba_api import client as nba_client
from src.sources.nba_api import config as nba_config
from src.sources.nba_data import client as nba_data_client
from src.sources.nba_data import config as nba_data_config

SOURCE_MODULES: dict[str, Tuple[Any, Any]] = {
    "nba_api": (nba_config, nba_client),
    "nba_data": (nba_data_config, nba_data_client),
}


def get_source_modules(source_code: str) -> Tuple[Any, Any]:
    if source_code not in SOURCE_MODULES:
        raise ValueError(f"Source modules for {source_code!r} not registered.")
    return SOURCE_MODULES[source_code]
