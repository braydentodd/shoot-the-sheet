"""
Shoot the Sheet - ETL Execution Configuration

Tuning parameters for ETL execution engine performance and resource management.

These constants control batch sizing, memory usage, and execution behavior
during the ETL pipeline.
"""

# Maximum entities to accumulate before flushing to database.
ENTITY_CHUNK_SIZE = 500

# Maximum rows per execute_values batch in bulk_upsert operations.
DEFAULT_BATCH_SIZE = 500

# Number of days the season detector looks back when checking for recent
# game activity.  If any games were played within this window, the league
# is considered active and stats columns are refreshed.  Otherwise,
# only profile / roster columns are updated.
GAME_LOOKBACK_DAYS = 8
