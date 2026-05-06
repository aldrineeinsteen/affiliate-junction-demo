# Federated Queries for Affiliate Junction Demo

Complete collection of federated queries demonstrating watsonx.data's ability to query across HCD (Cassandra) and Iceberg data sources.

## Table of Contents

1. [Basic Federated Queries](#basic-federated-queries)
2. [Real-Time vs Historical Comparison](#real-time-vs-historical-comparison)
3. [Cross-Catalog Joins](#cross-catalog-joins)
4. [Time-Series Analysis](#time-series-analysis)
5. [Performance Metrics](#performance-metrics)
6. [Data Validation Queries](#data-validation-queries)
7. [Advanced Analytics](#advanced-analytics)

---

## Basic Federated Queries

### Query 1: Count Comparison (Real-Time vs Historical)

```sql
-- Compare impression counts between operational (HCD) and analytical (Iceberg) stores
SELECT 
    'HCD (Last 5 min)' as source,
    COUNT(*) as impression_count,
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record
FROM hcd.affiliate_junction.impression_tracking
UNION ALL
SELECT 
    'Iceberg (Historical)' as source,
    COUNT(*) as impression_count,
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record
FROM iceberg_data.affiliate_junction.impression_tracking;
```

**Purpose:** Shows data distribution across operational and analytical stores  
**Expected Result:** HCD shows recent data (5 min), Iceberg shows all historical data

---

### Query 2: Publisher Activity Across Both Sources

```sql
-- Show publisher activity in both real-time and historical data
SELECT 
    'HCD (Real-Time)' as source,
    publishers_id,
    COUNT(*) as impression_count
FROM hcd.affiliate_junction.impression_tracking
GROUP BY publishers_id
UNION ALL
SELECT 
    'Iceberg (Historical)' as source,
    publishers_id,
    COUNT(*) as impression_count
FROM iceberg_data.affiliate_junction.impression_tracking
GROUP BY publishers_id
ORDER BY publishers_id, source;
```

**Purpose:** Compare publisher activity across both data stores  
**Use Case:** Verify ETL pipeline is moving data correctly

---

### Query 3: Conversion Tracking Comparison

```sql
-- Compare conversion counts between HCD and Iceberg
SELECT 
    'HCD (Recent)' as source,
    COUNT(*) as conversion_count,
    COUNT(DISTINCT cookie_id) as unique_cookies,
    COUNT(DISTINCT advertisers_id) as unique_advertisers
FROM hcd.affiliate_junction.conversion_tracking
UNION ALL
SELECT 
    'Iceberg (Historical)' as source,
    COUNT(*) as conversion_count,
    COUNT(DISTINCT cookie_id) as unique_cookies,
    COUNT(DISTINCT advertisers_id) as unique_advertisers
FROM iceberg_data.affiliate_junction.conversion_tracking;
```

**Purpose:** Validate conversion data across both systems  
**Metrics:** Total conversions, unique users, unique advertisers

---

## Real-Time vs Historical Comparison

### Query 4: Publisher Performance Growth

```sql
-- Compare current publisher performance vs historical average
WITH hcd_current AS (
    SELECT 
        publishers_id,
        COUNT(*) as current_impressions,
        COUNT(DISTINCT cookie_id) as current_unique_users
    FROM hcd.affiliate_junction.impression_tracking
    GROUP BY publishers_id
),
iceberg_historical AS (
    SELECT 
        publishers_id,
        COUNT(*) as total_impressions,
        COUNT(DISTINCT cookie_id) as total_unique_users,
        COUNT(DISTINCT DATE(timestamp)) as days_active
    FROM iceberg_data.affiliate_junction.impression_tracking
    GROUP BY publishers_id
)
SELECT 
    h.publishers_id,
    h.current_impressions,
    i.total_impressions as historical_total,
    ROUND(CAST(h.current_impressions AS DOUBLE) / NULLIF(i.total_impressions, 0) * 100, 2) as current_percentage,
    i.days_active,
    ROUND(CAST(i.total_impressions AS DOUBLE) / NULLIF(i.days_active, 0), 0) as avg_impressions_per_day
FROM hcd_current h
JOIN iceberg_historical i ON h.publishers_id = i.publishers_id
ORDER BY h.current_impressions DESC
LIMIT 10;
```

**Purpose:** Show publisher growth trends  
**Metrics:** Current activity, historical totals, daily averages

---

### Query 5: Advertiser ROI Analysis

```sql
-- Analyze advertiser ROI using both real-time and historical data
WITH hcd_recent AS (
    SELECT 
        advertisers_id,
        COUNT(*) as recent_impressions
    FROM hcd.affiliate_junction.impression_tracking
    GROUP BY advertisers_id
),
hcd_conversions AS (
    SELECT 
        advertisers_id,
        COUNT(*) as recent_conversions
    FROM hcd.affiliate_junction.conversion_tracking
    GROUP BY advertisers_id
),
iceberg_historical AS (
    SELECT 
        i.advertisers_id,
        COUNT(DISTINCT i.cookie_id) as total_impressions,
        COUNT(DISTINCT c.cookie_id) as total_conversions
    FROM iceberg_data.affiliate_junction.impression_tracking i
    LEFT JOIN iceberg_data.affiliate_junction.conversion_tracking c
        ON i.advertisers_id = c.advertisers_id
        AND i.cookie_id = c.cookie_id
    GROUP BY i.advertisers_id
)
SELECT 
    hr.advertisers_id,
    hr.recent_impressions,
    hc.recent_conversions,
    ROUND(CAST(hc.recent_conversions AS DOUBLE) / NULLIF(hr.recent_impressions, 0) * 100, 2) as recent_conversion_rate,
    ih.total_impressions as historical_impressions,
    ih.total_conversions as historical_conversions,
    ROUND(CAST(ih.total_conversions AS DOUBLE) / NULLIF(ih.total_impressions, 0) * 100, 2) as historical_conversion_rate
FROM hcd_recent hr
LEFT JOIN hcd_conversions hc ON hr.advertisers_id = hc.advertisers_id
LEFT JOIN iceberg_historical ih ON hr.advertisers_id = ih.advertisers_id
ORDER BY recent_conversion_rate DESC NULLS LAST
LIMIT 10;
```

**Purpose:** Compare recent vs historical conversion rates  
**Use Case:** Identify trending advertisers

---

## Cross-Catalog Joins

### Query 6: Attribution Analysis (Federated Join)

```sql
-- Join real-time impressions with historical conversions for attribution
SELECT 
    h.publishers_id,
    h.advertisers_id,
    h.cookie_id,
    h.timestamp as impression_time,
    c.timestamp as conversion_time,
    CAST((c.timestamp - h.timestamp) AS BIGINT) / 1000 as time_to_conversion_seconds
FROM hcd.affiliate_junction.impression_tracking h
JOIN iceberg_data.affiliate_junction.conversion_tracking c
    ON h.cookie_id = c.cookie_id
    AND h.advertisers_id = c.advertisers_id
    AND c.timestamp > h.timestamp
    AND c.timestamp <= h.timestamp + INTERVAL '90' MINUTE
WHERE h.timestamp > CURRENT_TIMESTAMP - INTERVAL '5' MINUTE
ORDER BY time_to_conversion_seconds
LIMIT 20;
```

**Purpose:** Real-time attribution using federated join  
**Performance:** Demonstrates cross-catalog join capability

---

### Query 7: Publisher-Advertiser Network Analysis

```sql
-- Analyze publisher-advertiser relationships across both systems
WITH hcd_relationships AS (
    SELECT 
        publishers_id,
        advertisers_id,
        COUNT(*) as recent_impressions,
        COUNT(DISTINCT cookie_id) as recent_unique_users
    FROM hcd.affiliate_junction.impression_tracking
    GROUP BY publishers_id, advertisers_id
),
iceberg_relationships AS (
    SELECT 
        publishers_id,
        advertisers_id,
        COUNT(*) as total_impressions,
        COUNT(DISTINCT cookie_id) as total_unique_users
    FROM iceberg_data.affiliate_junction.impression_tracking
    GROUP BY publishers_id, advertisers_id
)
SELECT 
    COALESCE(h.publishers_id, i.publishers_id) as publishers_id,
    COALESCE(h.advertisers_id, i.advertisers_id) as advertisers_id,
    COALESCE(h.recent_impressions, 0) as recent_impressions,
    COALESCE(i.total_impressions, 0) as historical_impressions,
    COALESCE(h.recent_unique_users, 0) as recent_unique_users,
    COALESCE(i.total_unique_users, 0) as historical_unique_users,
    ROUND(CAST(COALESCE(h.recent_impressions, 0) AS DOUBLE) / 
          NULLIF(COALESCE(i.total_impressions, 0), 0) * 100, 2) as recent_percentage
FROM hcd_relationships h
FULL OUTER JOIN iceberg_relationships i
    ON h.publishers_id = i.publishers_id
    AND h.advertisers_id = i.advertisers_id
ORDER BY recent_impressions DESC NULLS LAST
LIMIT 20;
```

**Purpose:** Full network analysis with outer join  
**Insight:** Shows relationships that exist in one system but not the other

---

## Time-Series Analysis

### Query 8: Hourly Trend Analysis

```sql
-- Compare hourly trends between HCD and Iceberg
WITH hcd_hourly AS (
    SELECT 
        DATE_TRUNC('hour', timestamp) as hour,
        COUNT(*) as impression_count
    FROM hcd.affiliate_junction.impression_tracking
    GROUP BY DATE_TRUNC('hour', timestamp)
),
iceberg_hourly AS (
    SELECT 
        DATE_TRUNC('hour', timestamp) as hour,
        COUNT(*) as impression_count
    FROM iceberg_data.affiliate_junction.impression_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24' HOUR
    GROUP BY DATE_TRUNC('hour', timestamp)
)
SELECT 
    COALESCE(h.hour, i.hour) as hour,
    COALESCE(h.impression_count, 0) as hcd_count,
    COALESCE(i.impression_count, 0) as iceberg_count,
    ABS(COALESCE(h.impression_count, 0) - COALESCE(i.impression_count, 0)) as difference
FROM hcd_hourly h
FULL OUTER JOIN iceberg_hourly i ON h.hour = i.hour
ORDER BY hour DESC;
```

**Purpose:** Validate ETL pipeline timing  
**Use Case:** Identify data lag between systems

---

### Query 9: Minute-by-Minute Activity

```sql
-- Real-time minute-by-minute activity comparison
SELECT 
    'HCD (Real-Time)' as source,
    DATE_TRUNC('minute', timestamp) as minute,
    COUNT(*) as impression_count,
    COUNT(DISTINCT publishers_id) as active_publishers,
    COUNT(DISTINCT advertisers_id) as active_advertisers
FROM hcd.affiliate_junction.impression_tracking
WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '10' MINUTE
GROUP BY DATE_TRUNC('minute', timestamp)
UNION ALL
SELECT 
    'Iceberg (Recent)' as source,
    DATE_TRUNC('minute', timestamp) as minute,
    COUNT(*) as impression_count,
    COUNT(DISTINCT publishers_id) as active_publishers,
    COUNT(DISTINCT advertisers_id) as active_advertisers
FROM iceberg_data.affiliate_junction.impression_tracking
WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '10' MINUTE
GROUP BY DATE_TRUNC('minute', timestamp)
ORDER BY minute DESC, source;
```

**Purpose:** Fine-grained activity monitoring  
**Frequency:** Can be run every minute for real-time dashboards

---

## Performance Metrics

### Query 10: Query Performance Comparison

```sql
-- Compare query performance across catalogs
WITH hcd_stats AS (
    SELECT 
        'HCD' as catalog,
        COUNT(*) as total_records,
        COUNT(DISTINCT publishers_id) as unique_publishers,
        COUNT(DISTINCT advertisers_id) as unique_advertisers,
        COUNT(DISTINCT cookie_id) as unique_cookies,
        MIN(timestamp) as oldest_record,
        MAX(timestamp) as newest_record
    FROM hcd.affiliate_junction.impression_tracking
),
iceberg_stats AS (
    SELECT 
        'Iceberg' as catalog,
        COUNT(*) as total_records,
        COUNT(DISTINCT publishers_id) as unique_publishers,
        COUNT(DISTINCT advertisers_id) as unique_advertisers,
        COUNT(DISTINCT cookie_id) as unique_cookies,
        MIN(timestamp) as oldest_record,
        MAX(timestamp) as newest_record
    FROM iceberg_data.affiliate_junction.impression_tracking
)
SELECT * FROM hcd_stats
UNION ALL
SELECT * FROM iceberg_stats;
```

**Purpose:** System health check  
**Metrics:** Record counts, cardinality, time ranges

---

### Query 11: Data Freshness Check

```sql
-- Check data freshness across both systems
SELECT 
    'HCD' as source,
    MAX(timestamp) as latest_record,
    CAST((CURRENT_TIMESTAMP - MAX(timestamp)) AS BIGINT) / 1000 as seconds_old,
    COUNT(*) as record_count
FROM hcd.affiliate_junction.impression_tracking
UNION ALL
SELECT 
    'Iceberg' as source,
    MAX(timestamp) as latest_record,
    CAST((CURRENT_TIMESTAMP - MAX(timestamp)) AS BIGINT) / 1000 as seconds_old,
    COUNT(*) as record_count
FROM iceberg_data.affiliate_junction.impression_tracking;
```

**Purpose:** Monitor ETL lag  
**Alert:** If Iceberg is >5 minutes behind, ETL may be delayed

---

## Data Validation Queries

### Query 12: Data Consistency Check

```sql
-- Verify data consistency between HCD and Iceberg
WITH hcd_summary AS (
    SELECT 
        publishers_id,
        advertisers_id,
        DATE(timestamp) as date,
        COUNT(*) as impression_count,
        COUNT(DISTINCT cookie_id) as unique_cookies
    FROM hcd.affiliate_junction.impression_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '1' HOUR
    GROUP BY publishers_id, advertisers_id, DATE(timestamp)
),
iceberg_summary AS (
    SELECT 
        publishers_id,
        advertisers_id,
        DATE(timestamp) as date,
        COUNT(*) as impression_count,
        COUNT(DISTINCT cookie_id) as unique_cookies
    FROM iceberg_data.affiliate_junction.impression_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '1' HOUR
    GROUP BY publishers_id, advertisers_id, DATE(timestamp)
)
SELECT 
    COALESCE(h.publishers_id, i.publishers_id) as publishers_id,
    COALESCE(h.advertisers_id, i.advertisers_id) as advertisers_id,
    COALESCE(h.date, i.date) as date,
    h.impression_count as hcd_count,
    i.impression_count as iceberg_count,
    ABS(COALESCE(h.impression_count, 0) - COALESCE(i.impression_count, 0)) as difference,
    CASE 
        WHEN ABS(COALESCE(h.impression_count, 0) - COALESCE(i.impression_count, 0)) > 10 
        THEN 'MISMATCH'
        ELSE 'OK'
    END as status
FROM hcd_summary h
FULL OUTER JOIN iceberg_summary i
    ON h.publishers_id = i.publishers_id
    AND h.advertisers_id = i.advertisers_id
    AND h.date = i.date
WHERE ABS(COALESCE(h.impression_count, 0) - COALESCE(i.impression_count, 0)) > 0
ORDER BY difference DESC;
```

**Purpose:** Identify data discrepancies  
**Use Case:** ETL validation and troubleshooting

---

### Query 13: Missing Data Detection

```sql
-- Find records in HCD but not yet in Iceberg
SELECT 
    h.publishers_id,
    h.advertisers_id,
    h.cookie_id,
    h.timestamp,
    'Missing in Iceberg' as status
FROM hcd.affiliate_junction.impression_tracking h
LEFT JOIN iceberg_data.affiliate_junction.impression_tracking i
    ON h.publishers_id = i.publishers_id
    AND h.advertisers_id = i.advertisers_id
    AND h.cookie_id = i.cookie_id
    AND h.timestamp = i.timestamp
WHERE i.publishers_id IS NULL
    AND h.timestamp < CURRENT_TIMESTAMP - INTERVAL '2' MINUTE
LIMIT 100;
```

**Purpose:** Detect ETL gaps  
**Alert:** Records older than 2 minutes should be in Iceberg

---

## Advanced Analytics

### Query 14: Conversion Funnel Analysis

```sql
-- Analyze conversion funnel across both systems
WITH impressions AS (
    SELECT 
        publishers_id,
        advertisers_id,
        cookie_id,
        timestamp as impression_time
    FROM iceberg_data.affiliate_junction.impression_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24' HOUR
),
conversions AS (
    SELECT 
        advertisers_id,
        cookie_id,
        timestamp as conversion_time
    FROM iceberg_data.affiliate_junction.conversion_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24' HOUR
),
recent_impressions AS (
    SELECT 
        publishers_id,
        advertisers_id,
        cookie_id,
        timestamp as impression_time
    FROM hcd.affiliate_junction.impression_tracking
)
SELECT 
    'Historical (24h)' as period,
    COUNT(DISTINCT i.cookie_id) as total_users,
    COUNT(DISTINCT c.cookie_id) as converted_users,
    ROUND(CAST(COUNT(DISTINCT c.cookie_id) AS DOUBLE) / 
          NULLIF(COUNT(DISTINCT i.cookie_id), 0) * 100, 2) as conversion_rate
FROM impressions i
LEFT JOIN conversions c 
    ON i.cookie_id = c.cookie_id
    AND i.advertisers_id = c.advertisers_id
    AND c.conversion_time > i.impression_time
    AND c.conversion_time <= i.impression_time + INTERVAL '90' MINUTE
UNION ALL
SELECT 
    'Real-Time (5min)' as period,
    COUNT(DISTINCT ri.cookie_id) as total_users,
    COUNT(DISTINCT c.cookie_id) as converted_users,
    ROUND(CAST(COUNT(DISTINCT c.cookie_id) AS DOUBLE) / 
          NULLIF(COUNT(DISTINCT ri.cookie_id), 0) * 100, 2) as conversion_rate
FROM recent_impressions ri
LEFT JOIN conversions c 
    ON ri.cookie_id = c.cookie_id
    AND ri.advertisers_id = c.advertisers_id
    AND c.conversion_time > ri.impression_time
    AND c.conversion_time <= ri.impression_time + INTERVAL '90' MINUTE;
```

**Purpose:** Compare conversion rates across time periods  
**Insight:** Real-time vs historical conversion performance

---

### Query 15: Top Performing Combinations

```sql
-- Find top performing publisher-advertiser combinations
WITH combined_data AS (
    SELECT 
        publishers_id,
        advertisers_id,
        COUNT(*) as impression_count,
        'Historical' as source
    FROM iceberg_data.affiliate_junction.impression_tracking
    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '7' DAY
    GROUP BY publishers_id, advertisers_id
    
    UNION ALL
    
    SELECT 
        publishers_id,
        advertisers_id,
        COUNT(*) as impression_count,
        'Real-Time' as source
    FROM hcd.affiliate_junction.impression_tracking
    GROUP BY publishers_id, advertisers_id
)
SELECT 
    publishers_id,
    advertisers_id,
    SUM(CASE WHEN source = 'Historical' THEN impression_count ELSE 0 END) as historical_impressions,
    SUM(CASE WHEN source = 'Real-Time' THEN impression_count ELSE 0 END) as realtime_impressions,
    SUM(impression_count) as total_impressions
FROM combined_data
GROUP BY publishers_id, advertisers_id
ORDER BY total_impressions DESC
LIMIT 20;
```

**Purpose:** Identify best partnerships  
**Use Case:** Business intelligence and optimization

---

## Query Execution Tips

### Performance Best Practices

1. **Use Time Filters**: Always filter by timestamp to reduce data scanned
   ```sql
   WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '1' HOUR
   ```

2. **Leverage Partitioning**: Iceberg tables are partitioned by hour and publisher bucket
   ```sql
   WHERE hour(timestamp) = hour(CURRENT_TIMESTAMP)
   ```

3. **Limit Result Sets**: Use LIMIT for exploratory queries
   ```sql
   LIMIT 100
   ```

4. **Use CTEs**: Break complex queries into readable CTEs
   ```sql
   WITH hcd_data AS (...), iceberg_data AS (...)
   ```

5. **Monitor Query Plans**: Use EXPLAIN to understand query execution
   ```sql
   EXPLAIN SELECT ...
   ```

### Common Patterns

**Pattern 1: UNION ALL for Side-by-Side Comparison**
```sql
SELECT 'HCD' as source, ... FROM hcd.table
UNION ALL
SELECT 'Iceberg' as source, ... FROM iceberg.table
```

**Pattern 2: FULL OUTER JOIN for Complete Picture**
```sql
FROM hcd_table h
FULL OUTER JOIN iceberg_table i ON h.key = i.key
```

**Pattern 3: Time-Based Joins for Attribution**
```sql
JOIN ... ON ... 
    AND target.time > source.time
    AND target.time <= source.time + INTERVAL '90' MINUTE
```

---

## Troubleshooting

### Query Fails with "Catalog not found"

**Solution:** Verify catalog names
```sql
SHOW CATALOGS;
SHOW SCHEMAS FROM hcd;
SHOW SCHEMAS FROM iceberg_data;
```

### Query Times Out

**Solution:** Add time filters and reduce data scanned
```sql
WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '1' HOUR
LIMIT 1000
```

### Results Don't Match

**Solution:** Check data freshness and ETL lag
```sql
SELECT MAX(timestamp) FROM hcd.affiliate_junction.impression_tracking;
SELECT MAX(timestamp) FROM iceberg_data.affiliate_junction.impression_tracking;
```

---

## Next Steps

1. Try modifying these queries for your specific use cases
2. Create views for frequently used federated queries
3. Build dashboards using these queries
4. Experiment with different time windows and filters
5. Monitor query performance and optimize as needed

For more information, see:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SERVICES.md](SERVICES.md) - Service documentation
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) - Demo walkthrough