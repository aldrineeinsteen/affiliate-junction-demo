# Lab 2: Operational Data in HCD

**Duration:** 30-40 minutes  
**Difficulty:** Intermediate  
**Environment:** watsonx.data Query Workspace + cqlsh

---

## Lab Overview

In this lab, you'll dive deep into HCD (Cassandra) operational data patterns. You'll learn:

1. How to write efficient queries using partition keys
2. Understanding bucketing strategies for high-volume data
3. Querying time-series data effectively
4. Monitoring write throughput and performance
5. Working with pre-computed statistics

**Building on Lab 1:**
You created `user_activity_tracking` table. Now you'll query it efficiently and explore the existing demo tables.

---

## Prerequisites

✅ Completed Lab 1 (created user_activity_tracking table)  
✅ Access to watsonx.data Query Workspace  
✅ SSH access to VM for cqlsh  
✅ Understanding of partition keys and clustering keys

---

## Part 1: Understanding Operational Data Characteristics (5 minutes)

### What Makes Data "Operational"?

**Operational Data Characteristics:**
- ✅ **High-velocity writes** (5000+ events/min in this demo)
- ✅ **Short retention** (5-10 minutes TTL)
- ✅ **Real-time access required** (sub-10ms latency)
- ✅ **Low-latency reads** (<10ms typical)
- ✅ **Optimized for current state** (not historical analysis)
- ✅ **Examples**: Active impressions, live clicks, current sessions

**Why HCD for Operational Data?**
- ✅ **Distributed architecture** - Linear scalability
- ✅ **Tunable consistency** - Balance speed vs accuracy
- ✅ **Automatic data expiration** (TTL) - No cleanup needed
- ✅ **Partition-based storage** - Prevents hot spots
- ✅ **Handles 5000+ writes/sec easily** - Web-scale performance

### HCD Tables in This Lab

```
📊 impression_tracking
   - Partition: (publishers_id, cookie_id, advertisers_id)
   - TTL: 5 minutes
   - Purpose: Track ad impressions in real-time

📊 impressions_by_minute
   - Partition: (bucket_date, bucket)
   - TTL: 10 minutes
   - Purpose: Time-bucketed impressions for aggregation

📊 publishers / advertisers
   - Partition: publisher_id / advertiser_id
   - TTL: 6 hours
   - Purpose: Pre-computed summary statistics

📊 user_activity_tracking (YOUR TABLE)
   - Partition: (user_id, session_id)
   - TTL: 10 minutes
   - Purpose: Track user sessions
```

---

## Part 2: Efficient Partition-Based Queries (10 minutes)

### Step 1: Query Your Data Efficiently

**❌ INEFFICIENT - Full Table Scan:**

```sql
-- DON'T DO THIS - Scans entire table across all nodes
SELECT * FROM hcd.affiliate_junction.user_activity_tracking
LIMIT 100;
```

**Why is this bad?**
- Queries ALL partitions across ALL nodes
- Slow for large datasets
- Doesn't use partition key
- Not scalable

**✅ EFFICIENT - Partition-Targeted Query:**

```sql
-- DO THIS - Targets specific partition
SELECT * 
FROM hcd.affiliate_junction.user_activity_tracking
WHERE user_id = 'user_001' 
  AND session_id = 'session_1001'
ORDER BY timestamp DESC;
```

**Why is this good?**
- Targets single partition on single node
- Fast (<10ms typical)
- Uses partition key efficiently
- Scalable to billions of records

### Step 2: Query Patterns for Your Table

**Pattern 1: Get all activity for a user session**

```sql
SELECT 
    action_type,
    page_url,
    timestamp,
    metadata
FROM hcd.affiliate_junction.user_activity_tracking
WHERE user_id = 'user_001'
  AND session_id = 'session_1001'
ORDER BY timestamp DESC;
```

**Explanation:**
- `WHERE user_id AND session_id` - Uses complete partition key
- `ORDER BY timestamp DESC` - Uses clustering key (already sorted)
- Fast because data is co-located on one node

