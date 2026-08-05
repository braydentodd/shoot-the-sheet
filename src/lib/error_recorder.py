"""
Shoot the Sheet - Error Recorder

Single home for the ETL error model and the one write path for
recording errors to ``core.errors``.

The schema for the ``errors`` table is defined in
:data:`src.definitions.db_columns.DB_COLUMNS` -- this module derives its
column list from that registry (the single source of truth) and is the
only consumer that writes to the table.  All ETL phases should call
:func:`log_error` instead of writing to ``core.errors`` directly.

PBP derivation errors (:class:`PbpError`) carry game context
(``identity``, ``dataset``, ``ext_game_id``, ``event_id``, ``seq``,
``event``) plus a ``severity`` taken from the ``INVARIANTS`` config, so
each error is traceable to the exact event and its severity is
config-driven.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.definitions.db_columns import DB_COLUMNS
from src.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)

# ============================================================================
# ERROR MODEL
# ============================================================================


@dataclass(frozen=True)
class PbpError:
    """A single PBP derivation error or invariant violation.

    Attributes:
        rule: The ``INVARIANTS`` key or chain rule that fired.
        message: Human-readable description.
        severity: ``"error"`` fails the game; ``"warn"`` logs loudly.
            Taken from the fired invariant's config.
        game_id: External game id.
        event_id: Id of the offending event (source id or derived id).
        seq: Sequence position of the offending event.
        event: Canonical event name of the offending event.
        team_id: Team id of the offending event.
        player_id: Player id of the offending event.
    """

    rule: str
    message: str
    severity: str = "error"
    game_id: str = ""
    event_id: str | None = None
    seq: int | None = None
    event: str | None = None
    team_id: str | None = None
    player_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# WRITE PATH
# ============================================================================

# Column order for core.errors, derived from DB_COLUMNS so the insert
# statement can never drift from the registry.
_ERROR_COLUMNS: tuple[str, ...] = tuple(
    name
    for name, meta in DB_COLUMNS.items()
    if "errors" in (meta.get("tables") if isinstance(meta.get("tables"), list) else [meta.get("tables")])
)


def log_error(
    *,
    phase: str,
    message: str,
    traceback: Optional[str] = None,
    conn: Any = None,
    identity: Optional[str] = None,
    dataset: Optional[str] = None,
    ext_game_id: Optional[str] = None,
    event_id: Optional[str] = None,
    seq: Optional[int] = None,
    event: Optional[str] = None,
) -> int:
    """Insert a row into ``core.errors``.

    Args:
        phase: Which ETL phase produced the error (e.g. ``"maintain_games"``).
        message: Human-readable error description. Include identifying
            context (entity, identity, dataset) in the message itself.
        traceback: Optional Python stack trace.
        conn: Optional database connection. When provided the caller manages
            commit; otherwise a new connection is opened and committed.
        identity: Identity code the error belongs to.
        dataset: Dataset name the error belongs to.
        ext_game_id: External game id the error belongs to.
        event_id: Offending PBP event id.
        seq: Sequence position of the offending event.
        event: Canonical event name of the offending event.

    Returns the number of rows inserted (0 or 1).
    """
    data: Dict[str, Any] = {
        "phase": phase,
        "message": message,
        "traceback": traceback,
        "identity": identity,
        "dataset": dataset,
        "ext_game_id": ext_game_id,
        "event_id": event_id,
        "seq": seq,
        "event": event,
    }

    # error_id is auto-assigned by the sequence default
    insert_cols = [c for c in _ERROR_COLUMNS if c != "error_id"]
    col_list = ", ".join(quote_col(c) for c in insert_cols)
    placeholders = ", ".join(f"%({c})s" for c in insert_cols)

    def _do_insert(cur) -> int:
        cur.execute(
            f"""
            INSERT INTO core.errors ({col_list})
            VALUES ({placeholders})
            """,
            data,
        )
        return cur.rowcount

    if conn is not None:
        with conn.cursor() as cur:
            return _do_insert(cur)
    else:
        with db_connection() as conn:
            with conn.cursor() as cur:
                result = _do_insert(cur)
            conn.commit()
            return result


def log_error_simple(
    phase: str,
    message: str,
    exc_info: Optional[BaseException] = None,
    **context: Optional[str],
) -> int:
    """Convenience wrapper that accepts an exception.

    Usage::

        log_error_simple("maintain_pbp", "Failed to fetch game 0022400001",
                         exc_info=e, ext_game_id="0022400001")

    Additional keyword arguments are forwarded to :func:`log_error`
    (``identity``, ``dataset``, ``ext_game_id``, ``event_id``, ``seq``,
    ``event``).
    """
    traceback = None
    if exc_info is not None:
        import traceback as tb

        traceback = "".join(
            tb.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
        )

    return log_error(
        phase=phase,
        message=message,
        traceback=traceback,
        **context,
    )
