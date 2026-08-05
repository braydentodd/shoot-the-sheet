"""
Shoot the Sheet - Schema Registry Resolver

Lookup helpers over the table registry in
:data:`src.definitions.schema.SCHEMAS`.  Kept out of the definitions
module per the convention: definitions hold config, lib holds code.
"""

from collections.abc import Iterator

from src.definitions.schema import SCHEMAS, Table


def get_table(qualified_name: str) -> Table:
    """Look up a table definition by ``'schema.table'`` qualified name.

    Raises ``KeyError`` if the schema or table is not registered.
    """
    schema, table = qualified_name.split(".", 1)
    return SCHEMAS[schema][table]


def iter_tables() -> Iterator[tuple[str, str, str, Table]]:
    """Yield ``(qualified_name, schema, table, Table)`` for every table."""
    for schema, tables in SCHEMAS.items():
        for table, meta in tables.items():
            yield f"{schema}.{table}", schema, table, meta
