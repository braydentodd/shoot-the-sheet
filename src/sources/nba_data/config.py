"""
Shoot the Sheet - nba_data Source Configuration

Pure data definitions for the nba_data (nbastats CSV) source:
column name references, event msgtype constants, period lengths,
and data directory configuration.

No functions -- only constants consumed by the normalizer and client.
"""

import os

# ============================================================================
# DATA DIRECTORIES
# ============================================================================

# Resolve paths against the project root (three levels up from this file:
# src/sources/nba_data/config.py -> src/sources/nba_data -> src/sources -> src -> root).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Extracted CSV files live here, one subdirectory per season.
#   {EXTRACTED_DIR}/nbastats_{start_year}/nbastats_{start_year}.csv
EXTRACTED_DIR = os.path.join(_PROJECT_ROOT, "data", "nba_data", "extracted")

# Downloaded .tar.xz archives live here.
#   {ARCHIVE_DIR}/nbastats_{start_year}.tar.xz
ARCHIVE_DIR = os.path.join(_PROJECT_ROOT, "data", "nba_data", "archives")

# Base URL for downloading season archives from shufinskiy/nba_data.
# {start_year} is substituted at runtime.
ARCHIVE_URL_TEMPLATE = (
    "https://github.com/shufinskiy/nba_data/raw/main/"
    "datasets/nbastats_{start_year}.tar.xz"
)


# ============================================================================
# CSV COLUMN NAMES
# ============================================================================

COL = {
    "GAME_ID": "GAME_ID",
    "EVENTNUM": "EVENTNUM",
    "EVENTMSGTYPE": "EVENTMSGTYPE",
    "EVENTMSGACTIONTYPE": "EVENTMSGACTIONTYPE",
    "PERIOD": "PERIOD",
    "PCTIMESTRING": "PCTIMESTRING",
    "HOMEDESCRIPTION": "HOMEDESCRIPTION",
    "NEUTRALDESCRIPTION": "NEUTRALDESCRIPTION",
    "VISITORDESCRIPTION": "VISITORDESCRIPTION",
    "SCORE": "SCORE",
    "PERSON1TYPE": "PERSON1TYPE",
    "PLAYER1_ID": "PLAYER1_ID",
    "PLAYER1_NAME": "PLAYER1_NAME",
    "PLAYER1_TEAM_ID": "PLAYER1_TEAM_ID",
    "PLAYER1_TEAM_ABBREVIATION": "PLAYER1_TEAM_ABBREVIATION",
    "PERSON2TYPE": "PERSON2TYPE",
    "PLAYER2_ID": "PLAYER2_ID",
    "PLAYER2_NAME": "PLAYER2_NAME",
    "PLAYER2_TEAM_ID": "PLAYER2_TEAM_ID",
    "PERSON3TYPE": "PERSON3TYPE",
    "PLAYER3_ID": "PLAYER3_ID",
    "PLAYER3_NAME": "PLAYER3_NAME",
    "PLAYER3_TEAM_ID": "PLAYER3_TEAM_ID",
}


# ============================================================================
# EVENTMSGTYPE CONSTANTS
# ============================================================================

class MSG:
    """nbastats EVENTMSGTYPE values."""
    MADE_FG = 1
    MISSED_FG = 2
    FREE_THROW = 3
    REBOUND = 4
    TURNOVER = 5
    FOUL = 6
    SUBSTITUTION = 8
    JUMP_BALL = 10
    PERIOD_START = 12
    PERIOD_END = 13


# ============================================================================
# EVENTMSGACTIONTYPE CONSTANTS
# ============================================================================

# Offensive foul action types for detecting o_foul_draw events.
OFFENSIVE_FOUL_ACTION_TYPES = frozenset({4, 26})

# Foul taxonomy: every MSG=6 EVENTMSGACTIONTYPE maps to exactly one
# canonical foul event.  This is the source's declarative foul semantics:
#
#   standard_foul -- a normal foul.  Resulting free throws are
#       pot_poss_ending_scoring_opp candidates.
#   elevated_foul -- a pause in action (flagrant / technical / clear
#       path / away-from-play / team / taunting ...).  Never possession
#       changing, never pot_poss_ending_scoring_opp; the trip is
#       transparent to scoring-sequence tracking.
#
# The elevated classification is proposed here and confirmed during the
# core.pbp_events catalog migration (discover-pbp over MSG=6, then
# review).  Verified against the 2010-11 nbastats archive (actions 6, 9,
# 11-19 are technical/flagrant/clear-path family fouls).
FOUL_TAXONOMY: dict[int, str] = {
    1: "standard_foul",   # personal
    2: "standard_foul",   # shooting
    3: "standard_foul",   # loose ball
    4: "standard_foul",   # offensive
    5: "standard_foul",   # inbound
    6: "elevated_foul",   # away from play
    9: "elevated_foul",   # clear path
    10: "standard_foul",  # double personal
    11: "elevated_foul",  # technical
    12: "elevated_foul",  # non-unsportsmanlike (bench technical)
    13: "elevated_foul",  # hanging tech
    14: "elevated_foul",  # flagrant 1
    15: "elevated_foul",  # flagrant 2
    16: "elevated_foul",  # double technical
    17: "elevated_foul",  # defensive 3 seconds
    18: "elevated_foul",  # team foul
    19: "elevated_foul",  # taunting
    26: "standard_foul",  # offensive charge
    27: "standard_foul",  # personal block
    28: "standard_foul",  # personal take
    29: "standard_foul",  # shooting block
}


# ============================================================================
# PERSON TYPE CONSTANTS
# ============================================================================

PERSON_NONE = 0
PERSON_TEAM = 3
PERSON_HOME = 4
PERSON_VISITOR = 5
