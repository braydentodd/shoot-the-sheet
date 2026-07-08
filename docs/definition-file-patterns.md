# Definition File Patterns

Canonical conventions for every file under `src/definitions/`. Follow these when
adding or modifying config dicts.

---

## Core Principle: Derive Don't Duplicate

Every VALID_* frozenset must be one of:

1. **Derived** — computed from the config data itself, e.g.
   `frozenset(PIPELINE.keys())`, `frozenset(get_args(Transform))`. These cannot
   drift from the source of truth.
2. **Domain knowledge** — externally defined constants with no project data
   source, e.g. `VALID_PG_TYPES`, `VALID_SHAPES`. These are validated against
   PostgreSQL or other external systems, not against project code.

Anything else is a drift risk. If you find a manually duplicated frozenset,
either derive it or delete it.

---

## File Layout (standard template)

```
"""
Shoot the Sheet - <File Purpose>
"""
# --- 1. Imports ---
from typing import Dict, List, Literal, TypedDict, Union

# --- 2. Literal type aliases used in TypedDict fields ---
# Only if you run a static type checker (pyright). One alias per constrained field.

# --- 3. TypedDicts (no suffix) ---
# One TypedDict per config dict. total=False when all fields are optional.

# --- 4. Config dicts ---
# Annotated with TypedDict. Literal values everywhere they apply.

# --- 5. Derived value sets ---
# Computed from the config dicts above. Zero maintenance.
```

---

## Naming Conventions

| Kind | Convention | Examples |
|---|---|---|
| Config dict | `UPPER_SNAKE_CASE` | `DATASETS`, `DB_COLUMNS`, `SOURCE_RATE_LIMITS` |
| TypedDict | `PascalCase`, no suffix | `Dataset`, `Column`, `League`, `Source` |
| Literal alias | `PascalCase` | `Coverage`, `ExecutionTier`, `Transform`, `Event` |
| Derived frozenset | `VALID_UPPER_SNAKE` | `VALID_PHASES`, `VALID_SOURCES`, `VALID_TRANSFORMS` |
| Domain frozenset | `VALID_UPPER_SNAKE` | `VALID_PG_TYPES`, `VALID_SHAPES` |
| Standalone constant | `UPPER_SNAKE_CASE` | `ENTITY_CHUNK_SIZE`, `TWO_DIGIT_PIVOT` |

### What NOT to use

- No `Def` suffix on TypedDicts (`Dataset` not `DatasetDef`)
- No `T` suffix on Literal aliases (`Transform` not `TransformT`)
- No `VALID_` prefix on derived sets that are only for internal use (keep them
  but don't export unless imported elsewhere)

---

## TypedDict Rules

- Define one TypedDict per config dict.
- Use `total=False` when the TypedDict only has optional fields (e.g.
  `SourceMapping`, `DatasetMapping`).
- Annotate constrained string fields with `Literal` in the TypedDict body:
  ```python
  class League(TypedDict):
      gender: Literal["M", "W"]
      season_format: str
  ```
- Do NOT use `Any` in TypedDict fields. If a value shape is truly dynamic,
  use `Dict[str, Any]` or `Union` with known alternatives.

---

## Literal Type Alias Rules

- Define a Literal alias **only** when it is consumed by at least one
  TypedDict field annotation.
- Place the alias in the same file as the TypedDict that uses it.
- When the Literal values match a runtime TRANSFORMS dict or other executable
  registry, derive the VALID_* set from the Literal via `get_args()`:
  ```python
  Transform = Literal["safe_int", "safe_str", ...]
  VALID_TRANSFORMS: FrozenSet[str] = frozenset(get_args(Transform))
  ```
- Remove Literal aliases that are not used in any TypedDict field. They are
  dead code.

---

## Deriving Validation Sets

| Current data source | Derived set | Location |
|---|---|---|
| `PIPELINE.keys()` | `VALID_CLUSTERS` | `pipeline.py` |
| All PIPELINE phases | `VALID_PHASES` | `pipeline.py` |
| `SOURCES.keys()` | `VALID_SOURCES` | `sources.py` |
| `DATASETS.keys()` | `VALID_IDENTITIES` | `datasets.py` |
| `SCHEMAS["staging"]` | `VALID_STAGING_TABLES` | `schema.py` |
| `SCHEMAS["core"]` | `VALID_CORE_TABLES` | `schema.py` |
| `SCHEMAS["intermediate"]` | `VALID_INTERMEDIATE_TABLES` | `schema.py` |
| `get_args(Transform)` | `VALID_TRANSFORMS` | `db_columns.py` |
| `LEAGUE_FORMAT_TO_SHAPE.keys()` | `VALID_LEAGUE_SEASON_FORMATS` | `season_formats.py` |

---

## Cross-Config Validation

The runtime validator in `src/lib/config_validation.py` catches:

- Unknown PostgreSQL types in `DB_COLUMNS`
- Unknown identity references in `dataset_mapping`
- Unknown table references in `discovery_tables` and FK targets
- Unknown transforms in `dataset_mapping`
- Unknown clusters/phases in `PIPELINE`
- Unknown source codes in `SOURCE_RATE_LIMITS`
- Dataset references that don't exist in `DATASETS`

These catch drift that static types alone cannot (e.g. a table name string
that doesn't match any entry in `SCHEMAS`).
