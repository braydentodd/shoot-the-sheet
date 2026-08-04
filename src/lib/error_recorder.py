"""
Shoot the Sheet - Error Recorder

Provides a single write path for recording ETL errors to ``core.errors``.

The schema for the ``errors`` table is defined in
:data:`src.definitions.db_columns.DB_COLUMNS` -- this module is the consumer
that writes to it. All ETL phases should call :func:`log_error` instead of
writing to ``core.errors`` directly.

PBP derivation errors carry game context (``identity``, ``dataset``,
``ext_game_id``, ``event_id``, ``seq``, ``event``) so each error is
traceable to the exact event.
"""

import logging
from typing import Any, Dict, Optional

from src.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)

# ============================================================================
# STANDARD COLUMN ORDER (matches core.errors table in schema.py + db_columns.py)
# ============================================================================

_ERROR_COLUMNS = [
    "error_id",
    "phase",
    "message",
    "traceback",
    "identity",
    "dataset",
    "ext_game_id",
    "event_id",
    "seq",
    "event",
]


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
