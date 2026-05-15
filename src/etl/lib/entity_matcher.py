"""
The Glass - Entity Matcher

Provides a stable orchestration hook for identity matching in the discover
phase. Behavior is config-driven via a single global ETL policy definition.
"""

import logging
from typing import Any, Dict, Iterable

from src.etl.definitions.pipeline import (
    ENTITY_MATCHER_POLICY,
    VALID_ENTITY_MATCHER_MODES,
)

logger = logging.getLogger(__name__)


def _as_set(values: Iterable[Any]) -> set[str]:
    return {str(v) for v in values if v is not None and str(v).strip() != ''}


def _resolve_matcher_rule(league_key: str, entity: str) -> Dict[str, Any]:
    """Resolve effective matcher rule for an entity in a league.

    Rule precedence: ``entity_rules[entity]`` over ``default_mode``.
    """
    matcher_cfg = ENTITY_MATCHER_POLICY

    default_mode = matcher_cfg.get('default_mode', 'approve_all')
    entity_rule = (matcher_cfg.get('entity_rules') or {}).get(entity, {})
    mode = entity_rule.get('mode', default_mode)
    blocked_ids = entity_rule.get('blocked_source_ids', [])

    if mode not in VALID_ENTITY_MATCHER_MODES:
        logger.warning(
            'Unknown matcher mode %r for league=%s entity=%s; falling back to approve_all',
            mode,
            league_key,
            entity,
        )
        mode = 'approve_all'

    return {
        'mode': mode,
        'blocked_source_ids': blocked_ids,
    }


def approve_entities(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    *,
    league_key: str,
    source_key: str,
    season: str,
    season_type: str,
) -> Dict[Any, Dict[str, Any]]:
    """Apply configured matcher policy and return approved rows.

    Supported modes:
        - ``approve_all``
        - ``drop_missing_source_id``
        - ``drop_blocked_source_ids``
    """
    try:
        rule = _resolve_matcher_rule(league_key, entity)
        mode = rule['mode']

        if mode == 'approve_all':
            logger.debug(
                'Entity matcher approve_all: league=%s source=%s entity=%s season=%s type=%s rows=%d',
                league_key,
                source_key,
                entity,
                season,
                season_type,
                len(rows),
            )
            return rows

        approved = dict(rows)

        if mode == 'drop_missing_source_id':
            approved = {
                sid: vals
                for sid, vals in approved.items()
                if sid is not None and str(sid).strip() != ''
            }
        elif mode == 'drop_blocked_source_ids':
            blocked = _as_set(rule.get('blocked_source_ids', []))
            approved = {
                sid: vals
                for sid, vals in approved.items()
                if str(sid) not in blocked
            }

        dropped = len(rows) - len(approved)
        if dropped:
            logger.info(
                'Entity matcher dropped %d row(s): league=%s source=%s entity=%s mode=%s',
                dropped,
                league_key,
                source_key,
                entity,
                mode,
            )
        return approved
    except Exception as exc:
        logger.error(
            'Entity matcher failed for league=%s source=%s entity=%s: %s. Falling back to approve_all.',
            league_key,
            source_key,
            entity,
            exc,
        )
        return rows