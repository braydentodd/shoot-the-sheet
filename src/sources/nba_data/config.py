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

# Extracted CSV files live here, one subdirectory per season.
#   {EXTRACTED_DIR}/nbastats_{start_year}/nbastats_{start_year}.csv
EXTRACTED_DIR = os.path.join("data", "nba_data", "extracted")

# Downloaded .tar.xz archives live here.
#   {ARCHIVE_DIR}/nbastats_{start_year}.tar.xz
ARCHIVE_DIR = os.path.join("data", "nba_data", "archives")

# Base URL for downloading season archives from shufinskiy/nba_data.
# {start_year} is substituted at runtime.
ARCHIVE_URL_TEMPLATE = (
    "https://github.com/shufinskiy/nba_data/releases/download/"
    "v4.0/nbastats_{start_year}.tar.xz"
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


# ============================================================================
# PERSON TYPE CONSTANTS
# ============================================================================

PERSON_NONE = 0
PERSON_TEAM = 3
PERSON_HOME = 4
PERSON_VISITOR = 5
