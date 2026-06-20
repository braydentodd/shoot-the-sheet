from typing import Any, Tuple

from src.etl.sources.nba_api import client as nba_client
from src.etl.sources.nba_api import config as nba_config
from src.etl.sources.pbp_stats import client as pbp_client
from src.etl.sources.pbp_stats import config as pbp_config

SOURCE_MODULES = {
    "nba_api": (nba_config, nba_client),
    "pbp_stats": (pbp_config, pbp_client),
}


def get_source_modules(source_key: str) -> Tuple[Any, Any]:
    if source_key not in SOURCE_MODULES:
        raise ValueError(f"Source modules for {source_key!r} not registered.")
    return SOURCE_MODULES[source_key]
