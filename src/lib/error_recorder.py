"""
Shoot the Sheet - Error Recorder

Provides a single write path for recording ETL errors to ``core.errors``.

The schema for the ``errors`` table is defined in
:data:`src.definitions.db_columns.DB_COLUMNS` -- this module is the consumer
that writes to it. All ETL phases should call :func:`log_error` instead of
writing to ``core.errors`` directly.
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
]


def log_error(
    *,
    phase: str,
    message: str,
    traceback: Optional[str] = None,
    conn: Any = None,
) -> int:
    """Insert a row into ``core.errors``.

    Args:
        phase: Which ETL phase produced the error (e.g. ``"maintain_games"``).
        message: Human-readable error description. Include identifying
            context (entity, identity, dataset) in the message itself.
            No category prefix -- use the phase parameter and message text
            for filtering.
        traceback: Optional Python stack trace.
        conn: Optional database connection. When provided the caller manages
            commit; otherwise a new connection is opened and committed.

    Returns the number of rows inserted (0 or 1).
    """
    data: Dict[str, Any] = {
        "phase": phase,
        "message": message,
        "traceback": traceback,
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
) -> int:
    """Convenience wrapper that accepts an exception.

    Usage::

        log_error_simple("maintain_pbp", "Failed to fetch game 0022400001",
                         exc_info=e)
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
    )
