# PBP Implementation Tracking

Source-of-truth design document for the play-by-play (PBP) subsystem.
Live in `project_tracking/`; implementation details, decisions, and plans.

---

## 1. Overview

PBP is the third major data ingestion pathway in Shoot the Sheet (after box-score stats and profile/roster data). It processes raw play-by-play event logs into per-game accumulated result sets for teams and players, then feeds those results into the existing `db_columns` → staging → intermediate → core pipeline.

**Trigger:** `maintain_pbp` phase in `pipeline.py` (runs after `match_games`, before `maintain_profiles`).

**Flow:**

```
Raw PBP source (per game)
  → source-specific handler → standardized PBP format
  → accumulation engine → 2 result_sets per game (team, player)
  → db_columns mapping → staging.player_games / staging.team_games
```

---

## 2. Current State

### 2.1 What Exists

| Component | Status | Notes |
|---|---|---|
| `maintain_pbp` in `pipeline.py` Phase literal | **Done** | Listed in `league_ingest` cluster |
| `_phase_maintain_pbp` handler | **BLOCKER** | Referenced in `PHASE_HANDLERS` dict (line 2407) but never defined. Will crash on import with `NameError`. |
| PBP dataset key in `db_columns.py` | **34 entries** | Currently `"pbp_data"`. Must be renamed to `"pbp_stats"` to match tracking doc (D-2). |
| `pbp_stats` dataset in `DATASETS` | **Missing** | No dataset registered with `phase: "maintain_pbp"` |
| Source-specific PBP handler | **Missing** | No nba_api PBP client or normalizer |
| Standardized PBP format/schema | **Missing** | Defined conceptually in `pbp.md`, not codified in code |
| Accumulation engine | **Missing** | No code to go from raw events → result_sets |
| PBP staging table | **Not needed** | D-3 decided: in-memory only, no staging table |

### 2.2 Columns Already Mapped to PBP

These columns in `db_columns.py` already have PBP dataset_mapping entries (all under `NBA.nba_id`):

**Self stats (team result_set / player result_set):**
- `poss_ending_ft_trips`

**Opponent stats (opp_team / opp_player result_sets):**
- `opp_fg2m`, `opp_fg2a`, `opp_fg3m`, `opp_fg3a`
- `opp_ftm`, `opp_fta`
- `opp_o_rebs`, `opp_d_rebs`
- `opp_turnovers`
- `opp_poss`
- `opp_poss_ending_ft_trips`

**On-court stats (on_player result_set):**
- `on_fg2m`, `on_fg2a`, `on_fg3m`, `on_fg3a`
- `on_ftm`, `on_fta`
- `on_o_rebs`, `on_d_rebs`
- `on_turnovers`
- `on_poss_ending_ft_trips`

### 2.3 Columns with `dataset_mapping: None` That PBP Could Provide

These columns exist in `team_games`/`player_games` tables but have no data source mapped:

| Column | Type | Potential PBP Source |
|---|---|---|
| `o_poss_secs` | INTEGER | team/player result_set → `o_poss_secs` |
| `d_poss_secs` | INTEGER | team/player result_set → `d_poss_secs` |
| `assist_points` | SMALLINT | Derived: `fg2_assists*2 + fg3_assists*3` (see D-5) |
| `o_fouls_draws` | SMALLINT | team/player result_set → `o_fouls_draws` |

---

## 3. Standard PBP Format

The standardized PBP format (defined in `pbp.md`) is the source-agnostic intermediate representation that all source-specific handlers must produce. It is **not persisted** (D-3) -- it is the contract between the normalizer and the accumulator, existing only in memory.

### 3.1 Standard PBP Columns

| Column | Type | Description |
|---|---|---|
| `identity` | TEXT | Source entity identifier (e.g. `nba_id`) |
| `game_id` | TEXT | External game identifier |
| `secs` | INTEGER | Total accumulated seconds from game start (regardless of period) |
| `event_id` | INTEGER | Serial integer, per event (internal) |
| `team_id` | TEXT | External team ID that performed the event |
| `player_id` | TEXT | External player ID that performed the event |
| `event` | TEXT | Normalized event type (see below) |

### 3.2 Normalized Event Types

