# Project Documentation Rules (Non-Obvious Only)

## Architecture Context

- **Dual-write pattern**: Data flows HCD → Presto/Iceberg via ETL, NOT bidirectional (common misconception)
- **Query metrics system**: ALL queries auto-captured via wrappers - this is architectural, not optional
- **TTL-based lifecycle**: Data expires automatically (5-10 min), no manual cleanup needed
- **Thread-local storage**: Web UI uses `_request_queries` for request-scoped metrics (not global)

## File Organization Quirks

- `affiliate_common/` contains shared service logic, NOT just utilities
- `web/cassandra_wrapper.py` and `web/presto_wrapper.py` are separate from service wrappers in `affiliate_common/`
- Service files (`.service`) are systemd units, not Python services
- Schema files use different syntaxes: `.cql` for HCD, `.sql` for Presto

## Hidden Dependencies

- Presto cert path hardcoded to `/certs/presto.crt` (not in env vars)
- `HCD_DATACENTER` env var is mandatory (connection fails without it)
- Setup script order matters: traffic generator starts first, ETL services wait 60s
- Python 3.11 venv auto-activated via `.bashrc` modification

## Schema Design Rationale

- Composite partition keys prevent hot partitions: `(publishers_id, cookie_id, advertisers_id)`
- TIMEUUID used for clustering (not TIMESTAMP) to enable time-ordered queries with uniqueness
- JSON stored as TEXT fields because HCD doesn't have native JSON type
- Bucket-based partitioning (0-59) distributes load across minute boundaries

## Service Communication

- Services poll `services` table for config updates (no IPC/messaging)
- Stats format is 90-datapoint timeseries: `[[timestamp, value], ...]` in JSON
- Query metrics stored in `services.query_metrics` as JSON array
- Dynamic config changes take effect within 1 minute (polling interval)

## Testing & Debugging Context

- Reboot server to reset state (truncates all tables via `truncate_all_tables.service`)
- Query panel in web UI shows real-time metrics (right sidebar toggle)
- Service logs via `journalctl -u <service_name> -f`
- Presto console separate from wx.d interface (different access points)

## Common Misunderstandings

- Presto doesn't use `?` placeholders - wrapper formats parameters into query string
- Batch operations create single metric, not per-statement metrics
- Query deduplication is automatic via `normalize_query_for_deduplication()`
- Representative query required for batch metrics (not inferred from batch content)