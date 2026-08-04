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
from src.sources.nba_data.config import (
    COL,
    FOUL_TAXONOMY,
    MSG,
    PERSON_NONE,
)

logger = logging.getLogger(__name__)

# Canonical foul events (the only supported foul vocabulary).
_FOUL_EVENTS = ("standard_foul", "elevated_foul")


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
        List of PBPEvent rows sorted by (secs, sort_priority, eventnum).
    """
    events: list[PBPEvent] = []

    reg_len, ot_len = _infer_period_lengths(rows)

    for row in rows:
        eventnum = _to_int(row.get(COL["EVENTNUM"]))
        period = _to_int(row.get(COL["PERIOD"]))
        pctime = _to_str(row.get(COL["PCTIMESTRING"]))
        event_id = str(eventnum)

        p1_id = _to_str(row.get(COL["PLAYER1_ID"]))
        p1_type = _to_int(row.get(COL["PERSON1TYPE"]))
        p2_id = _to_str(row.get(COL["PLAYER2_ID"]))
        p2_type = _to_int(row.get(COL["PERSON2TYPE"]))
        p3_id = _to_str(row.get(COL["PLAYER3_ID"]))
        p3_type = _to_int(row.get(COL["PERSON3TYPE"]))
        p3_team = _to_str(row.get(COL["PLAYER3_TEAM_ID"]))

        actiontype = _to_int(row.get(COL["EVENTMSGACTIONTYPE"]))

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
        elif handling in _FOUL_EVENTS:
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

        def _mk(
            event: str,
            team_id: str,
            player_id: str,
            *,
            chain_id: str | None = None,
        ) -> PBPEvent:
            return {
                "identity": identity,
                "game_id": game_id,
                "event_id": event_id,
                "seq": 0,
                "secs": secs,
                "period": period,
                "team_id": team_id,
                "player_id": player_id,
                "event": event,
                "chain_id": chain_id,
                "source": event_id,
            }

        # ── Fouls: emit the canonical foul + the fouled player ---------
        if handling in _FOUL_EVENTS:
            # Source-taxonomy cross-check: the catalog handling must
            # agree with the source's declarative foul semantics.
            expected = FOUL_TAXONOMY.get(actiontype)
            if expected is not None and expected != handling:
                logger.warning(
                    "Foul taxonomy mismatch in game %s event %s: "
                    "catalog handling=%s but FOUL_TAXONOMY[%s]=%s",
                    game_id, eventnum, handling, actiontype, expected,
                )
            events.append(_mk(handling, player_team, player, chain_id=event_id))
            if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                fouled_type, fouled_team = entity_resolver(p2_id)
                if fouled_type == "player" and fouled_team:
                    opp_team = _opponent(player_team, home_team_id, away_team_id)
                    events.append(_mk(
                        "o_foul_draw", opp_team, p2_id, chain_id=event_id,
                    ))
            continue

        # ── Rebounds: neutral event; off/def is chain-derived ----------
        if handling == "rebound":
            reb_player_id = "" if entity_type == "team" else p1_id
            events.append(_mk("rebound", player_team, reb_player_id))
            continue

        # ── Substitutions: player_out then player_in (same row) --------
        if handling == "substitution":
            if p2_id and p2_id != "0":
                events.append(_mk("player_in", player_team, p2_id, chain_id=event_id))
            if p1_id and p1_id != "0":
                events.append(_mk("player_out", player_team, p1_id, chain_id=event_id))
            continue

        # ── Turnovers: emit the turnover + any steal attribution -------
        if handling == "turnover":
            events.append(_mk("turnover", player_team, player, chain_id=event_id))
            if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                steal_type, steal_team = entity_resolver(p2_id)
                if steal_type == "player" and steal_team:
                    events.append(_mk("steal", steal_team, p2_id, chain_id=event_id))
            continue

        # ── Field goals: emit the attempt + assist/block attributions --
        if handling in ("fg2_make", "fg3_make", "fg2_miss", "fg3_miss"):
            events.append(_mk(handling, player_team, player, chain_id=event_id))
            if handling.endswith("_make"):
                if p2_type != PERSON_NONE and p2_id and p2_id != "0":
                    assist_type, assist_team = entity_resolver(p2_id)
                    if assist_type == "player" and assist_team:
                        assist_evt = "fg3_assist" if handling == "fg3_make" else "fg2_assist"
                        events.append(_mk(assist_evt, assist_team, p2_id,
                                          chain_id=event_id))
            else:
                if p3_type != PERSON_NONE and p3_id and p3_id != "0":
                    block_type, block_team = entity_resolver(p3_id)
                    if block_type == "player" and block_team:
                        events.append(_mk("block", block_team, p3_id,
                                          chain_id=event_id))
            continue

        # ── Jump ball win (PLAYER3 = winner) ---------------------------
        if handling == "jump_ball_win":
            if p3_id and p3_id != "0":
                _, tip_team = entity_resolver(p3_id)
                tip_team = p3_team or tip_team
                if tip_team:
                    events.append(_mk("jump_ball_win", tip_team, "", chain_id=event_id))
            continue

        # ── System events ----------------------------------------------
        if handling in ("period_start", "period_end"):
            events.append(_mk(handling, "", "", chain_id=event_id))
            continue

        # ── All other direct canonical events (FTs, free throws, ...) --
        if handling in PBP_EVENTS:
            events.append(_mk(handling, player_team, player))
        else:
            logger.debug(
                "Skipping unknown handling %r in game %s event %s",
                handling, game_id, eventnum,
            )

    if all(e.get("secs") is not None for e in events):
        # Arrival order is authoritative within the same second (the
        # user rule: "rebounds and shots at the same sec keep the order
        # they came in").  sort_priority documents the intended
        # same-second ordering but never overrides the feed order.
        events.sort(key=lambda e: (e["secs"], int(e["event_id"]) if e["event_id"].isdigit() else 0))
    for i, e in enumerate(events):
        e["seq"] = i
    return events


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _parse_pctime(pctimestring: str) -> int:
    """Parse a PCTIMESTRING (e.g. ``"12:00"``) into raw seconds.

    Returns 0 on parse failure.
    """
    try:
        parts = pctimestring.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 0


def _infer_period_lengths(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Infer regulation and overtime period lengths from the data.

    Reads PCTIMESTRING from period_start events (EVENTMSGTYPE=12).
    Falls back to max PCTIMESTRING seen in period 1 / first OT period.
    """
    reg_len = 0
    ot_len = 0
    for row in rows:
        msgtype = _to_int(row.get(COL["EVENTMSGTYPE"]))
        period = _to_int(row.get(COL["PERIOD"]))
        pctime = _to_str(row.get(COL["PCTIMESTRING"]))
        secs = _parse_pctime(pctime)
        if secs == 0:
            continue
        if msgtype == MSG.PERIOD_START:
            if period == 1:
                reg_len = secs
            elif period >= 5 and ot_len == 0:
                ot_len = secs
        elif period == 1 and secs > reg_len:
            reg_len = secs
        elif period >= 5 and secs > ot_len:
            ot_len = secs
    if reg_len == 0:
        reg_len = 720
    if ot_len == 0:
        ot_len = 300
    return reg_len, ot_len


def _pctime_to_secs(
    period: int, pctimestring: str, reg_len: int, ot_len: int,
) -> int:
    """Convert PERIOD + PCTIMESTRING to elapsed game-clock seconds."""
    remaining = _parse_pctime(pctimestring)

    if period <= 4:
        base = (period - 1) * reg_len
        elapsed_in_period = reg_len - remaining
    else:
        base = 4 * reg_len + (period - 5) * ot_len
        elapsed_in_period = ot_len - remaining

    return base + elapsed_in_period


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


def _to_int(val: Any) -> int:
    """Coerce a value to int, returning 0 for empty/missing."""
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _to_str(val: Any) -> str:
    """Coerce a value to str, returning '' for None."""
    if val is None:
        return ""
    return str(val)
