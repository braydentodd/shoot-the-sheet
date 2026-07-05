"""
Shoot the Sheet - Error Logging Utility

Centralized error capture and database logging. Provides a context manager
for ETL phases to catch and log ALL errors with full context.

Usage:
    with capture_errors(phase="maintain_games", identity="nba_id"):
        # ETL work here
        pass

All errors are logged to core.errors table with:
- Timestamp
- Phase name
- Identity
- Dataset (if applicable)
- Entity type/ID (if applicable)
- Error type (exception class name)
- Error message
- Full traceback
- JSON context (additional metadata)
"""

import json
import logging
import traceback
from contextlib import contextmanager
from typing import Any, Dict, Optional

from src.lib.postgres import db_connection

logger = logging.getLogger(__name__)


def log_error(
    error_type: str,
    error_message: str,
    *,
    phase: Optional[str] = None,
    identity: Optional[str] = None,
    dataset: Optional[str] = None,
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    error_traceback: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Write error to core.errors table.

    Args:
        error_type: Exception class name or error category
        error_message: Human-readable error message
        phase: ETL phase where error occurred
        identity: Identity code (nba_id, realgm_id, etc.)
        dataset: Dataset name
        entity: Entity type (player, team)
        entity_id: External entity ID
        error_traceback: Full traceback string
        context: Additional metadata as dict (stored as JSON)
    """
    try:
        context_json = json.dumps(context) if context else None

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.errors (
                        phase, identity, dataset, entity, entity_id,
                        error_type, error_message, error_traceback, context
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        phase,
                        identity,
                        dataset,
                        entity,
                        entity_id,
                        error_type,
                        error_message,
                        error_traceback,
                        context_json,
                    ),
                )
            conn.commit()
    except Exception as e:
        logger.error("Failed to log error to database: %s", e, exc_info=True)


@contextmanager
def capture_errors(
    phase: Optional[str] = None,
    identity: Optional[str] = None,
    dataset: Optional[str] = None,
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = True,
):
    """Context manager to capture and log errors.

    Args:
        phase: ETL phase name
        identity: Identity code
        dataset: Dataset name
        entity: Entity type (player, team)
        entity_id: External entity ID
        context: Additional metadata
        reraise: If True, re-raise caught exceptions after logging

    Usage:
        with capture_errors(phase="maintain_games", identity="nba_id"):
            # Work that might fail
            pass
    """
    try:
        yield
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        error_traceback = traceback.format_exc()

        logger.error(
            "Error in %s: %s",
            phase or "unknown_phase",
            error_message,
            exc_info=True,
        )

        log_error(
            error_type=error_type,
            error_message=error_message,
            phase=phase,
            identity=identity,
            dataset=dataset,
            entity=entity,
            entity_id=entity_id,
            error_traceback=error_traceback,
            context=context,
        )

        if reraise:
            raise