**Direct actions:**
- `fg2_make`, `fg2_miss` -- 2-point field goal
- `fg3_make`, `fg3_miss` -- 3-point field goal
- `ft1_make` -- made 1-point free throw (default; leagues with 1-for-2/3 differ)
- `ft2_make` -- made 2-point free throw
- `ft3_make` -- made 3-point free throw
- `ft1_miss` -- missed free throw
- `turnover` -- turnover
- `o_reb` -- offensive rebound (includes out-of-bounds after missed FG/FT without poss_end)
- `d_reb` -- defensive rebound (includes out-of-bounds after missed FG/FT with poss_end)
- `foul` -- committed foul

**Secondary actions (may not be provided by all sources):**
- `fg2_assist` -- assist on a made 2-point FG
- `fg3_assist` -- assist on a made 3-point FG
- `block` -- block on opponent FG attempt
- `steal` -- steal on opponent turnover
- `o_foul_draw` -- drawn offensive foul on opponent

**Possession events (derived, complex):**
- `poss_ending_ft_trip` -- free throw trip that could end possession (no and-ones, no technicals, no flagrants for NBA)
- `poss_start` -- possession start (jump_ball_win, opp turnover, d_reb, fga/fta followed by opp offensive event, period_start)
- `poss_end` -- possession end (always precedes poss_start unless period_start)

**Game context events:**
- `period_start` -- start of a period
- `period_end` -- end of a period
- `player_in` -- player enters the game (may need to be inferred)
- `player_out` -- player leaves the game (subs, ejections, period-end)
- `jump_ball_win` -- jump ball win

---

## 4. Result Sets

Each game produces **2 result sets**: one for teams, one for players. These are the accumulated outputs that feed into `db_columns`.

### 4.1 Team Result Set

One row per team per game. Event filtering: `team_id == event_team_id` (team events) or `team_id != event_team_id` (opp_team events).

| Field | Source | Description |
|---|---|---|
| `game_id` | identity | External game ID |
| `team_id` | identity | External team ID |
| `points` | computed | `fg2m*2 + fg3m*3 + ftm` |
| `poss` | sum | `new_poss` team events |
| `secs` | last row | Last record's secs amount |
| `o_poss_secs` | sum | secs between poss_start and poss_end (team) |
| `d_poss_secs` | sum | secs between poss_start and poss_end (opp_team) |
| `fg2m` | sum | `fg2_make` team events |
| `fg2a` | sum | `fg2_make + fg2_miss` team events |
| `fg3m` | sum | `fg3_make` team events |
| `fg3a` | sum | `fg3_make + fg3_miss` team events |
| `ftm` | sum | `ft_make` team events |
| `fta` | sum | `ft_make + ft_miss` team events |
| `poss_ending_ft_trips` | sum | `poss_ending_ft_trip` team events |
| `fg2_assists` | sum | `fg2_assist` team events |
| `fg3_assists` | sum | `fg3_assist` team events |
| `turnovers` | sum | `turnover` team events |
| `o_rebs` | sum | `o_reb` team events |
| `d_rebs` | sum | `d_reb` team events |
| `blocks` | sum | `block` team events |
| `o_fouls_draws` | sum | `o_foul_draw` team events |
| `steals` | sum | `steal` team events |
| `fouls` | sum | `foul` team events |
| `opp_poss` | sum | `new_poss` opp_team events |
| `opp_fg2m`..`opp_turnovers` | sum | Mirror of above for opp_team events |

### 4.2 Player Result Set

One row per player per game. Three event scopes:

- **player**: events where `player_id == event_player_id`
- **opp_player**: events by opposing players (while this player is on court)
- **on_player**: events by teammates (while this player is on court)

All team-scoped fields from the team result set are also available at the player level, plus:
- `win` -- boolean from team points comparison
- `poss` -- `poss_start on_player` events
- `secs` -- sum of secs between player_in and player_out events
- `on_*` fields -- teammate events while on court (on_fg2m, on_fg2a, on_fg3m, on_fg3a, on_ftm, on_fta, on_poss_ending_ft_trips, on_turnovers, on_o_rebs, on_d_rebs)

---

## 5. Config Architecture (Completed Refactor)

### 5.1 Entity Resolution (Phase 0 -- Done)

The config refactor (Phase 0) resolved 5 structural problems in how datasets, sources, and the executor wire together. All changes are implemented and verified.

**Key changes:**
- `execution_tier` replaced with `iterates_by: Literal["none", "team", "player", "game"]`
- `target_tables` changed from `List[str]` to `Dict[str, str]` (schema-qualified table name → entity type)
- `API_FIELD_NAMES['target_id']` replaced with `entity_fields` + `entity_params` in source config
- `_target_api_param()` removed from executor; `ctx.entity_param` used instead
- `season_type_separated` renamed to `per_season_type` for consistency with `iterates_by`

