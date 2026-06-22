"""
Value formatting utilities for display.
"""

from typing import Any, Callable, Union

from src.publish.definitions.stats import STAT_RATES


def format_stat_value(value: Any, fmt: str, decimals: int, nullable: bool) -> Any:
    """Format a stat value for display according to column definition.

    Args:
        value: The stat value to format
        fmt: Format type ('percentage', etc.)
        decimals: Number of decimal places
        nullable: If False, show 0 instead of blank for None values

    Returns:
        Formatted value (int, float, or empty string)
    """
    if value is None:
        # Non-nullable columns (games, seasons) show 0 instead of blank
        if not nullable:
            return 0
        return ""
    if isinstance(value, (int, float)) and value == 0:
        return 0

    if fmt == "percentage":
        # Value is already 0-100 from formula (e.g., (turnovers/possessions)*100)
        # Do NOT auto-scale — formulas are responsible for correct magnitude.
        rounded = round(value, decimals)
    else:
        rounded = round(value, decimals)

    # Return int if whole number
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def format_height(inches: Any) -> str:
    """Format height in inches to feet-inches string. 80 → 6'8\", 78.5 → 6'6.5\".

    Args:
        inches: Height in inches (int or float)

    Returns:
        Formatted height string (e.g., "6'8\"" or "6'6.5\"")
    """
    if not inches:
        return ""
    feet = int(inches // 12)
    remaining = inches % 12
    # Whole inches for individual players, 1 decimal for team averages
    if remaining == int(remaining):
        return f"{feet}'{int(remaining)}\""
    return f"{feet}'{remaining:.1f}\""


def format_section_header(
    section: str,
    historical_config: Union[dict, None] = None,
    current_season: int = 0,
    is_postseason: bool = False,
    mode: Union[str, None] = None,
    season_format_fn: Callable[[int], str] = str,
) -> str:
    """
    Build the full section header display string.

    Current stats:   "2025-26 Regular Season Stats per 100 Poss"
    Historical/Post: "Regular Season Stats per 100 Poss (Previous 3 Seasons)"
                     "Regular Season Stats per 100 Poss (Previous Season)"  (1 season)

    Args:
        section: 'current_stats', 'historical_stats', or 'postseason_stats'
        historical_config: {mode, value} for hist/post
        current_season: End-year integer (e.g. 2026 for the 2025-26 season)
        is_postseason: True for postseason sections
        mode: Stats rate ('per_possession', 'per_minute')
        season_format_fn: League-bound formatter that turns the end-year integer
            into a season label.  Defaults to ``str`` so unbound callers still
            render something readable.

    Returns:
        Formatted section header string
    """
    season_label = "Postseason" if is_postseason else "Regular Season"

    # Build the rate string ("per 100 Poss")
    rate_str = ""
    if mode and mode in STAT_RATES:
        rate_info = STAT_RATES[mode]
        rate_val = rate_info.get("rate")
        short_label = rate_info.get("short_label", "")
        if rate_val is not None:
            rate_str = f" per {rate_val} {short_label}"
        else:
            rate_str = f" per {short_label}"

    # Current stats: "YYYY-YY Regular Season Stats per 100 Poss"
    if section == "current_stats":
        season_str = season_format_fn(current_season)
        return f"{season_str} {season_label} Stats{rate_str}"

    # Historical / Postseason sections
    value = (historical_config or {}).get("value", 3)

    if isinstance(value, int):
        num = value
    elif isinstance(value, list) and value:
        num = len(value)
    else:
        return f"{season_label} Stats{rate_str}"

    if num == 1:
        timeframe_str = "(Previous Season)"
    else:
        timeframe_str = f"(Previous {num} Seasons)"

    return f"{season_label} Stats{rate_str} {timeframe_str}"


def _strip_trailing_decimal_zeros(s: str) -> str:
    """Strip trailing zeros from the fractional part only, and the decimal
    point if nothing remains after it. Leaves digits in the integer part
    alone (e.g., '+10.0' -> '+10', not '+1')."""
    if "." not in s:
        return s
    int_part, frac_part = s.split(".", 1)
    frac_part = frac_part.rstrip("0")
    return f"{int_part}.{frac_part}" if frac_part else int_part


def _format_companion(rank: float, diff: Union[float, None], base_def: dict) -> str:
    """Format a percentile companion cell as 'rank\n+/-diff'.

    Displays the percentile rank on the first line and the over/under
    vs league average (50th percentile value) on the second line.
    """
    rank_str = _strip_trailing_decimal_zeros(f"{rank:.1f}")

    if diff is None:
        return rank_str

    decimals = base_def.get("decimal_places")
    if decimals is None:
        decimals = 1

    diff_str = _strip_trailing_decimal_zeros(f"{diff:+.{decimals}f}")

    if diff_str in ("+", "-"):
        diff_str = "+0"
    if diff_str == "-0":
        diff_str = "+0"

    return f"{rank_str}\n{diff_str}"
