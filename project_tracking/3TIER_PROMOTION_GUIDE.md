# 3-Tier Promotion Implementation Guide

## Current State
- 2-tier promotion works (staging → core)
- Ready schema exists with 14 tables
- `last_identity` column added to all ready tables

## Implementation Plan

### Phase 1: Create Promotion Functions

```python
def _promote_profiles_to_ready(identity: str, cur) -> int:
    """Promote staging → ready for profiles (teams, players)."""
    # For each entity_type (team, player):
    #   INSERT INTO ready.{entity} 
    #   SELECT * FROM staging.{entity} WHERE identity = %s
    #   ON CONFLICT (staged columns) DO UPDATE 
    #   SET (all columns) = (EXCLUDED.*)
    #       last_identity = %s
    # Always overwrite - last identity wins
    
def _promote_rosters_to_ready(league_code: str, identity: str, cur) -> int:
    """Promote staging → ready for rosters."""
    # Similar to profiles but with league_code filtering
    
def _promote_seasons_to_ready(league_code: str, identity: str, cur) -> int:
    """Promote staging → ready for season stats."""
    
def _promote_games_to_ready(league_code: str, identity: str, cur) -> int:
    """Promote staging → ready for game stats."""
    
def _promote_to_core(entity_group: str, cur) -> int:
    """Promote ready → core (simple copy, no identity tracking)."""
    # For each table in entity_group:
    #   INSERT INTO core.{table}
    #   SELECT (all non-identity columns) FROM ready.{table}
    #   ON CONFLICT DO UPDATE SET ...
    # Drop last_identity column in SELECT
```

### Phase 2: Update Orchestrator Flow

**Current:**
```
per_identity:
  - maintain_*  (writes to staging)
  - ...
execution_end:
  - merge_staging (currently promotes staging → core)
  - ...
```

**New:**
```
per_identity:
  - maintain_*  (writes to staging)
  - promote_to_ready  (NEW: staging → ready per identity)
  
execution_end:
  - promote_to_core (NEW: ready → core after all identities)
  - ...
```

### Phase 3: Wire Into Pipeline

1. Add "promote_to_ready" phase to per_identity cluster in pipeline.py
2. Change execution_end "merge_staging" to "promote_to_core"
3. Implement _phase_promote_to_ready() in orchestrator
4. Implement _phase_promote_to_core() in orchestrator

## Benefits
- No production flickering during multi-identity runs
- Identity order = priority (last wins)
- Clean separation of concerns

## Complexity
- ~400 lines of new code
- Touches orchestrator, pipeline, potentially db_columns
- Requires careful SQL for conflict resolution

## Alternative: Defer to Next Session
Current 2-tier promotion works fine. 3-tier is an optimization for stability.
Can be implemented separately without breaking existing functionality.

## Decision
Given time constraints and the fact that 2-tier works, recommend:
1. Document the approach (this file)
2. Defer implementation to dedicated session
3. Focus on smaller wins (EntityType literals, docs)
