# Project Advanced Coding Rules (Non-Obvious Only)

## Database Wrapper Usage (CRITICAL)

- **NEVER bypass wrappers**: Use `CassandraConnection`/`PrestoConnection` in services, `cassandra_wrapper`/`presto_wrapper` in web UI
- Direct session access breaks automatic metrics capture system
- Batch operations MUST provide `representative_query` parameter: `execute_query(batch, representative_query="INSERT INTO...")`

## HCD/Cassandra Patterns

- Prepared statements are cached per session - reuse via `session.prepare()` before loops
- Batch operations required for >100 records: Use `BatchStatement(batch_type=BatchType.UNLOGGED)`
- Parameters use `?` placeholders: `execute_query("SELECT * FROM table WHERE id = ?", [value])`
- Composite partition keys required: `(publishers_id, cookie_id, advertisers_id)` for impression_tracking

## Presto Query Patterns

- NO `?` placeholders - wrapper formats parameters into query string via `_format_presto_query()`
- Connection uses hardcoded cert path: `/certs/presto.crt` (not configurable)
- SELECT detection: Wrappers check query prefix to determine if `fetchall()` needed
- Partitioning uses functions: `hour(timestamp)` and `bucket(publishers_id, 5)` - NOT date columns

## Service Implementation

- Services MUST use `ServicesManager` from [`affiliate_common/services_manager.py`](affiliate_common/services_manager.py)
- Stats stored as 90-datapoint timeseries: `[[timestamp, value], ...]` format in JSON text field
- Poll `services` table for dynamic config updates (no restart needed)
- Query metrics auto-captured and stored in `services.query_metrics` JSON field

## Schema Constraints

- TTL is automatic: 300-600s on HCD tables, data expires without manual cleanup
- TIMEUUID for clustering: Use `ts TIMEUUID` not `TIMESTAMP` for time-ordered queries
- JSON in TEXT fields: `publishers.impressions` and `advertisers.conversions` store JSON arrays as TEXT
- Bucket partitioning: `impressions_by_minute` uses `bucket SMALLINT` (0-59) in composite partition key

## Environment Requirements

- `HCD_DATACENTER` env var is mandatory (not optional) for DCAwareRoundRobinPolicy
- Python 3.11 venv at `.venv/bin/activate` (auto-added to `.bashrc`)
- Web UI port hardcoded to 10000 in uvicorn service

## Browser/MCP Tool Access

- Browser tools available for testing web UI at `http://localhost:10000`
- Query panel visible in web UI right sidebar (toggle button)
- MCP tools can interact with running services via systemd commands