"""
The Glass - League Resolvers

Pure resolvers over :data:`src.core.definitions.leagues.LEAGUES`.  Season
label *formatting* is delegated to :mod:`src.core.lib.seasons` so the same
shape engine drives league-canonical and source-wire formats.
"""

from datetime import datetime
from typing import List, Tuple

from src.core.definitions.leagues import LEAGUES
from src.core.definitions.stats import RETENTION_SEASONS
from src.core.lib.seasons_resolver import format_season_label, parse_season_end_year


def _league_or_raise(league_key: str) -> dict:
    if league_key not in LEAGUES:
        raise ValueError(f"Unknown league: {league_key!r}")
    return LEAGUES[league_key]


def _parse_flip_md(value: str) -> Tuple[int, int]:
    """Parse ``'MM/DD'`` into ``(month, day)``."""
    month_str, day_str = value.split('/')
    return int(month_str), int(day_str)


def get_current_season_year(league_key: str, now: datetime = None) -> int:
    """End-year of the current season for ``league_key``, respecting calendar_flip."""
    cfg = _league_or_raise(league_key)
    flip_month, flip_day = _parse_flip_md(cfg['calendar_flip'])
    now = now or datetime.now()
    if (now.month, now.day) >= (flip_month, flip_day):
        return now.year + 1
    return now.year


def get_current_season(league_key: str, now: datetime = None) -> str:
    """Current season label for ``league_key`` (e.g. ``'2025-26'`` for NBA)."""
    cfg = _league_or_raise(league_key)
    end_year = get_current_season_year(league_key, now)
    return format_season_label(end_year, cfg['season_format'])


def get_retained_seasons(league_key: str, current_season: str) -> List[str]:
    """Retained seasons (oldest -> newest) under global ``RETENTION_SEASONS``."""
    cfg = _league_or_raise(league_key)
    count = RETENTION_SEASONS
    fmt = cfg['season_format']
    end_year = parse_season_end_year(current_season, fmt)
    return [
        format_season_label(end_year - count + i + 1, fmt)
        for i in range(count)
    ]


def get_oldest_retained_season(league_key: str, current_season: str) -> str:
    """Oldest season still inside the retention window."""
    return get_retained_seasons(league_key, current_season)[0]


def get_season_types(league_key: str) -> List[str]:
    """Union of regular and post season type codes, in declaration order."""
    cfg = _league_or_raise(league_key)
    return list(cfg['regular_season_types']) + list(cfg['postseason_types'])
