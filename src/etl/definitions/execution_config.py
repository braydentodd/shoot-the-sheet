"""
The Glass - ETL Execution Configuration

Tuning parameters for ETL execution engine performance and resource management.

These constants control batch sizing, memory usage, and execution behavior
during the ETL pipeline.
"""

# Maximum entities to accumulate before flushing to database.
# Higher values = more memory usage but fewer DB round-trips.
# Lower values = less memory usage but more DB overhead.
# Recommended: 200-500 for typical workloads, 100-200 for memory-constrained environments.
ENTITY_CHUNK_SIZE = 200

# Maximum rows per execute_values batch in bulk_upsert operations.
# Controls how many rows are sent to PostgreSQL in a single INSERT statement.
# Higher values = fewer round-trips but larger query strings.
# PostgreSQL can handle large batches efficiently; 500 is a good default.
DEFAULT_BATCH_SIZE = 500
