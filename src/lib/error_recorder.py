"""
Shoot the Sheet - Error Recorder

Provides a single write path for recording ETL errors to ``core.errors``.

The schema for the ``errors`` table is defined in
:data:`src.definitions.db_columns.DB_COLUMNS` -- this module is the consumer
that writes to it. All ETL phases should call :func:`log_error` (or
:func:`log_error_simple`) instead of writing to ``core.errors`` directly.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)

# ============================================================================
# STANDARD COLUMN ORDER (matches core.errors table in schema.py + db_columns.py)
# ============================================================================

_ERROR_COLUMNS = [
    "error_id",
    "timestamp",
    "phase",
    "entity_id",
    "error_type",
    "error_message",
    "error_traceback",
    "context",
    "entity",
    "identity",
    "dataset",
]

# System columns auto-populated on every insert.
_DEFAULT_ENTITY = "etl"


def log_error(
    *,
    phase: str,
    error_message: str,
    error_type: str = "etl_error",
    entity_id: Optional[str] = None,
    entity: Optional[str] = None,
    identity: Optional[str] = None,
    dataset: Optional[str] = None,
    error_traceback: Optional[str] = None,
    context: Optional[str] = None,
    conn: Any = None,
) -> int:
    """Insert a row into ``core.errors``.

    All fields except *phase* and *error_message* have sensible defaults.
    When *conn* is provided the insert uses that connection (caller manages
    commit); otherwise a new connection is opened and committed.

    Returns the number of rows inserted (0 or 1).
    """
    ts = datetime.now(timezone.utc).isoformat()

    data: Dict[str, Any] = {
        "timestamp": ts,
        "phase": phase,
        "entity_id": entity_id,
        "error_type": error_type,
        "error_message": error_message,
        "error_traceback": error_traceback,
        "context": context,
        "entity": entity or _DEFAULT_ENTITY,
        "identity": identity,
        "dataset": dataset,
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
    error_message: str,
    exc_info: Optional[BaseException] = None,
    **extra: str,
) -> int:
    """Convenience wrapper that accepts an exception and optional keyword fields.

    Usage::

        log_error_simple("maintain_pbp", "Failed to fetch game",
                         exc_info=e, identity="nba_id")
    """
    error_traceback = None
    if exc_info is not None:
        import traceback

        error_traceback = "".join(
            traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
        )

    return log_error(
        phase=phase,
        error_message=error_message,
        error_traceback=error_traceback,
        **extra,
    )


def log_errors_batch(
    errors: List[Dict[str, Any]],
    conn: Any = None,
) -> int:
    """Insert multiple error rows in a single batch.

    Each dict in *errors* should contain fields matching the ``core.errors``
    column names (``phase``, ``error_message``, etc.).  The ``timestamp`` is
    auto-populated if not provided, and ``entity`` defaults to ``"etl"``.
    """
    if not errors:
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    insert_cols = [c for c in _ERROR_COLUMNS if c != "error_id"]
    col_list = ", ".join(quote_col(c) for c in insert_cols)

    rows = []
    for err in errors:
        row = {
            "timestamp": err.get("timestamp", ts),
            "phase": err.get("phase", ""),
            "entity_id": err.get("entity_id"),
            "error_type": err.get("error_type", "etl_error"),
            "error_message": err.get("error_message", ""),
            "error_traceback": err.get("error_traceback"),
            "context": err.get("context"),
            "entity": err.get("entity", _DEFAULT_ENTITY),
            "identity": err.get("identity"),
            "dataset": err.get("dataset"),
        }
        rows.append(tuple(row[c] for c in insert_cols))

    from psycopg2.extras import execute_values

    def _do_batch(cur) -> int:
        execute_values(
            cur,
            f"INSERT INTO core.errors ({col_list}) VALUES %s",
            rows,
        )
        return len(rows)

    if conn is not None:
        with conn.cursor() as cur:
            return _do_batch(cur)
    else:
        with db_connection() as conn:
            with conn.cursor() as cur:
                result = _do_batch(cur)
            conn.commit()
            return result
