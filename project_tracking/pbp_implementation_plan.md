# PBP Implementation Plan -- Event Catalog & Entity Validation

**Created:** 2026-07-28
**Status:** Design phase

---

## 1. Overview

| System | Purpose | Priority |
|--------|---------|----------|
| **Event Catalog** | Classify every possible source event (track/ignore), detect unknowns | P1 |
| **Entity Resolver** | Validate player/team IDs against staging tables | P1 |
| **Discovery Pipeline** | Build the catalog, find unknowns, enforce in production | P1 |

Core principle: **every event must be explicitly classified, every entity must exist in staging, and unknown data is a loud failure.**

---

## 2. Event Catalog System

### 2.1 Architecture

One DB table. No seed file. Discovery populates it. Humans review it. Production enforces it.

```
┌─────────────────────────────────────────────────────────┐
│                  DISCOVERY MODE                          │
│  ───────────────────────────────                        │
│  $ python -m src.lib.pbp.discover --source nba_data     │
│                                                         │
│  Processes all games, finds every unique event shape.    │
│  INSERTs into core.pbp_event_catalog with                │
│  status = 'unreviewed'.                                  │
│  On re-run, updates existing rows (game_count, etc.)     │
│  but never downgrades a reviewed status.                 │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  HUMAN REVIEW                            │
│  ───────────────────────────────                        │
│  Review unreviewed rows. Decide:                         │
│    status = 'track'   -> fill maps_to, contributes_to    │
│    status = 'ignore'  -> fill reason                     │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  PRODUCTION MODE                         │
│  ───────────────────────────────                        │
│  maintain_pbp checks every event against the catalog.    │
│  Rows with status IN ('track', 'ignore') are classified. │
│  Rows with status = 'unreviewed' are NOT classified      │
│    (they still need human review).                       │
│  Any event not matching a classified row -> ERROR.       │
│  Game is skipped. Phase stops.                           │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Schema: `core.pbp_event_catalog`

A single table. `status` controls the lifecycle.

```sql
CREATE TABLE core.pbp_event_catalog (
    identity        TEXT NOT NULL,          -- e.g. "nba_id"
    source          TEXT NOT NULL,          -- e.g. "nba_data"
    event_key       TEXT NOT NULL,          -- e.g. "MSG=6_ACT=7" (unique per source)

    -- Matching: how to identify this event in raw data
    match_fields    JSONB NOT NULL,         -- e.g. {"EVENTMSGTYPE": 6, "EVENTMSGACTIONTYPE": 7}

    -- Classification (set by human during review)
    status          TEXT NOT NULL DEFAULT 'unreviewed',
                                            -- 'unreviewed' | 'track' | 'ignore'
    maps_to         TEXT,                   -- standard PBPEventType (when status='track')
    reason          TEXT,                   -- why ignored (when status='ignore')
    contributes_to  TEXT[],                 -- stat categories: ["fouls", "fga", ...]
    secondary       JSONB,                  -- piggyback events: [{"maps_to": "steal", ...}]

    -- Discovery metadata (set by discovery script)
    discovered_season TEXT,                -- first season seen
    discovered_game  TEXT,                  -- first game_id seen
    sample_raw      JSONB,                  -- example raw row for human reference
    last_seen_season TEXT,                 -- most recent season seen
    game_count      INTEGER DEFAULT 1,      -- how many games contain this event

    -- Audit
    reviewed_by     TEXT,                   -- who set status='track' or 'ignore'
    reviewed_at     TIMESTAMPTZ,
    notes           TEXT,                   -- free-form human notes
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (identity, source, event_key)
);
```

**Status lifecycle:**

```
unreviewed  ──(human reviews)──►  track    ──► used by classifier in production
            │
            └──(human reviews)──►  ignore   ──► used by classifier in production

