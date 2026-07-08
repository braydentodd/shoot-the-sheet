"""
Shoot the Sheet - League Resolvers

Pure resolvers over :data:`src.definitions.leagues.LEAGUES`.  Season
label *formatting* is delegated to :mod:`src.lib.season_formatter` so the same
shape engine drives league-canonical and source-wire formats.
"""

from datetime import datetime
from typing import List, Optional, Tuple

from src.definitions.leagues import LEAGUES, League, SeasonType
from src.lib.season_formatter import format_season_label, parse_season_end_year


def _league_or_raise(league_code: str) -> "League":
    if league_code not in LEAGUES:
        raise ValueError(f"Unknown league: {league_code!r}")
    return LEAGUES[league_code]


def _parse_flip_md(value: str) -> Tuple[int, int]:
    """Parse ``'MM/DD'`` into ``(month, day)``."""
    month_str, day_str = value.split("/")
    return int(month_str), int(day_str)


def get_current_season_year(league_code: str, now: Optional[datetime] = None) -> int:
    """End-year of the current season for ``league_code``, respecting calendar_flip."""
    cfg = _league_or_raise(league_code)
    flip_month, flip_day = _parse_flip_md(cfg["calendar_flip"])
    now = now or datetime.now()
    if (now.month, now.day) >= (flip_month, flip_day):
        return now.year + 1
    return now.year


def get_current_season(league_code: str, now: Optional[datetime] = None) -> str:
    """Current season label for ``league_code`` (e.g. ``'2025-26'`` for NBA)."""
    cfg = _league_or_raise(league_code)
    end_year = get_current_season_year(league_code, now)
    return format_season_label(end_year, cfg["season_format"])


def get_retained_seasons(league_code: str, current_season: str) -> List[str]:
    """Retained seasons (oldest -> newest) from ``season_retention_start``."""
    cfg = _league_or_raise(league_code)
    start = cfg["season_retention_start"]
    fmt = cfg["season_format"]
    end_year = parse_season_end_year(current_season, fmt)
    start_year = parse_season_end_year(start, fmt)
    return [format_season_label(y, fmt) for y in range(start_year, end_year + 1)]


def get_oldest_retained_season(league_code: str, current_season: str) -> str:
    """Oldest season still inside the retention window."""
    return get_retained_seasons(league_code, current_season)[0]


# ============================================================================
# Season type resolvers
# ============================================================================
#  league.season_types = { canonical_key: {is_postseason, min_season}, ... }


def get_all_canonical_season_types(league_code: str) -> List[str]:
    """Every canonical season-type key for the league, in declaration order."""
    cfg = _league_or_raise(league_code)
    return list(cfg["season_types"].keys())


def get_regular_season_types(league_code: str) -> List[str]:
    """Canonical keys where is_postseason is False."""
    cfg = _league_or_raise(league_code)
    return [k for k, v in cfg["season_types"].items() if not v["is_postseason"]]


def get_postseason_types(league_code: str) -> List[str]:
    """Canonical keys where is_postseason is True."""
    cfg = _league_or_raise(league_code)
    return [k for k, v in cfg["season_types"].items() if v["is_postseason"]]


def get_season_type_def(league_code: str, canonical_key: str) -> SeasonType:
    """Return the SeasonType for *canonical_key*, or raise ValueError."""
    cfg = _league_or_raise(league_code)
    st = cfg["season_types"].get(canonical_key)
    if st is None:
        raise ValueError(
            f"Season type {canonical_key!r} not declared for league {league_code!r}"
        )
    return st


def is_season_type_valid_for(league_code: str, canonical_key: str, season: str) -> bool:
    """Return True if *canonical_key*'s min_season is <= *season*."""
    st = get_season_type_def(league_code, canonical_key)
    min_s = st.get("min_season")
    if min_s is None:
        return True
    return season >= min_s