**New resolution flow:**

```
datasets.py target_tables: {"staging.player_games": "player", "staging.team_games": "team"}
    ↓
orchestrator resolves per target:
    entity_type = dataset.target_tables[target]         # "player"
    entity_id_field = source.entity_fields[entity_type]  # "PLAYER_ID" (response)
    entity_param = source.entity_params[entity_type]     # "PLAYER_ID" (request)
    ↓
execute_group() dispatches by dataset.iterates_by:
    "none"   → one API call, extract all
    "team"   → iterate team IDs from staging.teams
    "player" → null-entity query on target staging table
    "game"   → iterate game IDs from staging.games (new, for PBP)
```

**Entity source resolution** (convention per `iterates_by` value):

| iterates_by | Entity source |
|---|---|
| `"none"` | N/A (one call) |
| `"team"` | `staging.teams` WHERE league_code = league |
| `"player"` | Null-entity query on target staging table |
| `"game"` | `staging.games` WHERE league + season + type |

### 5.2 Config Layer Separation

Each config layer has a distinct, non-overlapping purpose:

| Layer | File | Purpose | Example |
|---|---|---|---|
| **Table structure** | `schema.py` | PKs, FKs, indexes, constraints | `staging.team_games` PK = `[identity, ext_team_id, ext_game_id]` |
| **Column mapping** | `db_columns.py` | Which dataset field fills which column | `fg2m` on `team_games` maps to `pbp_data.result_set: "team"` |
| **Write declaration** | `datasets.target_tables` | Which tables a dataset writes to + entity type | `{"staging.team_games": "team"}` |
| **Stale row pruning** | `datasets.prune_tables` | Which tables to truncate stale rows from | `["staging.leagues_teams"]` |
| **Source wire format** | `nba_api/config.py` | How the API talks: field names, param names | `entity_fields["game"] = "GAME_ID"` |
| **League properties** | `leagues.py` | Calendar, retention, season types, FT rules | `season_types["playoffs"]["is_postseason"]` |

**Not duplicative:** `target_tables` declares *what a dataset writes to*. `db_columns` declares *what values fill the columns*. `schema` declares *how the table is structured*. They are complementary, not overlapping.

---

## 6. Architecture Decisions

### D-1: PBP Source Endpoint

**Question:** Which nba_api endpoint provides the raw PBP data?

**Options:**
- `playbyplayv3` -- Play-by-play via nba_api stats endpoint
- NBA Live API -- Real-time play-by-play (different format, auth requirements)

**Recommendation:** `playbyplayv3` for historical/backfill, consistent with existing nba_api pattern.

**Status:** PENDING

### D-2: PBP Dataset Registration Key

**Question:** What is the dataset key in `DATASETS["nba_id"]`?

**Options:**
- `pbp_stats` -- matches the name used in `db_columns.py` dataset_mapping
- `play_by_play` -- more descriptive of the raw source

**Recommendation:** `pbp_stats` -- consistency with db_columns.

**Status:** DECIDED -- `pbp_stats`

**BLOCKER:** `db_columns.py` currently has 34 entries using `"pbp_data"`, not `"pbp_stats"`. Must rename all 34 entries in `db_columns.py` from `"pbp_data"` to `"pbp_stats"` before implementation begins.

### D-3: Standard PBP Persistence

**Question:** Should the standardized PBP format be persisted to a staging table?

**Options:**
- **A) Persist** to `staging.pbp_events` -- enables reprocessing, debugging, audit trail
- **B) In-memory only** -- standard PBP is a transient DataFrame, only result_sets are written

**Tradeoffs:**
- Persistence adds a staging table, write overhead, and prune logic
- In-memory is simpler but makes debugging harder and reprocessing impossible without re-fetching

**Recommendation:** Start with in-memory (B). Add persistence later if needed for debugging or reprocessing.

**Status:** DECIDED -- in-memory only

### D-4: PBP Execution Tier / Strategy

**Question:** How does the orchestrator drive PBP ingestion?

**PBP reality:** PBP is inherently per-game -- one API call per game. The execution flow is:
1. Get list of games for the season/type (already available from `maintain_games`)
2. For each game, fetch raw PBP
3. Normalize → accumulate → write result_sets

**Options:**
- **A) New execution tier `per_game`** with PBP-specific orchestrator logic
- **B) Custom phase handler** (like `_maintain_games`) that iterates games directly
- **C) Reuse `per_team` tier** with game iteration baked into the fetcher

