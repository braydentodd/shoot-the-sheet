"""
Shoot the Sheet - FK Resolver Helpers

Shared helpers for resolving source IDs to internal database keys using the
table registry metadata.
"""

from typing import Any, Dict, Iterable, Optional, Tuple

from src.definitions.schema import get_table


def load_fk_mapping(
    conn: Any,
    ref_schema: str,
    ref_table: str,
    identity_code: str,
    source_ids: Optional[Iterable[Any]] = None,
) -> Dict[str, int]:
    """Return ``{str(ext_id): sts_id}`` via the identity registry.

    Routes to ``identities_players`` or ``identities_teams`` based on
    *ref_table* (e.g. ``"players"`` → identities_players).
    """
    if ref_table in ("players", "player"):
        id_table = "core.identities_players"
        id_col = "player_id"
    elif ref_table in ("teams", "team"):
        id_table = "core.identities_teams"
        id_col = "team_id"
    else:
        raise ValueError(f"Unsupported ref_table for FK mapping: {ref_table!r}")

    sql = f"SELECT i.ext_id, i.{id_col} FROM {id_table} i WHERE i.identity = %s"

    with conn.cursor() as cur:
        if source_ids is None:
            cur.execute(sql, (identity_code,))
        else:
            ids_list = [str(v) for v in source_ids if v is not None]
            if not ids_list:
                return {}
            cur.execute(
                sql + " AND i.ext_id = ANY(%s)",
                (identity_code, ids_list),
            )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def resolve_fk_value_columns(
    rows: Dict[Any, Dict[str, Any]],
    conn: Any,
    league_code: str,
    identity_code: str,
    table_name: str,
) -> Tuple[Dict[Any, Dict[str, Any]], int]:
    """Translate FK source-id values using explicit table config strategies.

    Uses the FK metadata `strategy` to determine resolution approach.
    Rows that cannot be fully resolved against a lookup strategy are dropped.
    """
    try:
        meta = get_table(table_name) if "." in table_name else {}
    except KeyError:
        meta = {}

    fks_to_resolve = [
        fk
        for fk in (meta.get("foreign_keys") or [])
        if fk.get("strategy") == "profile_lookup"
    ]

    if not fks_to_resolve:
        return rows, 0

    fk_maps: Dict[str, Dict[str, int]] = {}
    for fk in fks_to_resolve:
        # Composite FKs: use the first column as the lookup key.
        cols = fk.get("columns", [])
        if not cols:
            continue
        col = cols[0]
        raw_values = [
            str(row.get(col)) for row in rows.values() if row.get(col) is not None
        ]

        fk_maps[col] = load_fk_mapping(
            conn,
            ref_schema=fk["ref_schema"],
            ref_table=fk["ref_table"],
            identity_code=identity_code,
            source_ids=raw_values,
        )

    dropped = 0
    resolved: Dict[Any, Dict[str, Any]] = {}
    for key, row in rows.items():
        new_row = dict(row)
        ok = True
        for fk in fks_to_resolve:
            cols = fk.get("columns", [])
            if not cols:
                continue
            col = cols[0]
            raw = new_row.get(col)
            if raw is None:
                continue
            mapped = fk_maps[col].get(str(raw))
            if mapped is None:
                ok = False
                break
            new_row[col] = mapped
        if ok:
            resolved[key] = new_row
        else:
            dropped += 1

    return resolved, dropped
