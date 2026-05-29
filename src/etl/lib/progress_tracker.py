"""
The Glass - ETL Progress Tracking

Wrapper around core progress tracker with ETL-specific API.
"""

from typing import Any, Dict, List, Tuple

from src.core.lib.progress_tracker import (
    complete_run as _complete_run,
    fail_run as _fail_run,
    mark_task_process_completed as _mark_task_completed,
    mark_task_process_failed as _mark_task_failed,
    mark_task_process_started as _mark_task_started,
    resolve_work as _resolve_work,
    update_run_completed_tasks as _update_run_completed_tasks,
)

_PIPELINE = 'etl'


def _make_task_name(entity_type: str, dataset: str, tier: str, columns: Dict) -> str:
    """Build a human-readable name for a call-group work unit."""
    col_part = ','.join(sorted(columns.keys())) if columns else ''
    return f'{entity_type}:{dataset}:{tier}:{col_part}'


def resolve_work(
    conn: Any,
    db_schema: str,
    entity: str,
    season: str,
    season_type: str,
    groups: List[Dict[str, Any]],
    auto_resume: bool,
    league_id: int = None,
) -> Tuple[int, List[Tuple[Dict[str, Any], int]]]:
    """Determine the run_id and pending work items for an entity/season.

    If *auto_resume* is enabled and an interrupted run exists for the same
    (season, season_type, entity), resumes from the last pending group.
    Otherwise creates a fresh run and registers all groups.

    Returns (run_process_id, [(group_dict, task_process_id), ...]).
    """
    def task_name_fn(group: Dict[str, Any]) -> str:
        return _make_task_name(entity, group['dataset'], group['tier'], group.get('columns', {}))

    filters = dict(entity_type=entity, season=season, season_type=season_type)
    if league_id is not None:
        filters['league_id'] = league_id
    return _resolve_work(
        conn, db_schema, _PIPELINE, groups, task_name_fn, auto_resume,
        **filters,
    )


def mark_group_started(conn: Any, db_schema: str, task_process_id: int) -> None:
    """Mark a task entry as running."""
    _mark_task_started(conn, db_schema, task_process_id)


def mark_group_completed(
    conn: Any, db_schema: str, task_process_id: int, rows_written: int,
    dataset: str = None, tier: str = None,
) -> None:
    """Mark a task entry as completed."""
    metadata = dict(rows_written=rows_written)
    if dataset is not None:
        metadata['dataset'] = dataset
    if tier is not None:
        metadata['tier'] = tier
    _mark_task_completed(conn, db_schema, task_process_id, **metadata)


def mark_group_failed(
    conn: Any, db_schema: str, task_process_id: int, error_message: str,
) -> None:
    """Mark a task entry as failed and increment retry count."""
    _mark_task_failed(conn, db_schema, task_process_id, error_message)


def update_run_completed_groups(
    conn: Any, db_schema: str, run_process_id: int,
) -> None:
    """Sync the completed_tasks counter on the run record."""
    _update_run_completed_tasks(conn, db_schema, run_process_id, _PIPELINE)


def complete_run(conn: Any, db_schema: str, run_process_id: int) -> None:
    """Mark a run as completed."""
    _complete_run(conn, db_schema, run_process_id, _PIPELINE)


def fail_run(conn: Any, db_schema: str, run_process_id: int, error_message: str) -> None:
    """Mark a run as failed."""
    _fail_run(conn, db_schema, run_process_id, _PIPELINE, error_message)