**Recommendation:** B -- dedicated `_maintain_pbp` handler that iterates games directly. PBP accumulation is fundamentally different from the column-extraction pattern used by other phases.

**Status:** DECIDED -- custom `_maintain_pbp` handler with config-driven `iterates_by: "game"`

### D-5: Assist Point Derivation

**Question:** The `assist_points` column has `dataset_mapping: None`. PBP has `fg2_assists` and `fg3_assists` but no direct "assist points" field. How should `assist_points` be derived?

**Options:**
- **A) Derive from PBP**: `fg2_assists * 2 + fg3_assists * 3` (requires adding a derived mapping)
- **B) Leave unmapped**: `assist_points` stays None until a source provides it directly
- **C) Use a different source**: Some API might provide AST PTS directly

**Recommendation:** A -- derive from PBP. This is a clean, config-driven computation using the existing `derived` mechanism in `db_columns.py` (same pattern as `fg2m` which uses `"derived": {"math": "FGM - FG3M", "fields": ["OPP_FGM", "OPP_FG3M"]}`).

**Status:** PENDING

### D-6: Possession Tracking Complexity

**Question:** `poss_start` and `poss_end` events are complex to derive. How should they be implemented?

**Key complexity (from `pbp.md`):**
- `poss_start`: jump_ball_win, opponent turnover, d_rebound, fga/fta followed by opponent offensive event, period_start
- `poss_end`: always directly precedes poss_start (unless period_start)

**Options:**
- **A) Full derivation**: Implement the complete possession logic in the accumulator
- **B) Simplified NBA-first**: Start with NBA-specific rules, generalize later
- **C) Source-provided**: If the source provides possession data, use it directly

**Recommendation:** B -- start with NBA-specific rules (most straightforward: standard free throw trips, no and-ones/technicals/flagrants). Generalize via config when adding leagues.

**Status:** PENDING

### D-7: Player In/Out Tracking

**Question:** `player_in`/`player_out` events may not be provided by sources. How are they inferred?

**From `pbp.md`:** Players will record events within each period, allowing retroactive inference. The first and last events in each period should be player_in/player_out for all court players.

**Options:**
- **A) Infer from events**: Parse event sequences to build in/out retroactively
- **B) Require source data**: Only process PBP from sources that provide lineup data
- **C) Skip for MVP**: Don't generate player_in/player_out events initially; accumulate secs from box score

**Recommendation:** Implement in Phase 2. Critical for on_* player stats (on_fg2m, on_d_rebs, etc.) -- the 10 `on_player` columns in db_columns cannot be populated without knowing who is on court.

**Status:** DECIDED -- implement in Phase 2 (not deferred)

### D-8: FT Trip Rules by League

**Question:** `poss_ending_ft_trip` rules vary by league (NBA: standard trips only; G-League: 1-for-2/3; etc.). How is this configured?

**Options:**
- **A) League config**: Add FT trip rules to `leagues.py`
- **B) Dataset config**: Add rules to the PBP dataset entry in `DATASETS`
- **C) Source config**: Add rules to the source's `config.py`

**Recommendation:** A -- league-level config is the natural home. FT trip rules are league properties, not source properties. Proposed shape in `leagues.py`:

```python
"ft_trip_rules": {
    "exclude_and_ones": True,
    "exclude_technicals": True,
    "exclude_flagrants": True,
}
```

**Status:** PENDING

### D-9: Raw PBP Source as a Dataset

**Question:** Does the raw PBP fetch register as its own dataset in `DATASETS`, or is it a special case?

**Options:**
- **A) Register as dataset**: `pbp_stats` dataset in `DATASETS["nba_id"]` with `phase: "maintain_pbp"` and appropriate source_mapping
- **B) Hardcode in handler**: The `_maintain_pbp` handler directly calls the source client without going through the generic executor

**Recommendation:** A -- consistency with the existing pattern. The PBP handler can still use a custom execution path, but the dataset metadata (endpoint, season mapping, etc.) should live in `DATASETS`. Assigning the phase `maintain_pbp` is what drives it toward the PBP-specific transform logic in the custom handler.

**Status:** DECIDED -- register as standard dataset in DATASETS

---

## 7. Config Cleanup Items

### 7.1 `row_filters` -- Config-Driven Dataset-Level Filtering

