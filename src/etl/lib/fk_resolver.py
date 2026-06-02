"""
The Glass - FK Resolver Helpers

Shared helpers for resolving source IDs to internal database keys using the 
table registry metadata.
"""

from typing import Any, Dict, Iterable, Tuple

from src.core.definitions.schema import TABLES
from src.core.lib.postgres import quote_col
from src.etl.lib.sources_resolver import get_source_id_column


def load_fk_mapping(
    conn: Any,
    ref_schema: str,
    ref_table: str,
    ref_column: str,
    source_key: str,
    source_ids: Iterable[Any] = None,
) -> Dict[str, int]:
    """Return ``{str(source_id): target_id}`` dynamically for a referenced table."""
    src_col = get_source_id_column(source_key)

    sql_base = (
        f"SELECT {quote_col(src_col)}, {quote_col(ref_column)} "
        f"FROM {ref_schema}.{ref_table}"
    )

    with conn.cursor() as cur:
        if source_ids is None:
            cur.execute(sql_base)
        else:
            ids_list = [v for v in source_ids if v is not None]
            if not ids_list:
                return {}
            cur.execute(
                sql_base + f" WHERE {quote_col(src_col)} = ANY(%s)",
                (ids_list,),
            )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def resolve_fk_value_columns(
    rows: Dict[Any, Dict[str, Any]],
    conn: Any,
    league_key: str,
    source_key: str,
    table_name: str,
) -> Tuple[Dict[Any, Dict[str, Any]], int]:
    """Translate FK source-id values using explicit table config strategies.

    Uses the FK metadata `strategy` to determine resolution approach.
    Rows that cannot be fully resolved against a lookup strategy are dropped.
    """
    meta = TABLES.get(table_name, {})

    fks_to_resolve = [
        fk for fk in meta.get('foreign_keys', [])
        if fk['strategy'] == 'profile_lookup'
    ]

    if not fks_to_resolve:
        return rows, 0

    fk_maps: Dict[str, Dict[str, int]] = {}
    for fk in fks_to_resolve:
        col = fk['column']
        raw_values = [row.get(col) for row in rows.values() if row.get(col) is not None]
        
        fk_maps[col] = load_fk_mapping(
            conn, 
            ref_schema=fk['ref_schema'],
            ref_table=fk['ref_table'], 
            ref_column=fk['ref_column'],
            source_key=source_key, 
            source_ids=raw_values
        )

    dropped = 0
    resolved: Dict[Any, Dict[str, Any]] = {}
    for key, row in rows.items():
        new_row = dict(row)
        ok = True
        for fk in fks_to_resolve:
            col = fk['column']
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
