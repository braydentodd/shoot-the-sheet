"""
The Glass - ETL Execution Configuration

Tuning parameters for ETL execution engine performance and resource management.

These constants control batch sizing, memory usage, and execution behavior
during the ETL pipeline.
"""

# Maximum entities to accumulate before flushing to database.
ENTITY_CHUNK_SIZE = 500

# Maximum rows per execute_values batch in bulk_upsert operations.
DEFAULT_BATCH_SIZE = 500
