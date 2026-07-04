"""
Shoot the Sheet - Shared Database Primitives

Lightweight connection acquisition + identifier quoting used everywhere in
the codebase:

    get_db_connection / db_connection   - connection acquisition
    quote_col                           - identifier quoting

Higher-level concerns live elsewhere by design:
    - season helpers (static cutoff)    -> src.core.config
    - per-league season helpers         -> src.definitions
    - schema-aware table resolution     -> src.definitions
    - schema / DDL bootstrap            -> src.lib.schema_builder

All schemas share a single PostgreSQL instance.
"""

import logging
import os
from contextlib import contextmanager

import psycopg2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------


def quote_col(col: str) -> str:
    """Quote a column name for PostgreSQL.

    Always quotes so identifiers starting with a digit (``2fgm``) and
    reserved-ish names (``user``) are handled uniformly.
    """
    return f'"{col}"'


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def get_db_connection():
    """Create a new psycopg2 connection from ``DB_URL``.

    Caller is responsible for closing.  Prefer :func:`db_connection` for
    short-lived operations.
    """
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError("DB_URL environment variable is missing.")
    return psycopg2.connect(db_url)


@contextmanager
def db_connection():
    """Context-managed DB connection.

    Commits on a clean exit, rolls back on exception, and always closes.
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
