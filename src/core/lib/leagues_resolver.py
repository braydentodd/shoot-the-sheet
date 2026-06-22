"""
Shoot the Sheet - League Resolvers

Pure resolvers over :data:`src.core.definitions.leagues.LEAGUES`.  Season
label *formatting* is delegated to :mod:`src.core.lib.season_resolver` so the same
shape engine drives league-canonical and source-wire formats.
"""

from datetime import datetime
from typing import Dict, List, Tuple

from src.core.definitions.leagues import LEAGUES
from src.core.lib.season_resolver import format_season_label, parse_season_end_year


def _league_or_raise(league_key: str) -> dict:
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")
    return LEAGUES[league_key]


def _parse_flip_md(value: str) -> Tuple[int, int]:
    """Parse ``'MM/DD'`` into ``(month, day)``."""
    month_str, day_str = value.split("/")
    return int(month_str), int(day_str)


def get_current_season_year(league_key: str, now: datetime = None) -> int:
    """End-year of the current season for ``league_key``, respecting calendar_flip."""
    cfg = _league_or_raise(league_key)
    flip_month, flip_day = _parse_flip_md(cfg["calendar_flip"])
    now = now or datetime.now()
    if (now.month, now.day) >= (flip_month, flip_day):
        return now.year + 1
    return now.year


def get_current_season(league_key: str, now: datetime = None) -> str:
    """Current season label for ``league_key`` (e.g. ``'2025-26'`` for NBA)."""
    cfg = _league_or_raise(league_key)
    end_year = get_current_season_year(league_key, now)
    return format_season_label(end_year, cfg["season_format"])


def get_retained_seasons(league_key: str, current_season: str) -> List[str]:
    """Retained seasons (oldest -> newest) from ``season_retention_start``."""
    cfg = _league_or_raise(league_key)
    start = cfg["season_retention_start"]
    fmt = cfg["season_format"]
    end_year = parse_season_end_year(current_season, fmt)
    start_year = parse_season_end_year(start, fmt)
    return [format_season_label(y, fmt) for y in range(start_year, end_year + 1)]


def get_oldest_retained_season(league_key: str, current_season: str) -> str:
    """Oldest season still inside the retention window."""
    return get_retained_seasons(league_key, current_season)[0]


# ============================================================================
# Season type resolvers
# ============================================================================
#  league.season_types = { canonical_key: {is_postseason, min_season}, ... }


def get_all_canonical_season_types(league_key: str) -> List[str]:
    """Every canonical season-type key for the league, in declaration order."""
    cfg = _league_or_raise(league_key)
    return list(cfg["season_types"].keys())


def get_regular_season_types(league_key: str) -> List[str]:
    """Canonical keys where is_postseason is False."""
    cfg = _league_or_raise(league_key)
    return [k for k, v in cfg["season_types"].items() if not v["is_postseason"]]


def get_postseason_types(league_key: str) -> List[str]:
    """Canonical keys where is_postseason is True."""
    cfg = _league_or_raise(league_key)
    return [k for k, v in cfg["season_types"].items() if v["is_postseason"]]


def get_season_type_def(league_key: str, canonical_key: str) -> dict:
    """Return the SeasonTypeDef for *canonical_key*, or raise ValueError."""
    cfg = _league_or_raise(league_key)
    st = cfg["season_types"].get(canonical_key)
    if st is None:
        raise ValueError(
            f"Season type {canonical_key!r} not declared for league {league_key!r}"
        )
    return st


def is_season_type_valid_for(league_key: str, canonical_key: str, season: str) -> bool:
    """Return True if *canonical_key*'s min_season is <= *season*."""
    st = get_season_type_def(league_key, canonical_key)
    min_s = st.get("min_season")
    if min_s is None:
        return True
    return season >= min_s
