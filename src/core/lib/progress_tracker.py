"""
The Glass - Generic Progress Tracking

Database operations for tracking pipeline run state and per-item progress.
Uses the unified ``runs`` and ``tasks`` tables.

Each task row uses an ``item_key`` that encodes the work unit. The encoding
is pipeline-specific and provided by the caller.

Supports auto-resume: if a run was interrupted mid-flight, the runner
can detect the orphaned 'running' record and resume from the last
pending item.
"""

import logging
from typing import Any, Callable, List, Tuple, Union

logger = logging.getLogger(__name__)


# ============================================================================
# RUN LIFECYCLE
# ============================================================================


def create_run(
    conn: Any,
    db_schema: str,
    pipeline: str,
    entity_type: str,
    total_items: int,
    **metadata: Any,
) -> int:
    """Insert a new runs record and return the process id.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        pipeline: Pipeline identifier (e.g., 'etl', 'publish')
        entity_type: Type of entity being processed
        total_items: Total number of items to process
        **metadata: Additional pipeline-specific metadata (season, season_type, etc.)
    
    Returns:
        The run process id
    """
    # Build INSERT with dynamic metadata fields
    metadata_cols = list(metadata.keys())
    metadata_vals = list(metadata.values())
    
    cols = ['pipeline', 'entity_type', 'total_items'] + metadata_cols
    placeholders = ['%s'] * len(cols)
    
    query = (
        f"INSERT INTO {db_schema}.runs "
        f"({', '.join(cols)}) "
        f"VALUES ({', '.join(placeholders)}) RETURNING process_id"
    )
    
    vals = [pipeline, entity_type, total_items] + metadata_vals
    
    with conn.cursor() as cur:
        cur.execute(query, vals)
        process_id = cur.fetchone()[0]
    conn.commit()
    logger.info('Created %s run %d for %s', pipeline, process_id, entity_type)
    return process_id


def complete_run(
    conn: Any,
    db_schema: str,
    process_id: int,
    pipeline: str,
    **metadata: Any,
) -> None:
    """Mark a run as completed.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        process_id: Run process id to complete
        pipeline: Pipeline identifier
        **metadata: Additional fields to update (total_rows, etc.)
    """
    # Build UPDATE with dynamic metadata fields
    metadata_cols = list(metadata.keys())
    metadata_vals = list(metadata.values())
    
    updates = ["status = 'completed'", "completed_at = NOW()"]
    if metadata_cols:
        updates.extend([f"{col} = %s" for col in metadata_cols])
    
    query = (
        f"UPDATE {db_schema}.runs "
        f"SET {', '.join(updates)} "
        f"WHERE process_id = %s AND pipeline = %s"
    )
    
    vals = metadata_vals + [process_id, pipeline]
    
    with conn.cursor() as cur:
        cur.execute(query, vals)
    conn.commit()


def fail_run(
    conn: Any,
    db_schema: str,
    process_id: int,
    pipeline: str,
    error_message: str,
) -> None:
    """Mark a run as failed.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        process_id: Run process id to fail
        pipeline: Pipeline identifier
        error_message: Error message to store
    """
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {db_schema}.runs "
            f"SET status = 'failed', completed_at = NOW(), error_message = %s "
            f"WHERE process_id = %s AND pipeline = %s",
            (error_message, process_id, pipeline),
        )
    conn.commit()


# ============================================================================
# TASKS
# ============================================================================


def register_tasks(
    conn: Any,
    db_schema: str,
    run_process_id: int,
    pipeline: str,
    item_keys: List[str],
    **metadata: Any,
) -> List[int]:
    """Insert task rows for each item. Returns task process ids.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        run_process_id: Run process id
        pipeline: Pipeline identifier
        item_keys: List of item keys to register
        **metadata: Additional fields to insert (entity_type, etc.)
    
    Returns:
        List of task process ids
    """
    task_process_ids: List[int] = []
    
    # Build INSERT with dynamic metadata fields
    metadata_cols = list(metadata.keys())
    metadata_vals = list(metadata.values())
    
    cols = ['run_id', 'pipeline', 'item_key'] + metadata_cols
    placeholders = ['%s'] * len(cols)
    
    query = (
        f"INSERT INTO {db_schema}.tasks "
        f"({', '.join(cols)}) "
        f"VALUES ({', '.join(placeholders)}) RETURNING process_id"
    )
    
    with conn.cursor() as cur:
        for item_key in item_keys:
            vals = [run_process_id, pipeline, item_key] + metadata_vals
            cur.execute(query, vals)
            task_process_ids.append(cur.fetchone()[0])
    conn.commit()
    return task_process_ids


def mark_task_process_started(conn: Any, db_schema: str, task_process_id: int) -> None:
    """Mark a task entry as running.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        task_process_id: Task process id to mark as started
    """
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {db_schema}.tasks "
            f"SET status = 'running'"
            f"WHERE process_id = %s",
            (task_process_id,),
        )
    conn.commit()


def mark_task_process_completed(
    conn: Any,
    db_schema: str,
    task_process_id: int,
    **metadata: Any,
) -> None:
    """Mark a task entry as completed.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        task_process_id: Task process id to mark as completed
        **metadata: Additional fields to update (rows_written, etc.)
    """
    # Build UPDATE with dynamic metadata fields
    metadata_cols = list(metadata.keys())
    metadata_vals = list(metadata.values())
    
    updates = ["status = 'completed'", "completed_at = NOW()"]
    if metadata_cols:
        updates.extend([f"{col} = %s" for col in metadata_cols])
    
    query = (
        f"UPDATE {db_schema}.tasks "
        f"SET {', '.join(updates)} "
        f"WHERE process_id = %s"
    )
    
    vals = metadata_vals + [task_process_id]
    
    with conn.cursor() as cur:
        cur.execute(query, vals)
    conn.commit()