Discovery re-runs: ON CONFLICT UPDATE game_count, last_seen_season, sample_raw.
Never downgrades status. (unreviewed -> track is fine; track -> unreviewed is not.)
A new event shape that appears for the first time gets status='unreviewed'.
```

**Why not two tables?** `status` column is simpler. Discovery inserts unreviewed rows.
Humans update the status. Production queries `WHERE status IN ('track', 'ignore')`.
No row migration. No table joins.

**Why no seed file?** Discovery processes all games and finds every event shape.
A seed file would be redundant with what discovery produces, and a maintenance
burden to keep in sync with the DB. Start empty, discover everything, review, enforce.

---

## 3. Discovery Script

### 3.1 Entry point

```
# Full discovery: every PBP dataset
python -m src.cli --discover-pbp

# Targeted: a specific identity + dataset
python -m src.cli --discover-pbp nba_id.pbp_stats

# Targeted: a single season
python -m src.cli --discover-pbp nba_id.pbp_stats --season 2024-25

# Targeted: a single game
python -m src.cli --discover-pbp nba_id.pbp_stats --game-id 21000001
```

Arguments:
- `--discover-pbp [IDENTITY.DATASET]`: Run discovery instead of normal ETL.
  Optional value in `identity.dataset_name` format (e.g. `nba_id.pbp_stats`).
  If omitted, discovers all PBP datasets across all identities.
- `--season` (optional): limit to one season
- `--game-id` (optional): limit to one game

### 3.2 Behavior

```
For each game:
  1. Fetch raw PBP rows
  2. For each row, build a match signature (source-specific)
  3. Check against core.pbp_event_catalog WHERE status IN ('track', 'ignore')
  4. If NOT found in classified rows:
     - INSERT INTO core.pbp_event_catalog with status='unreviewed'
       (ON CONFLICT UPDATE game_count, last_seen_season)
  5. If found with status='unreviewed':
     - UPDATE game_count, last_seen_season, sample_raw
  6. Track: total games, total events, classified %, new types found

After all games:
  - Print summary report
  - Highlight how many new 'unreviewed' entries were added
  - Print instructions: "Review these rows and set status to 'track' or 'ignore'"
```

### 3.3 What it does NOT do

- Does NOT error on unrecognized events (that's production mode)
- Does NOT write to staging tables
- Does NOT write to game_coverages
- Does NOT accumulate stats
- Does NOT halt on any individual game failure

---

## 4. Production Enforcement (in `maintain_pbp`)

### 4.1 Behavior

```python
def _maintain_pbp(...):
    classifier = _load_classifier(identity_code, source)
    entity_resolver = make_entity_resolver(conn, identity_code)

    for game in games:
        rows = _fetch_pbp(game)
        events = normalize_game(rows, ..., entity_resolver=entity_resolver)

        # Classify every raw row against the catalog
        unclassified = []
        for raw_row in rows:
            try:
                result = classifier.classify(raw_row)
                if result.status == 'unreviewed':
                    unclassified.append(...)  # Needs human review
            except UnclassifiedEventError as e:
                unclassified.append(...)  # Not in catalog at all

        if unclassified:
            # Log ALL unrecognized events, not just the first
            for uc in unclassified:
                log_error_simple("maintain_pbp",
                    f"Unclassified event in {game['ext_game_id']}: {uc.signature}")

            logger.error(
                f"Game {game['ext_game_id']}: {len(unclassified)} unclassified "
                f"events. Skipping game and stopping PBP phase. "
                f"Run 'discover --source {source}' to find these, then review.")

            break  # Stop processing further games

        # All classified -> normal processing
        results = accumulate(events)
        write_to_staging(results)