**Pattern 2: Get recent activity for a user (across sessions)**

```sql
-- Note: This requires querying multiple partitions
-- Less efficient but sometimes necessary
SELECT
    session_id,
    action_type,
    page_url,
    timestamp
FROM hcd.affiliate_junction.user_activity_tracking
WHERE user_id = 'user_001';
```

**Explanation:**
- Queries without complete partition key (missing session_id)
- Presto will scan multiple partitions for this user_id
- Slower but acceptable for small datasets
- In cqlsh, this would require `ALLOW FILTERING`

**Pattern 3: Count activities in a session**

```sql
SELECT 
    COUNT(*) as activity_count
FROM hcd.affiliate_junction.user_activity_tracking
WHERE user_id = 'user_001'
  AND session_id = 'session_1001';
```

**Pattern 4: Get specific action types**

```sql
SELECT
    page_url,
    timestamp,
    metadata
FROM hcd.affiliate_junction.user_activity_tracking
WHERE user_id = 'user_001'
  AND session_id = 'session_1001'
  AND action_type = 'purchase';
```

**Explanation:**
- `action_type` is not part of primary key
- Presto filters after retrieving partition data
- In cqlsh, this would require `ALLOW FILTERING`

---

## Part 3: Exploring Bucketing Strategies (10 minutes)

### Step 3: Understanding Time-Based Bucketing

The demo uses `impressions_by_minute` table with a bucketing strategy to handle high-volume writes.

**View the schema:**

```sql
DESCRIBE hcd.affiliate_junction.impressions_by_minute;
```

**Key Design Elements:**

```sql
PRIMARY KEY ((bucket_date, bucket), ts, publishers_id, advertisers_id, cookie_id, impression_id)
```

**Understanding the Partition Key:**
- `bucket_date` - Date truncated to minute (e.g., '2026-05-06 10:30:00')
- `bucket` - SMALLINT 0-59 (distributes within minute)

**Why Bucketing?**

**Without Bucketing:**
```
Minute 10:30 → Single Partition → 5000 writes → HOT SPOT! ❌
```

**With Bucketing (0-59):**
```
Minute 10:30, Bucket 0  → ~83 writes
Minute 10:30, Bucket 1  → ~83 writes
...
Minute 10:30, Bucket 59 → ~83 writes
Total: 60 partitions × 83 writes = 5000 writes ✅
```

**Benefits:**
- Distributes load across 60 partitions
- Prevents hot spots
- Enables linear scaling
- Each partition handles manageable load

### Step 4: Query Bucketed Data

**Query specific bucket:**

```sql
SELECT 
    bucket_date,
    bucket,
    ts,
    publishers_id,
    advertisers_id,
    cookie_id
FROM hcd.affiliate_junction.impressions_by_minute
WHERE bucket_date >= CURRENT_TIMESTAMP - INTERVAL '1' HOUR
LIMIT 100;
```

**Explanation:**
- Targets single partition (bucket_date + bucket)
- Fast and efficient
- Returns ~83 records for this minute/bucket

**Query all buckets for a minute:**

```sql
-- This queries 60 partitions (one per bucket)
SELECT 
    bucket,
    COUNT(*) as impression_count
FROM hcd.affiliate_junction.impressions_by_minute
WHERE bucket_date >= CURRENT_TIMESTAMP - INTERVAL '1'
GROUP BY bucket;
```

**Expected Output:**
```
bucket | impression_count
-------+-----------------
     0 |               83
     1 |               85
     2 |               82
   ... |              ...
    59 |               84
```

**What this shows:**
- Relatively even distribution across buckets
- Each bucket handles similar load
- No hot spots

### Step 5: Create Your Own Bucketed Table

Let's create a bucketed version of your activity tracking via cqlsh:

**Connect to cqlsh:**

```bash
/opt/hcd-1.2.5/bin/cqlsh 10.243.0.34 9042
USE affiliate_junction;
```

