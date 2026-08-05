"""
Shoot the Sheet - nbastats CSV PBP Normalizer

Converts raw nbastats CSV rows into source-agnostic :class:`PBPEvent`
rows consumed by the derivation engine and accumulator.

Event classification is driven by ``core.pbp_events`` via the
:class:`~src.lib.pbp_classifier.EventClassifier`.  The classifier
replaces the previous hardcoded ``if msgtype == ...`` chain.

Pure functions -- no side effects, no I/O.
"""

import logging
from typing import Any

from src.definitions.pbp import PBP_EVENTS, PBPEvent
from src.lib.entity_resolver import EntityResolver
from src.lib.pbp_classifier import EventClassifier, UnclassifiedEventError
from src.lib.transform import to_int, to_str
from src.sources.nba_data.config import (
    COL,
    MSG,
    PERSON_NONE,
)

logger = logging.getLogger(__name__)

# Canonical foul events the source can emit -- derived from ``PBP_EVENTS``
# (every event whose ``foul_family`` is not ``"none"``) so the vocabulary
# can never drift from the canonical config.  The source has no foul map
# of its own; ``core.pbp_events`` (via the classifier) is the single
# authority.
_FOUL_TYPES: frozenset[str] = frozenset(
    name for name, ev_def in PBP_EVENTS.items()
    if ev_def["foul_family"] != "none"
)


# ============================================================================
# PUBLIC ENTRY POINT
# ============================================================================


