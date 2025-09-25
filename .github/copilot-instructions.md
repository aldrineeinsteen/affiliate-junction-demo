# AI Coding Agent Instructions - Affiliate Junction Demo

## Project Overview
This is a **federated data processing system** demonstrating affiliate marketing analytics across **IBM watsonx.data**. The system generates synthetic affiliate marketing data and processes it through a **dual-write pattern** between HCD (Cassandra) for real-time operations and Presto/Iceberg for analytics.

## Architecture & Data Flow

### Core Components
- **`generate_traffic.py`**: Synthetic data generator (publishers, advertisers, cookies, impressions, conversions)
- **`hcd_to_presto.py`**: ETL pipeline transferring and aggregating data from Cassandra to Presto/Iceberg  
- **`presto_cleanup.py`**: Data lifecycle management for Presto storage
- **`web/main.py`**: FastAPI web UI with real-time and analytical views

### Data Pipeline Pattern
1. **Real-time writes** → HCD (Cassandra) with 6-minute TTL for operational queries
2. **ETL aggregation** → Presto/Iceberg with hourly partitioning for analytics  
3. **Dual table structure**: Both `*_tracking` (aggregated) and `*_by_minute` (raw events) tables

## Critical Developer Workflows

### Setup & Installation
```bash
# Initial setup (requires watsonx.data + HCD installed)
./setup.sh                              # Installs deps, creates .env, enables services
```

### Service Management (systemd-based)
```bash
# View all service status
sudo systemctl status generate_traffic hcd_to_presto presto_cleanup

# Monitor real-time logs
journalctl -u generate_traffic -f
journalctl -u hcd_to_presto -f
```

### Database Access
```bash
# HCD/Cassandra console
./hcd-1.2.3/bin/hcd cqlsh 172.17.0.1 -u cassandra -p cassandra

# Quick data verification
SELECT COUNT(*) FROM affiliate_junction.impression_tracking;
```

### Web UI Development
```bash
cd web/
uvicorn main:app --host 0.0.0.0 --port 10000 --reload
```

### Testing & Development
```bash
# Always use the project's virtual environment for testing
source .venv/bin/activate
python script_name.py
```

## Project-Specific Conventions

### Environment Configuration
- **`env-sample` → `.env`**: Contains all connection strings and scaling parameters
- **Key configs**: `AFFILIATE_JUNCTION_TRAFFIC_MIN=10000` (impressions/min), `AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT=10` (hash buckets)
- **Connection pattern**: All services share identical connection logic (auth, timeouts, SSL certs)

### Data Modeling Patterns
- **Composite partition keys**: `(publishers_id, cookie_id, advertisers_id)` for impression aggregation
- **Time-bucketing**: `bucket_date` + `bucket` for write distribution across Cassandra partitions
- **TTL strategy**: 6min for operational data, 10min for raw events, 6hrs for aggregated views

### Code Structure Rules
1. **Database connections**: Always use connection pooling with timeouts and retry logic
2. **Batch operations**: Process in 10,000-record batches for Presto inserts
3. **Error handling**: Services restart on failure (systemd `Restart=on-failure`)
4. **Schema execution**: Both `.cql` and `.sql` files are executed during service startup


### Integration Points
- **Presto SSL**: All connections require `/certs/presto.crt` certificate validation
- **Spark integration**: ETL uses PySpark for DataFrame operations before Presto writes
- **Timing coordination**: ETL runs at "minute+5 seconds" to allow traffic generation to complete

## Common Debugging Patterns

### Data Pipeline Issues
- Check service logs first: `journalctl -u [service_name] -f`
- Verify `.env` file matches `env-sample` structure
- Confirm HCD keyspace and Presto schema creation via manual connection

### Performance Tuning
- Adjust `AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT` for write distribution
- Monitor Cassandra partition sizes in `impressions_by_minute` table
- Scale `TRAFFIC_MIN` and `SALES_MIN` based on system capacity

## File Locations for Common Tasks
- **Schema changes**: `hcd_schema.cql` and `presto_schema.sql`
- **Service configuration**: `*.service` files (systemd units)
- **ETL logic**: `hcd_to_presto.py` (data aggregation and transfer)
- **Web templates**: `web/templates/` (Jinja2 with partials)
- **Connection logic**: Reused across all Python files with identical patterns

## Key Dependencies
- **Cassandra**: `cassandra-driver` with `DCAwareRoundRobinPolicy`
- **Presto**: `presto-python-client` with BasicAuthentication + SSL
- **Spark**: `pyspark` for DataFrame processing in ETL pipeline
- **Web**: `fastapi` + `uvicorn` for API and template rendering

When modifying this codebase, maintain the existing connection patterns, respect the TTL configurations, and ensure all services can restart gracefully via systemd.