"""
The Glass - Publish Progress Tracking

Wrapper around core progress tracker with publish-specific API.
"""

from typing import Any, List, Tuple

from src.core.lib.progress_tracker import (
    complete_run as _complete_run,
    fail_run as _fail_run,
    mark_task_process_completed as _mark_task_completed,
    mark_task_process_failed as _mark_task_failed,
    mark_task_process_started as _mark_task_started,
    resolve_work as _resolve_work,
    update_run_completed_tasks as _update_run_completed_tasks,
)

_PIPELINE = 'publish'


def resolve_work(
    conn: Any,
    db_schema: str,
    league: str,
    views: List[str],
    auto_resume: bool,
) -> Tuple[int, List[Tuple[str, int]]]:
    """Determine the run_id and pending work items for a publish run.
    
    Returns (run_process_id, [(view_name, task_process_id), ...]).
    """
    def task_name_fn(view: str) -> str:
        return view

    return _resolve_work(
        conn, db_schema, _PIPELINE, views, task_name_fn, auto_resume,
        entity_type=league,
    )


def mark_view_started(conn: Any, db_schema: str, task_process_id: int) -> None:
    """Mark a task entry as running."""
    _mark_task_started(conn, db_schema, task_process_id)


def mark_view_completed(conn: Any, db_schema: str, task_process_id: int) -> None:
    """Mark a task entry as completed."""
    _mark_task_completed(conn, db_schema, task_process_id)


def mark_view_failed(conn: Any, db_schema: str, task_process_id: int, error_message: str) -> None:
    """Mark a task entry as failed and increment retry count."""
    _mark_task_failed(conn, db_schema, task_process_id, error_message)


def update_run_completed_views(conn: Any, db_schema: str, run_process_id: int) -> None:
    """Sync the completed_tasks counter on the run record."""
    _update_run_completed_tasks(conn, db_schema, run_process_id, _PIPELINE)


def complete_run(conn: Any, db_schema: str, run_process_id: int) -> None:
    """Mark a run as completed."""
    _complete_run(conn, db_schema, run_process_id, _PIPELINE)


def fail_run(conn: Any, db_schema: str, run_process_id: int, error_message: str) -> None:
    """Mark a run as failed."""
    _fail_run(conn, db_schema, run_process_id, _PIPELINE, error_message)
