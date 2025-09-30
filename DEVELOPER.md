# Developer Guide: Database Queries and Metrics

This guide explains how to execute Presto and HCD (Cassandra) queries in the Affiliate Junction demo system, both in service components and the web UI. It covers query execution patterns, metrics capture, and provides comprehensive examples.

## Table of Contents

1. [Query Execution Overview](#query-execution-overview)
2. [Service-Level Query Execution](#service-level-query-execution)
3. [Web UI Query Execution](#web-ui-query-execution)
4. [Query Metrics Capture](#query-metrics-capture)
5. [Example Metrics Output](#example-metrics-output)
6. [Performance Best Practices](#performance-best-practices)
7. [Debugging and Monitoring](#debugging-and-monitoring)

## Query Execution Overview

The system provides two database connection patterns:

- **HCD (Cassandra)**: Real-time operational data with 6-minute TTL
- **Presto/Iceberg**: Analytics-focused data with hourly partitioning

Both connections implement comprehensive query metrics capture for performance monitoring and debugging.

### Architecture Pattern

```
Service Layer (generate_traffic.py, hcd_to_presto.py, presto_cleanup.py)
├── CassandraConnection (from affiliate_common.database_connections)
└── PrestoConnection (from affiliate_common.database_connections)

Web UI Layer (web/main.py, web/*_operations.py)
├── cassandra_wrapper (from web.cassandra_wrapper)
└── presto_wrapper (from web.presto_wrapper)
```

## Service-Level Query Execution

### HCD/Cassandra in Services

Services use the shared `CassandraConnection` class from `affiliate_common.database_connections`:

```python
from affiliate_common import CassandraConnection

# Initialize connection
cassandra_connection = CassandraConnection()
session = cassandra_connection.connect()

# Execute simple query
result = cassandra_connection.execute_query(
    query="SELECT COUNT(*) FROM impression_tracking WHERE publishers_id = ?",
    parameters=['PID_TECH_001'],
    query_description="Get impression count for publisher"
)

# Execute batch operations (as seen in generate_traffic.py)
from cassandra.query import BatchStatement, BatchType

batch = BatchStatement(batch_type=BatchType.UNLOGGED)
for record in impression_data:
    batch.add(prepared_statement, [
        record['publishers_id'],
        record['cookie_id'],
        record['timestamp'],
        record['advertisers_id'],
        record['impressions']
    ])

# Execute with metrics capture
cassandra_connection.execute_query(
    query=batch,  # Pass batch object directly
    query_description="Batch insert impression tracking records",
    representative_query="INSERT INTO impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions) VALUES (?, ?, ?, ?, ?)"
)
```

### Presto in Services

Services use the shared `PrestoConnection` class:

```python
from affiliate_common import PrestoConnection

# Initialize connection
presto_client = PrestoConnection()
connection = presto_client.connect()

# Execute query with retry logic
result = presto_client.execute_query(
    query="""
    SELECT publishers_id, 
           SUM(impressions) as total_impressions,
           COUNT(DISTINCT cookie_id) as unique_cookies
    FROM iceberg.affiliate_junction.impression_tracking 
    WHERE bucket_date >= CURRENT_DATE - INTERVAL '1' DAY
    GROUP BY publishers_id
    ORDER BY total_impressions DESC
    LIMIT 10
    """,
    query_description="Top publishers by impression volume (last 24h)"
)
```

## Web UI Query Execution

### HCD/Cassandra in Web UI

The web UI uses `cassandra_wrapper` which provides the same metrics capture:

```python
from web.cassandra_wrapper import cassandra_wrapper

# Simple query execution
def get_publisher_metrics(publisher_id: str):
    query = """
    SELECT timestamp, impressions 
    FROM impression_tracking 
    WHERE publishers_id = ? 
    AND timestamp >= ?
    """
    
    result = cassandra_wrapper.execute_query_simple(
        query=query,
        parameters=[publisher_id, yesterday],
        query_description=f"Get metrics for publisher {publisher_id}"
    )
    return result

# Query with retry logic
def get_conversion_data():
    query = """
    SELECT advertisers_id, cookie_id, timestamp
    FROM conversion_tracking
    WHERE timestamp >= ?
    LIMIT 1000
    """
    
    result = cassandra_wrapper.execute_query(
        query=query,
        parameters=[start_time],
        max_retries=3,
        query_description="Recent conversion data for dashboard"
    )
    return result
```

### Presto in Web UI

The web UI uses `presto_wrapper` for analytics queries:

```python
from web.presto_wrapper import presto_wrapper

# Execute analytics query
def get_fraud_patterns():
    query = """
    WITH fraud_cookies AS (
        SELECT cookie_id 
        FROM iceberg.affiliate_junction.impression_tracking 
        WHERE bucket_date >= CURRENT_DATE - INTERVAL '7' DAY
        GROUP BY cookie_id
        HAVING COUNT(DISTINCT publishers_id) > 10
    )
    SELECT 
        i.cookie_id,
        COUNT(DISTINCT i.publishers_id) as publisher_count,
        COUNT(DISTINCT i.advertisers_id) as advertiser_count,
        SUM(i.impressions) as total_impressions
    FROM iceberg.affiliate_junction.impression_tracking i
    JOIN fraud_cookies f ON i.cookie_id = f.cookie_id
    WHERE i.bucket_date >= CURRENT_DATE - INTERVAL '7' DAY
    GROUP BY i.cookie_id
    ORDER BY publisher_count DESC
    """
    
    result = presto_wrapper.execute_query_simple(
        query=query,
        query_description="Detect potential fraud patterns"
    )
    return result

# Query with parameters
def get_advertiser_performance(advertiser_id: str, days: int):
    query = """
    SELECT 
        DATE(bucket_date) as date,
        SUM(impressions) as daily_impressions,
        COUNT(DISTINCT cookie_id) as unique_users
    FROM iceberg.affiliate_junction.impression_tracking
    WHERE advertisers_id = ?
    AND bucket_date >= CURRENT_DATE - INTERVAL ? DAY
    GROUP BY DATE(bucket_date)
    ORDER BY date DESC
    """
    
    result = presto_wrapper.execute_query_with_retry(
        query=query,
        parameters=[advertiser_id, str(days)],
        query_description=f"Performance metrics for advertiser {advertiser_id}"
    )
    return result
```

## Query Metrics Capture

All database connections automatically capture comprehensive metrics for every query executed.

### Accessing Metrics

**In Services:**
```python
# Get metrics from connection
cassandra_metrics = cassandra_connection.get_query_metrics()
presto_metrics = presto_client.get_query_metrics()

# Update service stats (as done in generate_traffic.py)
services_manager.update_query_metrics(
    cassandra_metrics=cassandra_metrics,
    presto_metrics=presto_metrics
)

# Clear metrics after storing
cassandra_connection.clear_query_metrics()
presto_client.clear_query_metrics()
```

**In Web UI:**
```python
# Get metrics for current request
cassandra_queries = cassandra_wrapper.get_request_queries()
presto_queries = presto_wrapper.get_request_queries()

# Get all metrics since last clear
all_cassandra_metrics = cassandra_wrapper.get_query_history()
all_presto_metrics = presto_wrapper.get_all_queries()

# Get summary statistics
presto_summary = presto_wrapper.get_query_summary()
```

### Metrics Deduplication

The system automatically deduplicates similar queries to reduce noise:

```python
# These queries would be deduplicated:
execute_query("SELECT * FROM impression_tracking WHERE publishers_id = 'PID_001'")
execute_query("SELECT * FROM impression_tracking WHERE publishers_id = 'PID_002'")
execute_query("SELECT * FROM impression_tracking WHERE publishers_id = 'PID_003'")

# Result: Single metric with repeat_count = 3
```

## Example Metrics Output

### Single Query Metric (HCD/Cassandra)

```json
{
    "query_id": "cql_45_1727734523456",
    "query_text": "SELECT publishers_id, SUM(impressions) FROM impression_tracking WHERE timestamp >= ? GROUP BY publishers_id",
    "query_description": "Get impression totals by publisher",
    "query_type": "HCD",
    "parameters": ["2024-09-30T14:00:00.000Z"],
    "start_time": "2024-09-30T14:15:23.456Z",
    "end_time": "2024-09-30T14:15:23.678Z",
    "execution_time_ms": 222.34,
    "rows_returned": 156,
    "success": true,
    "error_message": null,
    "prepared": true,
    "retry_count": 0,
    "formatted_query_text": "SELECT publishers_id,\n       SUM(impressions)\nFROM impression_tracking\nWHERE timestamp >= ?\nGROUP BY publishers_id",
    "repeat_count": 1
}
```

### Batch Operation Metric (HCD/Cassandra)

```json
{
    "query_id": "cql_46_1727734524789",
    "query_text": "-- <BatchStatement type=UNLOGGED, statements=2500, consistency=Not Set>\nINSERT INTO impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions)\nVALUES (?, ?, ?, ?, ?)",
    "query_description": "Batch insert impression tracking records",
    "query_type": "HCD",
    "parameters": null,
    "start_time": "2024-09-30T14:15:24.789Z",
    "end_time": "2024-09-30T14:15:25.123Z",
    "execution_time_ms": 334.12,
    "rows_returned": 0,
    "success": true,
    "error_message": null,
    "prepared": true,
    "retry_count": 0,
    "formatted_query_text": "-- <BatchStatement type=UNLOGGED, statements=2500, consistency=Not Set>\nINSERT INTO impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions)\nVALUES (?, ?, ?, ?, ?)",
    "repeat_count": 1
}
```

### Analytics Query Metric (Presto)

```json
{
    "query_id": "presto_23_1727734525456",
    "query_text": "WITH fraud_analysis AS (SELECT cookie_id, COUNT(DISTINCT publishers_id) as pub_count FROM iceberg.affiliate_junction.impression_tracking WHERE bucket_date >= CURRENT_DATE - INTERVAL '7' DAY GROUP BY cookie_id HAVING COUNT(DISTINCT publishers_id) > 10) SELECT f.cookie_id, f.pub_count, SUM(i.impressions) as total_impressions FROM fraud_analysis f JOIN iceberg.affiliate_junction.impression_tracking i ON f.cookie_id = i.cookie_id WHERE i.bucket_date >= CURRENT_DATE - INTERVAL '7' DAY GROUP BY f.cookie_id, f.pub_count ORDER BY f.pub_count DESC LIMIT 50",
    "query_description": "Detect fraud patterns across publishers",
    "query_type": "Presto",
    "parameters": null,
    "start_time": "2024-09-30T14:15:25.456Z",
    "end_time": "2024-09-30T14:15:27.890Z",
    "execution_time_ms": 2434.56,
    "rows_returned": 12,
    "success": true,
    "error_message": null,
    "prepared": false,
    "retry_count": 0,
    "formatted_query_text": "WITH fraud_analysis AS\n  (SELECT cookie_id,\n          COUNT(DISTINCT publishers_id) AS pub_count\n   FROM iceberg.affiliate_junction.impression_tracking\n   WHERE bucket_date >= CURRENT_DATE - INTERVAL '7' DAY\n   GROUP BY cookie_id\n   HAVING COUNT(DISTINCT publishers_id) > 10)\nSELECT f.cookie_id,\n       f.pub_count,\n       SUM(i.impressions) AS total_impressions\nFROM fraud_analysis f\nJOIN iceberg.affiliate_junction.impression_tracking i ON f.cookie_id = i.cookie_id\nWHERE i.bucket_date >= CURRENT_DATE - INTERVAL '7' DAY\nGROUP BY f.cookie_id,\n         f.pub_count\nORDER BY f.pub_count DESC\nLIMIT 50",
    "repeat_count": 1
}
```

### Deduplicated Query Metric

```json
{
    "query_id": "presto_24_1727734528123",
    "query_text": "SELECT COUNT(*) FROM iceberg.affiliate_junction.impression_tracking WHERE publishers_id = ?",
    "query_description": "Count impressions for publisher",
    "query_type": "Presto",
    "parameters": ["PID_TECH_..."],
    "start_time": "2024-09-30T14:15:28.789Z",
    "end_time": "2024-09-30T14:15:28.823Z",
    "execution_time_ms": 34.12,
    "rows_returned": 1,
    "success": true,
    "error_message": null,
    "prepared": false,
    "retry_count": 0,
    "formatted_query_text": "-- Query repeated 47 times\nSELECT COUNT(*)\nFROM iceberg.affiliate_junction.impression_tracking\nWHERE publishers_id = ?",
    "repeat_count": 47
}
```

### Failed Query Metric

```json
{
    "query_id": "presto_25_1727734529456",
    "query_text": "SELECT * FROM iceberg.affiliate_junction.nonexistent_table",
    "query_description": "Test query for error handling",
    "query_type": "Presto",
    "parameters": null,
    "start_time": "2024-09-30T14:15:29.456Z",
    "end_time": "2024-09-30T14:15:29.567Z",
    "execution_time_ms": 111.23,
    "rows_returned": null,
    "success": false,
    "error_message": "Table 'iceberg.affiliate_junction.nonexistent_table' does not exist",
    "prepared": false,
    "retry_count": 2,
    "formatted_query_text": "SELECT *\nFROM iceberg.affiliate_junction.nonexistent_table",
    "repeat_count": 1
}
```

### Query Summary Statistics

```json
{
    "total_queries": 156,
    "successful_queries": 154,
    "failed_queries": 2,
    "average_execution_time_ms": 287.45,
    "total_rows_returned": 45892,
    "query_type_breakdown": {
        "HCD": {
            "count": 98,
            "average_execution_time_ms": 145.67,
            "total_rows_returned": 12456
        },
        "Presto": {
            "count": 58,
            "average_execution_time_ms": 521.23,
            "total_rows_returned": 33436
        }
    }
}
```

## Performance Best Practices

### Query Optimization

**HCD/Cassandra:**
- Use partition keys in WHERE clauses
- Batch operations for bulk inserts (up to 10,000 records)
- Leverage TTL for automatic data cleanup
- Avoid full table scans

```python
# Good: Using partition key
query = "SELECT * FROM impression_tracking WHERE publishers_id = ? AND timestamp >= ?"

# Bad: Full table scan
query = "SELECT * FROM impression_tracking WHERE impressions > 100"
```

**Presto:**
- Use partition columns (bucket_date) in WHERE clauses
- Leverage approximate functions for large datasets
- Use LIMIT for exploratory queries
- Consider query complexity vs. data volume

```python
# Good: Partition-aware query
query = """
SELECT publishers_id, SUM(impressions)
FROM iceberg.affiliate_junction.impression_tracking
WHERE bucket_date >= CURRENT_DATE - INTERVAL '1' DAY
GROUP BY publishers_id
"""

# Better: Use approximate functions for large datasets
query = """
SELECT publishers_id, 
       approx_count_distinct(cookie_id) as approx_unique_users,
       SUM(impressions) as total_impressions
FROM iceberg.affiliate_junction.impression_tracking
WHERE bucket_date >= CURRENT_DATE - INTERVAL '7' DAY
GROUP BY publishers_id
"""
```

### Connection Management

**Services:**
- Reuse connections across iterations
- Implement proper connection pooling
- Handle connection failures gracefully

**Web UI:**
- Use request-scoped metrics
- Clear metrics after each request
- Implement connection retry logic

### Metrics Best Practices

**Metric Collection:**
```python
# In services - collect and store metrics periodically
def update_service_metrics():
    cassandra_metrics = cassandra_connection.get_query_metrics()
    presto_metrics = presto_client.get_query_metrics()
    
    services_manager.update_query_metrics(
        cassandra_metrics=cassandra_metrics,
        presto_metrics=presto_metrics
    )
    
    # Clear after storing to prevent memory buildup
    cassandra_connection.clear_query_metrics()
    presto_client.clear_query_metrics()

# In web UI - collect metrics per request
@app.middleware("http")
async def query_metrics_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Log query metrics for this request
    cassandra_queries = cassandra_wrapper.get_request_queries()
    presto_queries = presto_wrapper.get_request_queries()
    
    if cassandra_queries or presto_queries:
        logger.info(f"Request {request.url.path}: "
                   f"{len(cassandra_queries)} HCD queries, "
                   f"{len(presto_queries)} Presto queries")
    
    return response
```

## Debugging and Monitoring

### Logging Query Execution

```python
# Enable debug logging for detailed query information
logging.getLogger('affiliate_common.database_connections').setLevel(logging.DEBUG)
logging.getLogger('web.cassandra_wrapper').setLevel(logging.DEBUG)
logging.getLogger('web.presto_wrapper').setLevel(logging.DEBUG)
```

### Monitoring Query Performance

**Identify Slow Queries:**
```python
def find_slow_queries(metrics: List[Dict], threshold_ms: float = 1000):
    slow_queries = [
        metric for metric in metrics 
        if metric.get('execution_time_ms', 0) > threshold_ms
    ]
    
    for query in slow_queries:
        print(f"Slow query {query['query_id']}: {query['execution_time_ms']}ms")
        print(f"Description: {query['query_description']}")
        print(f"Query: {query['formatted_query_text'][:200]}...")
```

**Monitor Query Patterns:**
```python
def analyze_query_patterns(metrics: List[Dict]):
    # Group by simplified query text
    patterns = {}
    for metric in metrics:
        pattern = metric.get('simplified_query_text', 'unknown')
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append(metric)
    
    # Find most frequent patterns
    frequent_patterns = sorted(
        patterns.items(), 
        key=lambda x: sum(m.get('repeat_count', 1) for m in x[1]),
        reverse=True
    )
    
    for pattern, queries in frequent_patterns[:5]:
        total_executions = sum(q.get('repeat_count', 1) for q in queries)
        avg_time = sum(q.get('execution_time_ms', 0) for q in queries) / len(queries)
        print(f"Pattern executed {total_executions} times, avg {avg_time:.2f}ms")
```

### Service Health Monitoring

**Check Connection Status:**
```python
# Test database connections
def check_database_health():
    try:
        # Test Cassandra
        cassandra_wrapper.execute_query_simple(
            "SELECT COUNT(*) FROM system.local", 
            query_description="Health check"
        )
        cassandra_healthy = True
    except Exception as e:
        cassandra_healthy = False
        logger.error(f"Cassandra health check failed: {e}")
    
    try:
        # Test Presto
        presto_wrapper.execute_query_simple(
            "SELECT 1", 
            query_description="Health check"
        )
        presto_healthy = True
    except Exception as e:
        presto_healthy = False
        logger.error(f"Presto health check failed: {e}")
    
    return {
        "cassandra": cassandra_healthy,
        "presto": presto_healthy
    }
```

This comprehensive guide provides developers with the tools and knowledge needed to effectively use the database query system, capture meaningful metrics, and optimize performance across both service and web UI components of the Affiliate Junction demo.