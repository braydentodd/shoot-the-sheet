"""
The Glass - Destination Registry

Declarative registry of every publish destination. Destinations are where
data is output (e.g., Google Sheets, database exports, etc.).

Rate limiting configuration is defined per destination to handle API limits
for each destination type.
"""

from typing import Any, Dict

VALID_DESTINATION_ROLES = frozenset({'primary', 'backup'})

APPS_SCRIPT_SCHEMA: Dict[str, Dict[str, Any]] = {
    'enabled':   {'required': True, 'types': (bool,)},
    'directory': {'required': True, 'types': (str,)},
}

DESTINATIONS_SCHEMA: Dict[str, Dict[str, Any]] = {
    'leagues':      {'required': True,  'types': (list,)},
    'role':         {'required': True,  'types': (str,), 'allowed_values': VALID_DESTINATION_ROLES},
    'rate_limits':  {'required': False, 'types': (dict, type(None))},
    'apps_script':  {'required': False, 'types': (dict, type(None))},
}

DESTINATIONS: Dict[str, Dict[str, Any]] = {
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