def normalize_game(
    rows: list[dict[str, Any]],
    game_id: str,
    home_team_id: str,
    away_team_id: str,
    entity_resolver: EntityResolver,
    classifier: EventClassifier,
    identity: str = "nba_id",
) -> list[PBPEvent]:
    """Normalize nbastats CSV rows into standard PBPEvent rows.

    Args:
        rows: Raw CSV rows for a single game (list of dicts keyed by
              COL constants).  Must be sorted by EVENTNUM ascending.
        game_id: External game ID (e.g. ``"22400001"``).
        home_team_id: External home team ID.
        away_team_id: External away team ID.
        entity_resolver: Callable for staging-table entity lookup.
        classifier: EventClassifier loaded from ``core.pbp_events``.
        identity: Identity code for the event's ``identity`` field.

    Returns:
        List of PBPEvent rows in feed order.  ``secs`` holds elapsed
        game-clock seconds parsed per event (``None`` where the clock is
        missing or the period family's length is unknown).  A game with
        any untimed event stays in feed order; a fully timed game is
        clock-ordered.
    """
    events: list[PBPEvent] = []

    reg_len, ot_len = _infer_period_lengths(rows)

    for row in rows:
        eventnum = to_int(row.get(COL["EVENTNUM"]))
        period = to_int(row.get(COL["PERIOD"]))
        pctime = to_str(row.get(COL["PCTIMESTRING"]))
        event_id = str(eventnum)

        p1_id = to_str(row.get(COL["PLAYER1_ID"]))
        p1_type = to_int(row.get(COL["PERSON1TYPE"]))
        p2_id = to_str(row.get(COL["PLAYER2_ID"]))
        p2_type = to_int(row.get(COL["PERSON2TYPE"]))
        p3_id = to_str(row.get(COL["PLAYER3_ID"]))
        p3_type = to_int(row.get(COL["PERSON3TYPE"]))
        p3_team = to_str(row.get(COL["PLAYER3_TEAM_ID"]))

        secs = _pctime_to_secs(period, pctime, reg_len, ot_len)

        # Classify first -- system events don't need entity resolution.
        try:
            classification = classifier.classify(row)
        except UnclassifiedEventError:
            continue

        if classification.is_ignore:
            continue

        handling = classification.handling

        # Resolve the primary entity (skip for system events).  Fouls are
        # emitted even when the committer is unresolvable (bench players
        # and coaches commit technicals and are not staging entities) so
        # their free throws still chain to a foul.
        if handling in ("period_start", "period_end"):
            entity_type = "system"
            resolved_team = ""
        elif handling in _FOUL_TYPES:
            entity_type, resolved_team = entity_resolver(p1_id)
            if entity_type is None or resolved_team is None:
                entity_type = "unknown"
                resolved_team = ""
        else:
            entity_type, resolved_team = entity_resolver(p1_id)
            if entity_type is None or resolved_team is None:
                logger.debug(
                    "Unknown entity %r (PERSON1TYPE=%s) in game %s event %s",
                    p1_id, p1_type, game_id, eventnum,
                )
                continue
        player_team = resolved_team
        player = "" if entity_type == "team" else p1_id

        # Row context shared by every event emitted from this raw row.
        # Passed explicitly to the module-level ``_mk_event`` so no loop
        # variables are captured late (the previous inline closure bound
        # ``event_id``/``secs``/``period`` by reference).
        base = {
            "identity": identity,
            "game_id": game_id,
            "event_id": event_id,
            "seq": 0,
            "secs": secs,
            "period": period,
            "source": event_id,
        }

        # ── Fouls: emit the canonical foul + the fouled player ---------
        if handling in _FOUL_TYPES:
            # Resolve the fouled player (PLAYER2) when the source provides
            # one; the catalog handling is the sole authority on semantics.
            fouled_id: str | None = None
            if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                fouled_type, fouled_team = entity_resolver(p2_id)
                if fouled_type == "player" and fouled_team:
                    fouled_id = p2_id
            # Standard fouls carry the fouled player on the event itself
            # (``fouled_player_id``); offensive fouls additionally credit
            # the defender who drew them via ``o_foul_draw``.  Elevated
            # fouls (bench technicals, coach Ts) have no player to credit.
            events.append(_mk_event(
                base, handling, player_team, player,
                chain_id=event_id,
                fouled_player_id=fouled_id if handling != "elevated_foul" else None,
            ))
            if handling == "o_standard_foul" and fouled_id:
                opp_team = _opponent(player_team, home_team_id, away_team_id)
                events.append(_mk_event(
                    base, "o_foul_draw", opp_team, fouled_id, chain_id=event_id,
                ))
            continue

        # ── Rebounds: neutral event; off/def is chain-derived ----------
        if handling == "rebound":
            reb_player_id = "" if entity_type == "team" else p1_id
            events.append(_mk_event(base, "rebound", player_team, reb_player_id))
            continue

        # ── Substitutions: player_out then player_in (same row) --------
        if handling == "substitution":
            if p2_id and p2_id != "0":
                events.append(_mk_event(
                    base, "player_in", player_team, p2_id, chain_id=event_id,
                ))
            if p1_id and p1_id != "0":
                events.append(_mk_event(
                    base, "player_out", player_team, p1_id, chain_id=event_id,
                ))
            continue

        # ── Turnovers: emit the turnover + any steal attribution -------
        if handling == "turnover":
            events.append(_mk_event(base, "turnover", player_team, player,
                                    chain_id=event_id))
            if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                steal_type, steal_team = entity_resolver(p2_id)
                if steal_type == "player" and steal_team:
                    events.append(_mk_event(
                        base, "steal", steal_team, p2_id, chain_id=event_id,
                    ))
            continue

        # ── Field goals: emit the attempt + assist/block attributions --
        if handling in ("fg2_make", "fg3_make", "fg2_miss", "fg3_miss"):
            events.append(_mk_event(base, handling, player_team, player,
                                    chain_id=event_id))
            if handling.endswith("_make"):
                if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                    assist_type, assist_team = entity_resolver(p2_id)
                    if assist_type == "player" and assist_team:
                        assist_evt = "fg3_assist" if handling == "fg3_make" else "fg2_assist"
                        events.append(_mk_event(
                            base, assist_evt, assist_team, p2_id, chain_id=event_id,
                        ))
            else:
                if p3_type != PERSON_NONE and p3_id and p3_id != "0":
                    block_type, block_team = entity_resolver(p3_id)
                    if block_type == "player" and block_team:
                        events.append(_mk_event(
                            base, "block", block_team, p3_id, chain_id=event_id,
                        ))
            continue

        # ── Jump ball win (PLAYER3 = winner) ---------------------------
        if handling == "jump_ball_win":
            if p3_id and p3_id != "0":
                _, tip_team = entity_resolver(p3_id)
                tip_team = p3_team or tip_team
                if tip_team:
                    events.append(_mk_event(
                        base, "jump_ball_win", tip_team, "", chain_id=event_id,
                    ))
            continue

        # ── System events ----------------------------------------------
        if handling in ("period_start", "period_end"):
            events.append(_mk_event(base, handling, "", "", chain_id=event_id))
            continue

        # ── All other direct canonical events (FTs, free throws, ...) --
        if handling in PBP_EVENTS:
            events.append(_mk_event(base, handling, player_team, player))
        else:
            logger.debug(
                "Skipping unknown handling %r in game %s event %s",
                handling, game_id, eventnum,
            )

    # ``secs`` is per-event metadata: every parseable clock is preserved
    # and events without a usable clock carry ``secs=None`` (the deriver's
    # clock-completion pass fills gaps from the nearest previous timed
    # event in the same period).  A fully timed game is clock-ordered
    # (same-second events keep EVENTNUM arrival order); any untimed event
    # keeps the game in feed order.
    if all(e.get("secs") is not None for e in events):
        events.sort(key=lambda e: (e.get("secs"), _event_order(e.get("event_id"))))
    for i, e in enumerate(events):
        e["seq"] = i
    return events


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _mk_event(
    base: dict[str, Any],
    event: str,
    team_id: str,
    player_id: str,
    *,
    chain_id: str | None = None,
    fouled_player_id: str | None = None,
) -> PBPEvent:
    """Build a standard PBPEvent row from a raw row's shared context.

    ``base`` holds the per-row constants (``identity``, ``game_id``,
    ``event_id``, ``seq``, ``secs``, ``period``, ``source``); the event
    identity varies per call.  Module-level so no loop variables are
    captured late.
    """
    return {
        "identity": base["identity"],
        "game_id": base["game_id"],
        "event_id": base["event_id"],
        "seq": base["seq"],
        "secs": base["secs"],
        "period": base["period"],
        "team_id": team_id,
        "player_id": player_id,
        "event": event,
        "chain_id": chain_id,
        "fouled_player_id": fouled_player_id,
        "source": base["source"],
    }