def mark_task_process_failed(
    conn: Any,
    db_schema: str,
    task_process_id: int,
    error_message: str,
) -> None:
    """Mark a task entry as failed and increment retry count.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        task_process_id: Task process id to mark as failed
        error_message: Error message to store
    """
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {db_schema}.tasks "
            f"SET status = 'failed', completed_at = NOW(), "
            f"error_message = %s, retry_count = retry_count + 1 "
            f"WHERE process_id = %s",
            (error_message, task_process_id),
        )
    conn.commit()


# ============================================================================
# AUTO-RESUME
# ============================================================================


def find_resumable_run(
    conn: Any,
    db_schema: str,
    pipeline: str,
    **filters: Any,
) -> Union[int, None]:
    """Find an interrupted run matching the given filters.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        pipeline: Pipeline identifier
        **filters: Additional filter conditions (entity_type, season, season_type, etc.)
    
    Returns:
        The run process id if a 'running' record exists, else None
    """
    filter_cols = list(filters.keys())
    filter_vals = list(filters.values())
    
    where_clauses = ["pipeline = %s", "status = 'running'"] + [f"{col} = %s" for col in filter_cols]
    query = (
        f"SELECT process_id FROM {db_schema}.runs "
        f"WHERE {' AND '.join(where_clauses)} "
        f"ORDER BY created_at DESC LIMIT 1"
    )
    
    vals = [pipeline] + filter_vals
    
    with conn.cursor() as cur:
        cur.execute(query, vals)
        row = cur.fetchone()
    return row[0] if row else None


def get_pending_task_process_ids(
    conn: Any,
    db_schema: str,
    run_process_id: int,
    pipeline: str,
) -> List[Tuple[int, str]]:
    """Return (task_process_id, item_key) for incomplete items.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        run_process_id: Run process id
        pipeline: Pipeline identifier
    
    Returns:
        List of (task_process_id, item_key) for items with status 'pending' or 'running'
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT process_id, item_key FROM {db_schema}.tasks "
            f"WHERE run_id = %s AND pipeline = %s AND status IN ('pending', 'running') "
            f"ORDER BY process_id",
            (run_process_id, pipeline),
        )
        return cur.fetchall()


def update_run_completed_items(
    conn: Any,
    db_schema: str,
    process_id: int,
    pipeline: str,
) -> None:
    """Sync the completed_items counter on the run record.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        process_id: Run process id
        pipeline: Pipeline identifier
    """
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {db_schema}.runs SET completed_items = ("
            f"  SELECT COUNT(*) FROM {db_schema}.tasks "
            f"  WHERE run_id = %s AND pipeline = %s AND status = 'completed'"
            f") WHERE process_id = %s AND pipeline = %s",
            (process_id, pipeline, process_id, pipeline),
        )
    conn.commit()


# ============================================================================
# WORK RESOLUTION
# ============================================================================


def resolve_work(
    conn: Any,
    db_schema: str,
    pipeline: str,
    items: List[Any],
    item_key_fn: Callable[[Any], str],
    auto_resume: bool,
    **filters: Any,
) -> Tuple[int, List[Tuple[Any, int]]]:
    """Determine the run process id and pending work items for a pipeline run.
    
    If *auto_resume* is enabled and an interrupted run exists matching the filters,
    resumes from the last pending item. Otherwise creates a fresh run.
    
    Args:
        conn: Database connection
        db_schema: Database schema name
        pipeline: Pipeline identifier
        items: List of work items (tabs, groups, etc.)
        item_key_fn: Function to convert an item to its item_key string
        auto_resume: Whether to attempt auto-resume
        **filters: Additional filters for finding resumable runs (entity_type, season, etc.)
    
    Returns:
        (run_process_id, [(item, task_process_id), ...])
    """
    if auto_resume:
        run_process_id = find_resumable_run(conn, db_schema, pipeline, **filters)
        if run_process_id:
            logger.info('Resuming interrupted %s run %d', pipeline, run_process_id)
            pending = get_pending_task_process_ids(conn, db_schema, run_process_id, pipeline)
            pending_by_key = {item_key: tid for tid, item_key in pending}
            work_items: List[Tuple[Any, int]] = []
            for item in items:
                key = item_key_fn(item)
                if key in pending_by_key:
                    work_items.append((item, pending_by_key[key]))
            logger.info('Resuming with %d pending items', len(work_items))
            return run_process_id, work_items

    # Create fresh run
    item_keys = [item_key_fn(item) for item in items]
    # Handle both dict items (ETL) and string items (publish)
    entity_type = items[0].get('entity_type', 'unknown') if items and isinstance(items[0], dict) else 'unknown'
    # Extract entity_type from filters if provided (e.g., from publish)
    entity_type = filters.pop('entity_type', entity_type)
    run_process_id = create_run(conn, db_schema, pipeline, entity_type, len(items), **filters)
    task_process_ids = register_tasks(conn, db_schema, run_process_id, pipeline, item_keys)
    return run_process_id, list(zip(items, task_process_ids))