**Finding:** `row_filters` was defined in the `Dataset` TypedDict and populated on `leagues_teams_rosters`, but had no consumer. The filtering logic was never implemented -- a gap, not dead config.

**What it does:** The `commonteamyears` NBA API endpoint returns ALL NBA teams historically (with `MIN_YEAR`/`MAX_YEAR` indicating active range). The `row_filters` config filters to only teams active during the current season:

```python
"row_filters": [
    {"field": "MIN_YEAR", "op": "lte", "value_template": "{season_end_year}"},
    {"field": "MAX_YEAR", "op": "gte", "value_template": "{season_end_year}"},
]
```

**Resolution:** The config is correct and config-driven. Implemented the consumer:

1. `apply_row_filters()` in `src/lib/extract.py` -- filters rows in every result set based on dataset-level `row_filters` config. Supports `lte`, `gte`, `eq` operators with template variable resolution.
2. Called in `src/orchestrator.py` `_run_groups` -- applied after fetch, before `execute_group`. Template variables (e.g. `season_end_year`) are resolved from the orchestrator's runtime context.

This is config-driven: the filter lives in the dataset definition, the orchestrator reads and applies it, and no individual column entry needs to know about filtering.

### 7.2 `pbp_data` → `pbp_stats` Rename

**Finding:** `db_columns.py` has 34 entries using `"pbp_data"` as the dataset key. The tracking doc and D-2 decision specify `"pbp_stats"`.

**Action:** Rename all 34 `"pbp_data"` entries in `db_columns.py` to `"pbp_stats"` before PBP implementation begins. This is a mechanical find-and-replace.

---

## 8. File Manifest

| File | Purpose | Status |
|---|---|---|
| `project_tracking/pbp.md` | PBP spec: standard columns, events, result_set formulas | DONE |
| `project_tracking/pbp_tracking.md` | This file: implementation tracking, decisions, plans | DONE |
| `src/definitions/pipeline.py` | `maintain_pbp` in `league_ingest` cluster, Phase Literal | DONE |
| `src/definitions/datasets.py` | `iterates_by`, `target_tables` Dict, `per_season_type` rename | DONE |
| `src/definitions/db_columns.py` | 34 PBP entries (rename `pbp_data` → `pbp_stats`). Add PBP-derived mappings for unmapped columns. | TODO |
| `src/definitions/schema.py` | Table definitions (no changes needed for PBP) | DONE |
| `src/sources/nba_api/config.py` | `entity_fields` + `entity_params` replacing `target_id` | DONE |
| `src/lib/executor.py` | `ctx.entity_param` replacing `_target_api_param()` | DONE |
| `src/lib/call_grouper.py` | `iterates_by` replacing `execution_tier` | DONE |
| `src/lib/coverage_tracker.py` | `iterates_by` replacing `execution_tier` | DONE |
| `src/orchestrator.py` | `_resolve_entity_for_target()`, `_generic_targets_for_dataset()`. Define `_phase_maintain_pbp` handler. | PARTIAL |
| `src/sources/nba_api/pbp_handler.py` | Source-specific PBP normalizer: raw nba_api PBP → standard format | TODO |
| `src/lib/pbp/__init__.py` | Package init for PBP library modules | TODO |
| `src/lib/pbp/schema.py` | Standard PBP format as TypedDict (event types, result_set fields) | TODO |
| `src/lib/pbp/accumulator.py` | Core accumulation engine: standard PBP → team/player result_sets | TODO |
| `src/lib/pbp/events.py` | Event classification and possession logic | TODO |
| `src/lib/pbp/lineups.py` | Player in/out inference from event sequences | TODO |
| `src/lib/extract.py` | `apply_row_filters()` -- dataset-level post-fetch row filtering | DONE |
| `src/definitions/leagues.py` | Add FT trip rules for NBA | TODO |

---

## 9. Implementation Phases

### Phase 0: Config Refactor (Complete)
- [x] Replace `execution_tier` with `iterates_by` in Dataset type
- [x] Change `target_tables` from `List[str]` to `Dict[str, str]` (table → entity_type)
- [x] Replace `API_FIELD_NAMES['target_id']` with `entity_fields` + `entity_params` in source config
- [x] Remove `_target_api_param()` from executor, use `ctx.entity_param`
- [x] Update orchestrator to resolve entity_type from target_tables dict
- [x] Update call_grouper to use `iterates_by` instead of `execution_tier`
- [x] Update all existing dataset entries to new format
- [x] Rename `season_type_separated` to `per_season_type`
- [x] Verify no regressions in existing phases

