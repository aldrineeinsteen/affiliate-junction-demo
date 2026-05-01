# Project Architecture Rules (Non-Obvious Only)

## Core Architecture Constraints

- **Dual-write is unidirectional**: HCD → Presto/Iceberg only, NOT bidirectional (architectural decision)
- **Query metrics are mandatory**: Wrappers auto-capture ALL queries - bypassing breaks observability system
- **TTL-based expiration**: Data lifecycle managed by TTL (300-600s), not manual cleanup processes
- **Thread-local isolation**: Web UI uses thread-local storage for request-scoped metrics (prevents cross-request pollution)

## Service Orchestration

- **Startup order critical**: `generate_traffic` starts first, ETL services wait 60s for Presto DDL completion
- **Dynamic configuration**: Services poll `services` table every minute for config updates (no restart needed)
- **Stats format standardized**: 90-datapoint timeseries as `[[timestamp, value], ...]` in JSON text fields
- **Systemd managed**: All services are systemd units, not standalone processes

## Data Flow Architecture

- **ETL pattern**: `generate_traffic` → HCD → `hcd_to_presto` → Presto/Iceberg → `presto_to_hcd` → HCD (for aggregates)
- **Batch processing**: HCD writes use BatchStatement for >100 records (performance requirement)
- **Metrics deduplication**: Similar queries auto-deduplicated via `normalize_query_for_deduplication()`
- **Representative queries**: Batch operations require sample query for metrics (not inferred)

## Schema Design Decisions

- **Composite partition keys**: `(publishers_id, cookie_id, advertisers_id)` prevents hot partitions
- **Bucket-based partitioning**: `impressions_by_minute` uses `(bucket_date, bucket)` where bucket is SMALLINT 0-59
- **TIMEUUID clustering**: Enables time-ordered queries with uniqueness (TIMESTAMP lacks uniqueness)
- **JSON as TEXT**: HCD stores JSON in TEXT fields (no native JSON type)
- **Presto function partitioning**: Uses `hour(timestamp)` and `bucket(publishers_id, 5)` - NOT date columns

## Connection Architecture

- **Wrapper separation**: Services use `affiliate_common/database_connections.py`, web UI uses `web/*_wrapper.py`
- **Cert path hardcoded**: Presto connection uses `/certs/presto.crt` (not configurable via env)
- **Datacenter required**: `HCD_DATACENTER` env var mandatory for DCAwareRoundRobinPolicy
- **Prepared statement caching**: HCD prepared statements cached per session (reuse pattern required)

## Performance Patterns

- **Query truncation**: Queries >1500 chars auto-truncated in metrics (prevents memory bloat)
- **Batch metrics**: Single metric per batch, not per statement (reduces overhead)
- **SELECT detection**: Wrappers check query prefix to determine if `fetchall()` needed
- **Parameter formatting**: Presto formats parameters into query string (no `?` placeholders)

## Testing & Reset Strategy

- **Clean state via reboot**: Server reboot triggers `truncate_all_tables.service` (resets all data)
- **Query visibility**: Web UI query panel (right sidebar) shows real-time metrics
- **Service logs**: Access via `journalctl -u <service_name> -f`
- **Connection health**: Use `test_connection()` method on presto_wrapper

## Hidden Coupling

- **Services table dependency**: All services depend on `services` table for stats/config storage
- **Metrics capture coupling**: Query execution tightly coupled to metrics system (cannot be disabled)
- **TTL coupling**: Data lifecycle coupled to TTL settings (no manual cleanup paths)
- **Wrapper coupling**: Direct session access breaks metrics capture (architectural constraint)