"""
The Glass - Destination Registry

Declarative registry of every publish destination. Destinations are where
data is output (e.g., Google Sheets, database exports, etc.).

Rate limiting configuration is defined per destination to handle API limits
for each destination type.
"""

from typing import TypedDict, Dict, List

VALID_DESTINATION_ROLES = frozenset({'primary', 'backup'})

class RateLimitsDef(TypedDict):
    requests_per_second: float
    max_retries: int
    backoff_base: int
    timeout_default: int
    timeout_bulk: int
    max_consecutive_failures: int

class AppsScriptDef(TypedDict):
    enabled: bool
    directory: str

class DestinationDef(TypedDict):
    leagues: List[str]
    role: str
    rate_limits: RateLimitsDef
    apps_script: AppsScriptDef

DESTINATIONS: Dict[str, DestinationDef] = {

    'google_sheets': {
        'leagues': ['nba'],
        'role': 'primary',
        'rate_limits': {
            'requests_per_second': 1.0,
            'max_retries': 3,
            'backoff_base': 30,
            'timeout_default': 30,
            'timeout_bulk': 120,
            'max_consecutive_failures': 5,
        },
        'apps_script': {
            'enabled':   True,
            'directory': 'apps_script',
        },
    },
}