### Phase 0.5: Pre-PBP Cleanup
- [x] Rename `pbp_data` → `pbp_stats` in all 34 db_columns.py entries
- [x] Implement `row_filters` consumer (`apply_row_filters` in extract.py, wired in orchestrator)
- [ ] Define `_phase_maintain_pbp` stub in orchestrator (fix import crash)

### Phase 1: PBP Foundation
- [ ] Register `pbp_stats` dataset in `DATASETS["nba_id"]`
  - `phase: "maintain_pbp"`, `iterates_by: "game"`, `per_season_type: True`
  - `target_tables: {"staging.team_games": "team", "staging.player_games": "player"}`
  - `source_mapping: {"class_name": "playbyplayv3", ...}`
- [ ] Define standard PBP format as TypedDict in `src/lib/pbp/schema.py`
  - Event type Literal, standard column TypedDicts, result_set field TypedDicts
- [ ] Implement nba_api PBP normalizer (`src/sources/nba_api/pbp_handler.py`)
  - Raw nba_api PBP response → standard PBP format DataFrame
  - Event classification: map source-specific event strings to standard event types
- [ ] Implement basic accumulator (`src/lib/pbp/accumulator.py`)
  - Standard PBP events → team result_set (sum events by team_id)
  - Handle simple events (fg2_make, turnover, etc.) and complex events (poss_ending_ft_trip)
- [ ] Wire `_phase_maintain_pbp` in orchestrator
  - Iterate games from `staging.games` WHERE league + season + type
  - Per game: fetch raw PBP → normalize → accumulate → write result_sets
  - Use existing `bulk_upsert` or `write_entity_rows` for DB writes

### Phase 2: Player Result Set + Lineups
- [ ] Extend accumulator to produce player result_set
  - Three scopes: player, opp_player, on_player
- [ ] Implement player_in/player_out inference (`src/lib/pbp/lineups.py`)
  - Parse event sequences to retroactively build in/out events at period boundaries
- [ ] Implement on-court event tracking
  - Track which players are on court at each event timestamp
  - Filter opp_player and on_player events to "while player is on court"

### Phase 3: DB Column Integration
- [ ] Add PBP-derived mappings for `o_poss_secs`, `d_poss_secs`, `o_fouls_draws`
- [ ] Derive `assist_points` from PBP: `fg2_assists*2 + fg3_assists*3`
  - Use existing `derived` mechanism in db_columns.py
- [ ] Verify first-write-wins semantics with existing box-score mappings
  - PBP and box-score may both write to `team_games`/`player_games`
  - First-write-wins within a single identity run prevents conflicts

### Phase 4: Possession Logic
- [ ] Implement `poss_start`/`poss_end` event derivation in `src/lib/pbp/events.py`
- [ ] Implement `poss_ending_ft_trip` with NBA-specific rules
- [ ] Add FT trip rules to `leagues.py`
- [ ] Implement `o_poss_secs`/`d_poss_secs` calculation from possession events

### Phase 5: Hardening
- [ ] Coverage tracking integration (PBP likely needs `"games_coverage"`)
- [ ] Error handling for incomplete PBP data (missing events, partial games)
- [ ] Reprocessing support (if D-3 persistence is added later)
- [ ] Performance optimization for full-season backfill

---

## 10. Open Questions

1. **PBP column for `assist_points`**: Should we add a computed field to the PBP result_set (`fg2_assists*2 + fg3_assists*3`) or use the `derived` mechanism in `db_columns.py` to compute it from existing `fg2_assists` and `fg3_assists` fields? The `derived` approach is more DRY (single source of truth for the formula).

2. **Alternative PBP sources for box-score columns**: Should `fouls`, `blocks`, and `steals` get PBP mappings as alternative/secondary sources to box score? Currently these are box-score-only. PBP provides them but with different semantics (committed fouls vs drawn fouls, etc.).

3. **Incomplete PBP data handling**: How should the accumulator handle incomplete PBP data (e.g., missing events, partial games, source errors)? Options: skip the game entirely, accumulate with NULL for missing fields, or log and continue.

4. **Season coverage model for PBP**: Per-game coverage seems natural (each game is independently fetchable). Should we use `"games_coverage"` or `"seasons_coverage"` in the dataset config?

5. **`points` field**: The team result set has a `points` field (`fg2m*2 + fg3m*3 + ftm`). Does this map to any existing `db_columns` entry, or is it only used for the `win` derivation in the player result set?