**Create the bucketed table:**

```cql
CREATE TABLE IF NOT EXISTS user_activity_by_minute (
    minute_bucket TIMESTAMP,
    bucket SMALLINT,
    ts TIMESTAMP,
    user_id TEXT,
    session_id TEXT,
    action_type TEXT,
    page_url TEXT,
    metadata TEXT,
    PRIMARY KEY ((minute_bucket, bucket), ts, user_id, session_id)
) WITH CLUSTERING ORDER BY (ts DESC, user_id ASC, session_id ASC)
AND default_time_to_live = 600
AND gc_grace_seconds = 0;
```

**Understanding the Design:**

**Partition Key: `(minute_bucket, bucket)`**
- `minute_bucket` - Timestamp truncated to minute
- `bucket` - SMALLINT 0-59 for distribution

**Clustering Key: `ts, user_id, session_id`**
- Orders by timestamp within partition
- Allows efficient time-range queries

**When to Use Bucketing:**
- ✅ High write volume (>1000/sec per partition)
- ✅ Time-series data
- ✅ Need to prevent hot spots
- ❌ Low write volume (adds complexity)
- ❌ Need to query by specific user (harder with bucketing)

---

## Part 4: Working with Pre-Computed Statistics (10 minutes)

### Step 6: Explore Publisher Statistics

The demo pre-computes publisher statistics for fast dashboard serving.

**Query publisher statistics:**

```sql
SELECT 
    publisher_id,
    impressions,
    conversions,
    last_updated
FROM hcd.affiliate_junction.publishers
LIMIT 5;
```

**Understanding the Data:**

**`impressions` and `conversions` columns:**
- Stored as TEXT containing JSON arrays
- Format: `[{"ts": 1234567890, "count": 10}, ...]`
- Contains last 90 minutes of data points
- Updated by ETL service every minute

**Why Pre-Compute?**
- ✅ Dashboard needs fast response (<100ms)
- ✅ Aggregating raw data is slow
- ✅ Same calculation repeated many times
- ✅ Trade storage for speed

**Parse the JSON data:**

```sql
SELECT 
    publisher_id,
    impressions,
    last_updated,
    CAST((CURRENT_TIMESTAMP - last_updated) AS BIGINT) / 1000 as seconds_old
FROM hcd.affiliate_junction.publishers
WHERE publisher_id = 'pub_001';
```

**What you're seeing:**
- Pre-aggregated timeseries data
- Updated every minute by `presto_to_hcd` service
- Fast to query (single partition lookup)
- Perfect for dashboard serving

### Step 7: Create Your Own Statistics Table

Let's create a statistics table for your user activity via cqlsh:

**In cqlsh:**

```cql
CREATE TABLE IF NOT EXISTS user_activity_stats (
    user_id TEXT PRIMARY KEY,
    total_sessions BIGINT,
    total_activities BIGINT,
    last_activity TIMESTAMP,
    activity_breakdown TEXT,
    last_updated TIMESTAMP
) WITH default_time_to_live = 3600
AND gc_grace_seconds = 0;
```

**Insert sample statistics:**

```cql
INSERT INTO user_activity_stats
(user_id, total_sessions, total_activities, last_activity, activity_breakdown, last_updated)
VALUES (
    'user_001',
    5,
    47,
    toTimestamp(now()),
    '{"page_view": 20, "click": 15, "scroll": 8, "add_to_cart": 3, "purchase": 1}',
    toTimestamp(now())
);
```

**Query the statistics in cqlsh:**

```cql
SELECT
    user_id,
    total_sessions,
    total_activities,
    activity_breakdown,
    last_activity
FROM user_activity_stats
WHERE user_id = 'user_001';
```

**Or query via watsonx.data Query Workspace:**

```sql
SELECT
    user_id,
    total_sessions,
    total_activities,
    ROUND(CAST(total_activities AS DOUBLE) / NULLIF(total_sessions, 0), 2) as avg_activities_per_session,
    activity_breakdown,
    last_activity
FROM hcd.affiliate_junction.user_activity_stats
WHERE user_id = 'user_001';
```

