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
#  league.season_types = { group: [canonical_key, ...], ... }
#    e.g. { "regular_season": ["regular_season", "showcase_cup"],
#           "postseason":     ["playoffs"] }


def get_all_canonical_season_types(league_key: str) -> List[str]:
    """Every canonical season-type key for the league, in declaration order."""
    cfg = _league_or_raise(league_key)
    all_keys: List[str] = []
    for group in cfg["season_types"]:
        all_keys.extend(cfg["season_types"][group])
    return all_keys


def get_canonical_season_types_for_group(league_key: str, group: str) -> List[str]:
    """Return the canonical keys that belong to *group*.

    ``group`` must be one of ``'regular_season'`` / ``'postseason'``.
    """
    cfg = _league_or_raise(league_key)
    return list(cfg["season_types"].get(group, []))


def get_regular_season_types(league_key: str) -> List[str]:
    """Canonical keys for the regular-season group."""
    return get_canonical_season_types_for_group(league_key, "regular_season")


def get_postseason_types(league_key: str) -> List[str]:
    """Canonical keys for the postseason group."""
    return get_canonical_season_types_for_group(league_key, "postseason")


def get_consolidated_group(league_key: str, canonical_key: str) -> str:
    """Return the consolidated group a canonical key belongs to.

    Returns ``"regular_season"`` or ``"postseason"``.
    Raises ``ValueError`` if the key is not declared for the league.
    """
    cfg = _league_or_raise(league_key)
    for group, keys in cfg["season_types"].items():
        if canonical_key in keys:
            return group
    raise ValueError(
        f"Canonical season type {canonical_key!r} not declared for league {league_key!r}"
    )


def build_consolidation_map(league_key: str) -> Dict[str, str]:
    """Return ``{canonical_key: consolidated_group}`` for every canonical key."""
    cfg = _league_or_raise(league_key)
    result: Dict[str, str] = {}
    for group, keys in cfg["season_types"].items():
        for key in keys:
            result[key] = group
    return result


def get_effective_season_types(league_key: str) -> List[str]:
    """Return the canonical keys that need individual API calls.

    When ``combined_season_types`` declares that a lead key covers
    sub-keys (e.g. G League where ``regular_season`` also returns
    ``showcase_cup`` data), only the lead key is included.  Sub-keys
    are still part of ``get_all_canonical_season_types`` but are
    deduplicated here to avoid redundant API calls.
    """
    cfg = _league_or_raise(league_key)
    all_keys = get_all_canonical_season_types(league_key)
    combined = cfg.get("combined_season_types", {})
    covered: set = set()
    for lead, sub_keys in combined.items():
        covered.update(k for k in sub_keys if k != lead)
    return [k for k in all_keys if k not in covered]


def get_combined_covers(league_key: str, canonical_key: str) -> List[str]:
    """Return the list of canonical keys that *canonical_key* covers
    in a single API call, or ``[canonical_key]`` if not combined."""
    cfg = _league_or_raise(league_key)
    combined = cfg.get("combined_season_types", {})
    return list(combined.get(canonical_key, [canonical_key]))
