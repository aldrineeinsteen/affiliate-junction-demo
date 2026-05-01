# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Critical Architecture Patterns

- **Dual-write architecture**: Data flows HCD (Cassandra) → Presto/Iceberg via ETL services, NOT bidirectional
- **Query metrics auto-capture**: ALL database operations automatically capture metrics via wrapper classes - never bypass wrappers
- **TTL-based data lifecycle**: HCD tables use 5-10 minute TTLs (300-600s), data expires automatically
- **Batch operations required**: HCD writes MUST use BatchStatement for >100 records, prepared statements mandatory
- **Thread-local query storage**: Web UI uses thread-local storage for request-scoped query metrics via `_request_queries`

## Database Connection Rules

- **Services**: Use `CassandraConnection` and `PrestoConnection` from [`affiliate_common/database_connections.py`](affiliate_common/database_connections.py)
- **Web UI**: Use `cassandra_wrapper` from [`web/cassandra_wrapper.py`](web/cassandra_wrapper.py) and `presto_wrapper` from [`web/presto_wrapper.py`](web/presto_wrapper.py)
- **Never bypass wrappers**: Direct session/connection access breaks metrics capture system
- **Metrics deduplication**: Wrappers automatically deduplicate similar queries using `normalize_query_for_deduplication()`
- **Representative queries for batches**: When executing BatchStatement, provide `representative_query` parameter showing sample INSERT

## Service Management

- Services managed via systemd: `generate_traffic`, `hcd_to_presto`, `presto_to_hcd`, `presto_insights`, `presto_cleanup`, `uvicorn`
- Service stats stored in HCD `services` table with JSON fields: `stats`, `settings`, `query_metrics`
- Stats use 90-datapoint timeseries arrays: `[[timestamp, value], ...]` format
- Services poll `services` table for dynamic configuration updates (no restart needed)
- Use `ServicesManager` from [`affiliate_common/services_manager.py`](affiliate_common/services_manager.py) for service table operations

## Environment & Setup

- Python 3.11 venv required: `.venv/bin/activate` (auto-added to `.bashrc` by setup)
- Presto cert path hardcoded: `/certs/presto.crt` in connection setup
- HCD connection requires datacenter: `HCD_DATACENTER` env var (not optional)
- Web UI runs on port 10000 via uvicorn service
- Setup script enables services in specific order: traffic generator first, then ETL services after 60s delay

## Schema Peculiarities

- HCD partition keys are composite: `(publishers_id, cookie_id, advertisers_id)` for impression_tracking
- Bucket-based partitioning: `impressions_by_minute` uses `(bucket_date, bucket)` where bucket is SMALLINT 0-59
- TIMEUUID clustering: `ts TIMEUUID` used for time-ordered queries, not TIMESTAMP
- JSON text fields: `publishers` and `advertisers` tables store timeseries as TEXT containing JSON arrays
- Presto partitioning: Uses `hour(timestamp)` and `bucket(publishers_id, 5)` - NOT date-based

## Query Execution Gotchas

- Presto doesn't use `?` placeholders - wrapper formats parameters into query string
- HCD prepared statements cache per session - reuse via `session.prepare()`
- Query truncation: Queries >1500 chars auto-truncated in metrics with `[truncated from X chars]` suffix
- Batch metrics: Single metric created per batch, not per statement in batch
- SELECT vs DML detection: Wrappers check query prefix to determine if `fetchall()` needed

## Testing & Debugging

- View service logs: `journalctl -u <service_name> -f`
- Query metrics visible in web UI query panel (right sidebar toggle)
- Restart from clean state: Reboot server (truncates all tables on boot via `truncate_all_tables.service`)
- Presto console available for ad-hoc queries (separate from wx.d interface)
- Connection health checks: Use `test_connection()` method on presto_wrapper