**Understanding the Pattern:**

```
Raw Data (user_activity_tracking)
         ↓
    ETL Process
         ↓
Statistics (user_activity_stats)
         ↓
   Fast Dashboard
```

---

## Part 5: Advanced Querying with cqlsh (5 minutes)

### Step 8: Connect via cqlsh

For some operations, native CQL shell is more powerful:

```bash
# SSH to VM
ssh -p <port> watsonx@<hostname>

# Connect to HCD
cqlsh localhost 9042

# Switch to keyspace
USE affiliate_junction;
```

### Step 9: Advanced CQL Queries

**Query with TIMEUUID:**

```sql
-- impressions_by_minute uses TIMEUUID for ts
SELECT 
    dateOf(ts) as timestamp,
    publishers_id,
    advertisers_id
FROM impressions_by_minute
WHERE bucket_date = '2026-05-06 10:30:00'
  AND bucket = 0
LIMIT 10;
```

**Explanation:**
- `TIMEUUID` - Time-based UUID for ordering
- `dateOf()` - Converts TIMEUUID to timestamp
- Provides microsecond precision

**Query with token ranges:**

```sql
-- See which node stores data for a partition
SELECT 
    token(publishers_id, cookie_id, advertisers_id) as partition_token,
    publishers_id,
    cookie_id,
    advertisers_id
FROM impression_tracking
LIMIT 10;
```

**Explanation:**
- `token()` - Shows partition token (hash value)
- Determines which node stores the data
- Useful for understanding data distribution

**Batch operations:**

```sql
BEGIN BATCH
    INSERT INTO user_activity_tracking 
    (user_id, session_id, page_url, action_type, timestamp, metadata)
    VALUES ('user_batch', 'session_001', '/page1', 'view', toTimestamp(now()), '{}');
    
    INSERT INTO user_activity_tracking 
    (user_id, session_id, page_url, action_type, timestamp, metadata)
    VALUES ('user_batch', 'session_001', '/page2', 'view', toTimestamp(now()), '{}');
    
    INSERT INTO user_activity_tracking 
    (user_id, session_id, page_url, action_type, timestamp, metadata)
    VALUES ('user_batch', 'session_001', '/page3', 'view', toTimestamp(now()), '{}');
APPLY BATCH;
```

**Explanation:**
- `BEGIN BATCH ... APPLY BATCH` - Atomic batch operation
- All inserts succeed or all fail
- Use for related data in same partition
- Don't use across partitions (performance penalty)

---

## Part 6: Monitoring and Performance (5 minutes)

### Step 10: Monitor Write Throughput

**Check service statistics:**

```sql
SELECT 
    name,
    stats,
    last_updated
FROM hcd.affiliate_junction.services
WHERE name = 'generate_traffic';
```

**Understanding the stats:**
- JSON field containing service metrics
- Includes write rates, error rates, latency
- Updated every minute

**Query execution metrics:**

```sql
SELECT 
    name,
    query_metrics
FROM hcd.affiliate_junction.services
WHERE name = 'generate_traffic';
```

**What you're seeing:**
- All queries executed by the service
- Execution times
- Success/failure rates
- Query patterns

### Step 11: Performance Best Practices

**✅ DO:**
1. **Always use partition key in WHERE clause**
   ```sql
   WHERE user_id = 'user_001' AND session_id = 'session_1001'
   ```

2. **Use prepared statements for repeated queries**
   ```python
   prepared = session.prepare("INSERT INTO ...")
   session.execute(prepared, values)
   ```

3. **Batch related writes to same partition**
   ```sql
   BEGIN BATCH
       INSERT INTO table VALUES (...);  -- Same partition
       INSERT INTO table VALUES (...);  -- Same partition
   APPLY BATCH;
   ```

4. **Use TTL for automatic cleanup**
   ```sql
   WITH default_time_to_live = 600
   ```