```

### 4.2 What counts as "classified"

Only rows with `status IN ('track', 'ignore')`. Rows with `status = 'unreviewed'` are NOT classified -- they need human review first. This prevents the pipeline from running against an unreviewed catalog.

---

## 5. Entity Resolver (Standardized)

### 5.1 Design

Source-agnostic. Lives in `src/lib/pbp/entity_resolver.py`. Every normalizer consumes it identically.

```python
def make_entity_resolver(conn, identity_code: str):
    """Build a resolver callable from staging.players and staging.teams."""

    teams = set()
    players = {}  # player_id -> team_id

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ext_id FROM staging.teams WHERE identity = %s",
            (identity_code,))
        for row in cur:
            teams.add(row[0])

        cur.execute(
            "SELECT ext_id, team_id FROM staging.players WHERE identity = %s",
            (identity_code,))
        for row in cur:
            players[row[0]] = row[1]

    def resolve(entity_id: str) -> tuple[str | None, str | None]:
        """Return (entity_type, team_id) or (None, None) for unknown."""
        if not entity_id or entity_id == "0":
            return None, None
        if entity_id in teams:
            return ("team", entity_id)
        if entity_id in players:
            return ("player", players[entity_id])
        return (None, None)

    return resolve
```

### 5.2 How the normalizer uses it

```python
def normalize_game(rows, game_id, home_team_id, away_team_id,
                   identity="nba_id",
                   entity_resolver=None):  # NEW parameter

    for row in rows:
        p1_id = _to_str(row.get(COL["PLAYER1_ID"]))

        # Resolve entity via staging lookup (not PERSON1TYPE)
        if entity_resolver:
            entity_type, team_id = entity_resolver(p1_id)
            if entity_type is None:
                _log_unknown_entity(game_id, p1_id, p1_type)
                continue  # skip this event
        else:
            # Fallback to legacy behavior (backward compat)
            team_id = _resolve_player_team(p1_type, p1_id, p1_team)

        player_team = team_id
        ...
```

PERSON1TYPE is used only for a soft validation warning, never for resolution:

```python
# Optional: warn on mismatch
if entity_type == "player" and p1_type not in (4, 5):
    logger.debug(f"PERSON1TYPE={p1_type} but {p1_id} resolved as player")
```

### 5.3 Testability

The resolver is a callable, so tests inject mocks:

```python
def test_unknown_entity_is_skipped():
    def mock_resolver(entity_id):
        return ("player", "Celtics") if entity_id == "Pierce" else (None, None)

    events = normalize_game(rows, ..., entity_resolver=mock_resolver)
    assert not any(e["player_id"] == "2614" for e in events)
```

---

## 6. Classifier Module: `src/lib/pbp/classifier.py`

```python
"""
Source-agnostic event classifier.

Reads core.pbp_event_catalog and classifies raw source rows.
"""


class MatchStrategy(Protocol):
    """How to match a raw source row to a catalog entry."""
    def matches(self, row: dict, match_fields: dict) -> bool: ...
    def build_signature(self, row: dict) -> dict: ...


class Classification:
    """Result of classifying a raw source row."""
    status: str        # 'track' | 'ignore' | 'unreviewed'
    maps_to: str | None
    reason: str | None
    secondary: list
    contributes_to: list


class EventClassifier:
    """Classify raw source rows against the catalog."""

    def __init__(self, catalog_rows: list[dict], strategy: MatchStrategy):
        # Only trust reviewed rows
        self._classified = [r for r in catalog_rows
                            if r["status"] in ("track", "ignore")]
        self._strategy = strategy

    def classify(self, row: dict) -> Classification:
        """Match a row. Raises UnclassifiedEventError if no match."""
        for entry in self._classified:
            if self._strategy.matches(row, entry["match_fields"]):
                return Classification(
                    status=entry["status"],
                    maps_to=entry.get("maps_to"),
                    reason=entry.get("reason"),
                    secondary=entry.get("secondary", []),
                    contributes_to=entry.get("contributes_to", []),
                )
        raise UnclassifiedEventError(self._strategy.build_signature(row), row)
```

### 6.1 Match strategy per source

Each source provides its own matching logic:

```python
# nba_data uses structured field matching
class FieldLookupStrategy:
    def matches(self, row: dict, match_fields: dict) -> bool:
        for field, expected in match_fields.items():
            if field == "text_contains":
                if expected.upper() not in row.get("_desc", "").upper():
                    return False
            elif field == "text_not_contains":
                if expected.upper() in row.get("_desc", "").upper():
                    return False
            else:
                actual = row.get(field)
                if isinstance(expected, list):
                    if actual not in expected:
                        return False
                elif actual != expected:
                    return False
        return True

    def build_signature(self, row: dict) -> dict:
        return {
            "EVENTMSGTYPE": row.get("EVENTMSGTYPE"),
            "EVENTMSGACTIONTYPE": row.get("EVENTMSGACTIONTYPE"),
        }
