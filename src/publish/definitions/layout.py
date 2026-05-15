"""
The Glass - Sheet Layout Definitions

Tab, section, and subsection definitions that drive the publish layout
engine, plus the summary-threshold rows displayed at the bottom of
players/teams sheets.
"""

from typing import TypedDict, Dict, List, Tuple, Union


# ============================================================================
# TABS
# ============================================================================

# Ordered list of aggregate (non-team) tabs that are published after all
# individual team tabs.  The orchestrator iterates this sequence directly;
# any priority-tab reordering is applied on top.
AGGREGATE_TABS: List[str] = ['all_players', 'all_teams']

class TabConfigDef(TypedDict):
    tab_name: Union[str, None]
    move_to_front: bool
    footer: Union[str, None]
    footer_divider_row_height: Union[int, None]

class CategoryGroupDef(TypedDict):
    sections: List[str]
    border_color: str

class SectionDef(TypedDict):
    title: str
    column: str

class SubsectionDef(TypedDict):
    title: str
    columns: List[str]

TABS_CONFIG: Dict[str, TabConfigDef] = {

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

SECTIONS_CONFIG = {
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

SUBSECTIONS: Dict[str, SectionDef] = {
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