def _parse_pctime(pctimestring: str) -> int | None:
    """Parse a PCTIMESTRING (e.g. ``"12:00"``) into raw remaining seconds.

    Returns ``None`` when the string does not parse.  ``0`` is a valid
    remaining value (``"0:00"``), so it is never used as a failure
    sentinel.
    """
    try:
        parts = pctimestring.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


def _infer_period_lengths(rows: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    """Infer regulation and overtime period lengths from the data.

    Reads PCTIMESTRING from period_start events (EVENTMSGTYPE=12);
    falls back to the max PCTIMESTRING seen in period 1 / the first OT
    period.  Never assumes league defaults: a length the data cannot
    establish is reported as ``None`` and events in that period family
    carry ``secs=None``, so clock-less or partially clocked sources work
    by design.
    """
    reg_len: int | None = None
    ot_len: int | None = None
    for row in rows:
        msgtype = to_int(row.get(COL["EVENTMSGTYPE"]))
        period = to_int(row.get(COL["PERIOD"]))
        pctime = to_str(row.get(COL["PCTIMESTRING"]))
        secs = _parse_pctime(pctime)
        # A zero remaining clock carries no length signal.
        if secs is None or secs == 0:
            continue
        if msgtype == MSG.PERIOD_START:
            if period == 1:
                reg_len = secs
            elif period >= 5 and ot_len is None:
                ot_len = secs
        elif period == 1 and (reg_len is None or secs > reg_len):
            reg_len = secs
        elif period >= 5 and (ot_len is None or secs > ot_len):
            ot_len = secs
    return reg_len, ot_len


def _pctime_to_secs(
    period: int, pctimestring: str, reg_len: int | None, ot_len: int | None,
) -> int | None:
    """Convert PERIOD + PCTIMESTRING to elapsed game-clock seconds.

    Returns ``None`` when the clock string does not parse or the period
    family's length is unknown (per-event clock metadata).
    """
    remaining = _parse_pctime(pctimestring)
    if remaining is None:
        return None

    if period <= 4:
        if reg_len is None:
            return None
        base = (period - 1) * reg_len
        elapsed_in_period = reg_len - remaining
    else:
        if reg_len is None or ot_len is None:
            return None
        base = 4 * reg_len + (period - 5) * ot_len
        elapsed_in_period = ot_len - remaining

    return base + elapsed_in_period


def _event_order(event_id: str | None) -> int:
    """Stable tiebreaker for same-second events (EVENTNUM arrival order)."""
    return int(event_id) if event_id and event_id.isdigit() else 0


def _opponent(
    team_id: str,
    home_team_id: str,
    away_team_id: str,
) -> str:
    """Return the opposing team ID."""
    if team_id == home_team_id:
        return away_team_id
    if team_id == away_team_id:
        return home_team_id
    return ""
