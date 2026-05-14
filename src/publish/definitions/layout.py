"""
The Glass - Sheet Layout Definitions

Tab, section, and subsection definitions that drive the publish layout
engine, plus the summary-threshold rows displayed at the bottom of
players/teams sheets.
"""

from typing import Any, Dict, List, Tuple


# ============================================================================
# TABS
# ============================================================================

# Ordered list of aggregate (non-team) tabs that are published after all
# individual team tabs.  The orchestrator iterates this sequence directly;
# any priority-tab reordering is applied on top.
AGGREGATE_TABS: List[str] = ['all_players', 'all_teams']

TABS_CONFIG: Dict[str, Dict[str, Any]] = {
    'all_players': {
        'tab_name':                  'Players',
        'move_to_front':             True,
        'footer':                    'percentiles',
        'footer_divider_row_height': 4,
    },
    'all_teams': {
        'tab_name':                  'Teams',
        'move_to_front':             True,
        'footer':                    'percentiles',
        'footer_divider_row_height': 4,
    },
    'individual_team': {
        'move_to_front':             False,
        'footer':                    'team/opponent',
        'footer_divider_row_height': 4,
    },
}


# ============================================================================
# SECTIONS
# ============================================================================

SECTIONS_CONFIG: Dict[str, Dict[str, Any]] = {
    'entities': {
        'menu_label':         None,
        'stats_timeframe':    None,
        'toggleable':         False,
        'visible_by_default': True,
    },
    'profile': {
        'display_name':       'Profile',
        'menu_label':         'Profile',
        'stats_timeframe':    None,
        'toggleable':         True,
        'visible_by_default': True,
    },
    'evaluation': {
        'display_name':       'Evaluation',
        'menu_label':         'Evaluation',
        'stats_timeframe':    None,
        'toggleable':         True,
        'visible_by_default': True,
    },
    'current_stats': {
        'menu_label':         'Current Stats',
        'stats_timeframe':    'current',
        'toggleable':         True,
        'visible_by_default': True,
    },
    'historical_stats': {
        'menu_label':         'Historical Stats',
        'stats_timeframe':    'historical',
        'toggleable':         True,
        'visible_by_default': True,
    },
    'postseason_stats': {
        'menu_label':         'Postseason Stats',
        'stats_timeframe':    'historical',
        'toggleable':         True,
        'visible_by_default': True,
    },
    'identity': {
        'display_name':       'Identity',
        'menu_label':         None,
        'stats_timeframe':    None,
        'toggleable':         False,
        'visible_by_default': False,
    },
}


# ============================================================================
# SUBSECTIONS  (Row 2 grouping headers)
# ============================================================================

SUBSECTIONS: Dict[str, Dict[str, Any]] = {
    'league': {
        'display_name': 'League',
        'sections':     ['profile'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'player': {
        'display_name': 'Player',
        'sections':     ['profile'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'rates': {
        'display_name': 'Rates',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'scoring': {
        'display_name': 'Scoring',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'ball_management': {
        'display_name': 'Ball Management',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'rebounding': {
        'display_name': 'Rebounding',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'distance': {
        'display_name': 'Distance',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'defense': {
        'display_name': 'Defense',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
    'opponent': {
        'display_name': 'Opponent',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_teams'],
    },
    'team_ratings': {
        'display_name': 'Team Ratings',
        'sections':     ['current_stats', 'historical_stats', 'postseason_stats'],
        'tabs':         ['all_players', 'all_teams', 'individual_team'],
    },
}


# ============================================================================
# SUMMARY THRESHOLDS  (footer of players/teams sheets)
# ============================================================================

SUMMARY_THRESHOLDS: List[Tuple[str, int]] = [
    ('Best',            100),
    ('75th Percentile',  75),
    ('Average',          50),
    ('25th Percentile',  25),
    ('Worst',             0),
]


# ============================================================================
# COLUMN VALUE-KEY -> ENTITY TYPE
# Maps a column's "values" dict key to the entity type those values represent.
# ============================================================================

VALUES_KEY_ENTITY: Dict[str, str] = {
    'player':          'player',
    'individual_team': 'team',
    'all_teams':       'team',
    'opponents':       'team',
}


# ============================================================================
# VALIDATION SCHEMAS
# ============================================================================

TABS_CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    'move_to_front':             {'required': True, 'types': (bool,)},
    'footer':                    {'required': True, 'types': (str, type(None))},
    'footer_divider_row_height': {'required': True, 'types': (int,)},
}

SECTIONS_SCHEMA: Dict[str, Dict[str, Any]] = {
    'menu_label':         {'required': True, 'types': (str, type(None))},
    # A non-None stats_timeframe identifies a section as a stats section
    # (consumed by the publish layer to decide percentile / rate scaling).
    'stats_timeframe':    {'required': True, 'types': (str, type(None))},
    'toggleable':         {'required': True, 'types': (bool,)},
    'visible_by_default': {'required': True, 'types': (bool,)},
}

SUBSECTIONS_SCHEMA: Dict[str, Dict[str, Any]] = {
    'display_name': {'required': True, 'types': (str,)},
    'sections':     {'required': True, 'types': (list,)},
    'tabs':         {'required': True, 'types': (list,)},
}
