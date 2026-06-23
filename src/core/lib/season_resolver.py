"""
Shoot the Sheet - Season Label Format Engine

Shape-driven rendering and parsing for season labels.  Supports both
league-canonical formats (a coarse ``same_year``/``split_year`` enum) and
arbitrary source wire formats (e.g. ``YYYY-YYYY`` for NCAA stats, ``YY/YY``
for an FIBA feed).

Two-digit year parsing uses a 1980 pivot: ``00..79`` resolves to ``2000..2079``,
``80..99`` to ``1980..1999``.  This window is plenty for sports data; revisit
if a source emits two-digit labels for seasons before 1980.
"""

from typing import Tuple, Union

from src.core.definitions.leagues import VALID_LEAGUE_SEASON_FORMATS

# ---------------------------------------------------------------------------
# Shape-level validation constants (local to this module)
# ---------------------------------------------------------------------------

VALID_SHAPES = frozenset(
    {
        "YYYY",
        "YY",
        "YYYY-YY",
        "YY-YY",
        "YYYY-YYYY",
        "YYYY/YY",
        "YY/YY",
        "YYYY/YYYY",
    }
)
VALID_ANCHORS = frozenset({"start", "end", None})
_VALID_ANCHORS_STR = frozenset({"start", "end"})

# ---------------------------------------------------------------------------
# League format mapping
# ---------------------------------------------------------------------------

_LEAGUE_FORMAT_TO_SHAPE: dict = {
    "same_year": ("YYYY", "end"),
    "split_year": ("YYYY-YY", None),
}

_TWO_DIGIT_PIVOT = 80


# ---------------------------------------------------------------------------
# Shape parsing
# ---------------------------------------------------------------------------


def _separator(shape: str) -> Union[str, None]:
    if "-" in shape:
        return "-"
    if "/" in shape:
        return "/"
    return None


def _segments(shape: str) -> Tuple[str, ...]:
    sep = _separator(shape)
    return tuple(shape.split(sep)) if sep else (shape,)


def _validate_shape(shape: str) -> None:
    if shape not in VALID_SHAPES:
        raise ValueError(
            f"Invalid season shape {shape!r}; expected one of {sorted(VALID_SHAPES)}"
        )


def _resolve_two_digit_year(two_digit: int) -> int:
    """Map a 0..99 short year to a four-digit year via the 1980 pivot."""
    return 2000 + two_digit if two_digit < _TWO_DIGIT_PIVOT else 1900 + two_digit


def _format_year(year: int, digits: int) -> str:
    if digits == 4:
        return str(year)
    if digits == 2:
        return f"{year % 100:02d}"
    raise ValueError(f"Year segment must be 2 or 4 digits, got {digits}")


# ---------------------------------------------------------------------------
# Shape-level renderer / parser
# ---------------------------------------------------------------------------


def render_season_in_shape(
    end_year: int,
    shape: str,
    anchor: Union[str, None] = None,
) -> str:
    """Render an integer ``end_year`` (e.g. ``2026``) into a season label.

    For single-segment shapes (``YYYY`` / ``YY``), ``anchor`` selects which
    side of the season the digits represent: ``'start'`` -> start year,
    ``'end'`` -> end year.

    For two-segment shapes, segments are always chronological (start -> end)
    and ``anchor`` is ignored.
    """
    _validate_shape(shape)
    if anchor not in VALID_ANCHORS:
        raise ValueError(
            f"Invalid anchor {anchor!r}; expected one of {sorted(_VALID_ANCHORS_STR)} or None"
        )

    sep = _separator(shape)
    if sep is None:
        if anchor not in ("start", "end"):
            raise ValueError(
                f"Single-year shape {shape!r} requires anchor='start' or 'end'"
            )
        year = end_year if anchor == "end" else end_year - 1
        return _format_year(year, len(shape))

    left_seg, right_seg = _segments(shape)
    return (
        f"{_format_year(end_year - 1, len(left_seg))}"
        f"{sep}"
        f"{_format_year(end_year, len(right_seg))}"
    )


def parse_season_in_shape(
    label: str,
    shape: str,
    anchor: Union[str, None] = None,
) -> int:
    """Inverse of :func:`render_season_in_shape`; returns the end_year integer."""
    _validate_shape(shape)
    if anchor not in VALID_ANCHORS:
        raise ValueError(
            f"Invalid anchor {anchor!r}; expected one of {sorted(_VALID_ANCHORS_STR)} or None"
        )

    sep = _separator(shape)
    if sep is None:
        if anchor not in ("start", "end"):
            raise ValueError(
                f"Single-year shape {shape!r} requires anchor='start' or 'end'"
            )
        digits = len(shape)
        if digits == 4:
            year = int(label)
        elif digits == 2:
            year = _resolve_two_digit_year(int(label))
        else:
            raise ValueError(f"Single-year shape {shape!r} has unsupported digit count")
        return year if anchor == "end" else year + 1

    left_seg, right_seg = _segments(shape)
    left_label, right_label = label.split(sep)

    # End year is preferred when the right segment is unambiguous (4-digit).
    if len(right_seg) == 4:
        return int(right_label)

    # Two-digit right segment: use left segment to disambiguate the century.
    end_two = int(right_label)
    if len(left_seg) == 4:
        start = int(left_label)
        return start + 1
    return _resolve_two_digit_year(end_two)