```

---

## 7. What Changes in the Codebase

### 7.1 New files

| File | Purpose |
|------|---------|
| `src/lib/pbp/__init__.py` | Package init |
| `src/lib/pbp/classifier.py` | Event classification against catalog |
| `src/lib/pbp/entity_resolver.py` | Staging-table entity lookup |
| `src/lib/pbp/discover.py` | Discovery logic (called by CLI `--discover-pbp` flag) |

### 7.2 Modified files

| File | Change |
|------|--------|
| `src/sources/nba_data/pbp_normalizer.py` | Accept `entity_resolver` param; use it over `_resolve_player_team` |
| `src/orchestrator.py` | Build entity_resolver from DB; add classification enforcement in `_maintain_pbp` |
| `src/definitions/schema.py` | Add `core.pbp_event_catalog` table definition |
| `src/definitions/db_columns.py` | Add columns for new table |

### 7.3 New DB table

| Table | Purpose |
|-------|---------|
| `core.pbp_event_catalog` | Known events per source with review status |

### 7.4 What does NOT change

- `game_coverages` -- unchanged, tracks fetch success
- `src/definitions/datasets.py` -- no changes
- `src/definitions/pipeline.py` -- `maintain_pbp` still the same phase
- `src/lib/pbp_accumulator.py` -- accumulation is separate from classification
- `src/sources/nba_data/config.py` -- MSG constants remain as field vocabulary

---

## 8. Implementation Order

### Phase A: Entity Resolver (standalone, testable)

1. Create `src/lib/pbp/__init__.py` and `src/lib/pbp/entity_resolver.py`
2. Write unit tests with mock resolvers
3. Modify `pbp_normalizer.py` to accept optional `entity_resolver` parameter
4. Fall back to existing `_resolve_player_team` if resolver is None
5. Modify `_maintain_pbp` to build resolver from DB and pass to normalizer

### Phase B: Event Catalog Table

1. Add `core.pbp_event_catalog` to `src/definitions/schema.py`
2. Add column definitions to `src/definitions/db_columns.py`
3. Schema builder creates the table

### Phase C: Discovery Script

1. Create `src/lib/pbp/discover.py`
2. Build match signatures from raw rows (source-specific strategy)
3. INSERT into catalog with status='unreviewed', ON CONFLICT UPDATE
4. Print summary report

### Phase D: Classifier + Production Enforcement

1. Create `src/lib/pbp/classifier.py` with `EventClassifier`
2. Integrate into `_maintain_pbp`: check every event, collect unknowns, skip + stop if any
3. Only trust rows with `status IN ('track', 'ignore')`

### Phase E: End-to-End Onboarding

1. Run discovery on a full nba_data season
2. Review unreviewed rows in catalog, set to 'track' or 'ignore'
3. Re-run discovery to confirm zero new unreviewed
4. Run production mode -- should pass clean

---

## 9. Open Questions

1. **Should discovery auto-classify simple cases?** Events like MSGTYPE=12 (period start)
   are unambiguous. Could discovery auto-set status='track' for these? Risk: hides
   unexpected ACTIONTYPE combinations. Recommendation: start with everything
   unreviewed, add auto-classification later if the manual review is too tedious.

2. **What about PERSON1TYPE=6?** We haven't seen it. Discovery will insert it as
   unreviewed when it appears. No special handling needed.

3. **What if a game has events that match unreviewed catalog rows?** Production mode
   treats unreviewed rows as unclassified. The game errors. This forces human review
   before the pipeline can proceed. This is intentional.

4. **Should the normalizer consume the classifier?** Eventually, yes -- replace the
   if/elif chain with classifier calls. But phase this in: start with the classifier
   as a validation layer, then migrate the normalizer to consume it.