5. **Design partition keys for even distribution**
   ```sql
   PRIMARY KEY ((user_id, session_id), timestamp)
   ```

**❌ DON'T:**
1. **Avoid full table scans**
   ```sql
   SELECT * FROM table LIMIT 1000;  -- Scans all nodes
   ```

2. **Don't batch across partitions**
   ```sql
   BEGIN BATCH
       INSERT INTO table VALUES (...);  -- Partition 1
       INSERT INTO table VALUES (...);  -- Partition 2 ❌
   APPLY BATCH;
   ```

3. **Avoid queries that require full table scans**
   ```cql
   -- In cqlsh, this requires ALLOW FILTERING (inefficient)
   SELECT * FROM table WHERE non_key_column = 'value' ALLOW FILTERING;
   ```
   - Design tables so queries use partition keys
   - Avoid filtering on non-key columns

4. **Avoid large partitions (>100MB)**
   - Use bucketing for high-volume data
   - Monitor partition sizes

5. **Don't query without partition key**
   ```sql
   SELECT * FROM table WHERE clustering_key = 'value';  -- Missing partition key
   ```

---

## Lab Summary

### What You've Accomplished

✅ **Wrote efficient partition-targeted queries**  
✅ **Understood bucketing strategies for high-volume data**  
✅ **Explored pre-computed statistics patterns**  
✅ **Used advanced CQL features (TIMEUUID, tokens, batches)**  
✅ **Learned performance best practices**  

### Key Concepts Learned

**1. Partition-Targeted Queries**
- Always include partition key in WHERE clause
- Targets single node for fast response
- Scalable to billions of records

**2. Bucketing Strategy**
- Distributes high-volume writes across partitions
- Prevents hot spots
- Enables linear scaling
- Use for >1000 writes/sec per partition

**3. Pre-Computed Statistics**
- Trade storage for query speed
- Perfect for dashboard serving
- Updated by ETL processes
- Fast single-partition lookups

**4. TTL-Based Lifecycle**
- Automatic data expiration
- No manual cleanup needed
- Perfect for operational data
- Configurable per table

**5. Performance Patterns**
- Use prepared statements
- Batch within partitions
- Monitor partition sizes
- Design for even distribution

---

## Next Steps

Continue to **[Lab 3: Transformation (ETL)](3-transformation-etl.md)** where you'll:
- Create Iceberg tables for analytics
- Write PySpark ETL scripts
- Transform operational data to analytical format
- Implement aggregations and enrichment

---

## Troubleshooting

### Query Timeout

**Error:** `ReadTimeout: Timeout waiting for response`

**Solutions:**
1. Add partition key to WHERE clause
2. Reduce LIMIT value
3. Check if data exists
4. Verify HCD is running: `systemctl status hcd`

### ALLOW FILTERING Warning (cqlsh only)

**Warning in cqlsh:** `Cannot execute this query as it might involve data filtering`

**Solution for cqlsh:**
Add `ALLOW FILTERING` to query:
```cql
SELECT * FROM table WHERE non_key_column = 'value' ALLOW FILTERING;
```

**Note:**
- `ALLOW FILTERING` is CQL-specific syntax (cqlsh only)
- Not needed in Query Workspace (Presto) - it filters automatically
- Use sparingly - indicates inefficient query that scans multiple partitions

### No Data Returned

**Possible causes:**
1. Data expired (check TTL)
2. Wrong partition key values
3. Generator not running

**Verify:**
```sql
SELECT COUNT(*) FROM hcd.affiliate_junction.user_activity_tracking;
```

---

## Additional Resources

- [HCD Schema](../hcd_schema.cql) - Complete schema definitions
- [Cassandra Query Language](https://cassandra.apache.org/doc/latest/cql/) - CQL reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [SERVICES.md](../SERVICES.md) - Service documentation

---

**Lab 2 Complete!** ✅

You now understand how to query operational data efficiently in HCD. Continue to Lab 3 to learn how to transform this data for analytics.