# ---------------------------------------------------------------------------
# League-level convenience (same_year / split_year enum)
# ---------------------------------------------------------------------------


def format_season_label(end_year: int, league_season_format: str) -> str:
    """Render a season label using a league's coarse format enum.

    ``'split_year'`` -> e.g. ``2026 -> '2025-26'`` (NBA, NCAA basketball).
    ``'same_year'``  -> e.g. ``2026 -> '2026'`` (single-calendar-year leagues).
    """
    if league_season_format not in _LEAGUE_FORMAT_TO_SHAPE:
        raise ValueError(
            f"Unsupported league season_format {league_season_format!r}; "
            f"expected one of {sorted(VALID_LEAGUE_SEASON_FORMATS)}"
        )
    shape, anchor = _LEAGUE_FORMAT_TO_SHAPE[league_season_format]
    return render_season_in_shape(end_year, shape, anchor)


def parse_season_end_year(label: str, league_season_format: str) -> int:
    """Inverse of :func:`format_season_label`."""
    if league_season_format not in _LEAGUE_FORMAT_TO_SHAPE:
        raise ValueError(
            f"Unsupported league season_format {league_season_format!r}; "
            f"expected one of {sorted(VALID_LEAGUE_SEASON_FORMATS)}"
        )
    shape, anchor = _LEAGUE_FORMAT_TO_SHAPE[league_season_format]
    return parse_season_in_shape(label, shape, anchor)


# ---------------------------------------------------------------------------
# Source-level season parameter formatter (token-based)
# ---------------------------------------------------------------------------


def _format_year_token(year: int, token_len: int) -> str:
    """Format a year integer to match a token run length.

    ``token_len == 2`` -> two-digit year (``2025 -> '25'``).
    ``token_len == 4`` -> four-digit year (``2025 -> '2025'``).
    """
    if token_len == 4:
        return str(year)
    if token_len == 2:
        return f"{year % 100:02d}"
    raise ValueError(f"Unsupported token length {token_len}; expected 2 or 4")


def _replace_token_runs(param_format: str, token: str, value: str) -> str:
    """Replace contiguous runs of *token* in *param_format* with *value*."""
    result = []
    i = 0
    while i < len(param_format):
        if param_format[i] == token:
            run_len = 1
            while (
                i + run_len < len(param_format) and param_format[i + run_len] == token
            ):
                run_len += 1
            result.append(value)
            i += run_len
        else:
            result.append(param_format[i])
            i += 1
    return "".join(result)


def format_season_param(
    end_year: int,
    param_format: str,
    season_format: str,
) -> str:
    """Render a season parameter string from a token format.

    ``season_format`` is the league-level semantic format
    (``'split_year'`` or ``'same_year'``) used to derive the start year.

    Token reference:

      - ``S`` -> start year of the season
      - ``E`` -> end year of the season

    Examples for ``split_year`` with ``end_year = 2026``:

      - ``SSSS-EE`` -> ``2025-26``
      - ``SSEE``      -> ``2526``
      - ``EEEE``      -> ``2026``
      - ``EE``        -> ``26``

    For ``same_year`` start and end are identical.
    """
    if season_format not in VALID_LEAGUE_SEASON_FORMATS:
        raise ValueError(
            f"Unsupported season_format {season_format!r}; "
            f"expected one of {sorted(VALID_LEAGUE_SEASON_FORMATS)}"
        )

    start_year = end_year if season_format == "same_year" else end_year - 1

    # Determine token run lengths from the format string
    max_s = 0
    max_e = 0
    i = 0
    while i < len(param_format):
        if param_format[i] == "S":
            run_len = 1
            while i + run_len < len(param_format) and param_format[i + run_len] == "S":
                run_len += 1
            max_s = max(max_s, run_len)
            i += run_len
        elif param_format[i] == "E":
            run_len = 1
            while i + run_len < len(param_format) and param_format[i + run_len] == "E":
                run_len += 1
            max_e = max(max_e, run_len)
            i += run_len
        else:
            i += 1

    result = param_format
    if max_s > 0:
        result = _replace_token_runs(result, "S", _format_year_token(start_year, max_s))
    if max_e > 0:
        result = _replace_token_runs(result, "E", _format_year_token(end_year, max_e))
    return result
