"""
Shoot the Sheet - PBP Clock Utilities

Generic helpers for the optional per-event ``secs`` metadata on standard
PBP event streams.

Every derivation rule operates on ``seq`` -- never ``secs``.  ``secs``
is optional metadata; these helpers complete or read that metadata
without changing sequence-derived behavior.
"""

from src.definitions.pbp import PBP_CLOCK_EVENTS, PBPEvent


def fill_missing_secs(events: list[PBPEvent]) -> None:
    """Forward-fill missing ``secs`` for clock-required event types.

    Only events named by ``PBP_CLOCK_EVENTS`` (period boundaries,
    player in/out markers, possession markers) are filled -- these are
    exactly the events the clock-derived result fields read (``secs``,
    ``o_poss_secs``).  Every other event keeps its own parsed ``secs``
    (or ``None``): a shot or turnover's clock is never fabricated.

    A missing ``secs`` inherits the nearest previous timed event in the
    same period (floor fill); a period with no clock data keeps its
    events at ``secs=None`` -- a period's clock is never fabricated.
    Fully timed and fully untimed games are no-ops.  Mutates the list in
    place (metadata only; ordering and ``seq`` are untouched).
    """
    last_secs: dict[int, int] = {}
    for e in events:
        period = e["period"]
        secs = e["secs"]
        if secs is not None:
            last_secs[period] = secs
        elif e["event"] in PBP_CLOCK_EVENTS and period in last_secs:
            e["secs"] = last_secs[period]
