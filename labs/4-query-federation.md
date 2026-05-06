# Lab 4: Query Federation

**Duration:** 40-50 minutes  
**Difficulty:** Intermediate to Advanced  
**Environment:** watsonx.data Query Workspace

---

## Lab Overview

In this final lab, you'll experience the power of federated queries - querying across multiple data sources in a single SQL statement. You'll learn:

1. How to query HCD and Iceberg simultaneously
2. Joining operational and analytical data
3. Importing CSV reference data
4. Building complete analytics combining all sources
5. Performance considerations for federated queries

**Building on Labs 1-3:**
You now have data in both HCD (operational) and Iceberg (analytical). Now you'll query across both systems seamlessly.

---

## Prerequisites

✅ Completed Labs 1-3  
✅ Data in HCD (`user_activity_tracking`)  
✅ Data in Iceberg (`user_activity_analytics`)  
✅ Access to watsonx.data Query Workspace  
✅ Understanding of SQL joins

---

## Part 1: Understanding Query Federation (5 minutes)

### What is Query Federation?

**Traditional Approach (Data Movement):**
```
HCD Data → ETL → Copy → Iceberg → Query
         ↓
    Time delay
    Storage duplication
    Complexity
```

**Federated Approach (Query in Place):**
```
HCD Data ←┐
          ├→ Single Query → Results
Iceberg ←─┘
         ↓
    No data movement
    Real-time results
    Unified interface
```

### Query Federation in watsonx.data

**Architecture:**
```
┌─────────────────────────────────────┐
│      Presto Query Engine            │
│  (Federated Query Coordinator)      │
└──────┬──────────────────┬───────────┘
       │                  │
       ↓                  ↓
┌─────────────┐    ┌─────────────┐
│     HCD     │    │   Iceberg   │
│  Connector  │    │  Connector  │
└──────┬──────┘    └──────┬──────┘
       │                  │
       ↓                  ↓
┌─────────────┐    ┌─────────────┐
│ Operational │    │ Analytical  │
│    Data     │    │    Data     │
└─────────────┘    └─────────────┘
```

**Benefits:**
- ✅ **Single SQL interface** - One query language
- ✅ **No data movement** - Query data where it lives
- ✅ **Real-time joins** - Combine operational + analytical
- ✅ **Unified view** - Complete picture across systems
- ✅ **Cost optimization** - Right storage for each workload

### In This Lab

You'll query across:
1. **HCD** - Real-time user activity (last 10 minutes)
2. **Iceberg** - Historical session analytics
3. **CSV** - Reference data (user profiles, benchmarks)

---

## Part 2: Basic Federated Queries (10 minutes)

### Step 1: Query Each Source Separately

Open watsonx.data Query Workspace.

**Query HCD (Operational):**

```sql
SELECT 
    'HCD (Real-Time)' as source,
    COUNT(*) as activity_count,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT session_id) as active_sessions,
    MIN(timestamp) as oldest_activity,
    MAX(timestamp) as newest_activity
FROM hcd.affiliate_junction.user_activity_tracking;
```

**Expected Output:**
```
source           | activity_count | unique_users | active_sessions | oldest_activity      | newest_activity
-----------------+----------------+--------------+-----------------+---------------------+---------------------
HCD (Real-Time)  | 1247           | 45           | 156             | 2026-05-06 11:05:23 | 2026-05-06 11:14:58
```

**Query Iceberg (Analytical):**

```sql
SELECT 
    'Iceberg (Historical)' as source,
    COUNT(*) as session_count,
    COUNT(DISTINCT user_id) as unique_users,
    SUM(total_activities) as total_activities,
    SUM(purchases) as total_purchases,
    ROUND(AVG(session_duration_seconds), 2) as avg_session_duration
FROM iceberg_data.affiliate_junction.user_activity_analytics;
```

**Expected Output:**
```
source                | session_count | unique_users | total_activities | total_purchases | avg_session_duration
----------------------+---------------+--------------+------------------+-----------------+---------------------
Iceberg (Historical)  | 156           | 45           | 1247             | 18              | 145.67
```

### Step 2: Your First Federated Query

**Combine both sources with UNION ALL:**

```sql
SELECT 
    'HCD (Real-Time)' as source,
    COUNT(*) as record_count,
    COUNT(DISTINCT user_id) as unique_users,
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record
FROM hcd.affiliate_junction.user_activity_tracking

UNION ALL

SELECT 
    'Iceberg (Historical)' as source,
    COUNT(*) as record_count,
    COUNT(DISTINCT user_id) as unique_users,
    MIN(session_start) as oldest_record,
    MAX(session_start) as newest_record
FROM iceberg_data.affiliate_junction.user_activity_analytics;
```

**Understanding the Query:**

**`UNION ALL`:**
- Combines results from multiple queries
- Each query can target different catalogs
- Results stacked vertically
- No deduplication (unlike UNION)

**What You're Seeing:**
- Side-by-side comparison of both systems
- Real-time vs historical data
- Data freshness indicators
- Single query, multiple sources

### Step 3: Compare Activity Patterns

**Real-time vs Historical Activity Breakdown:**

```sql
WITH hcd_activity AS (
    SELECT 
        action_type,
        COUNT(*) as count
    FROM hcd.affiliate_junction.user_activity_tracking
    GROUP BY action_type
),
iceberg_activity AS (
    SELECT 
        'page_view' as action_type,
        SUM(page_views) as count
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    
    UNION ALL
    
    SELECT 'click', SUM(clicks)
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    
    UNION ALL
    
    SELECT 'scroll', SUM(scrolls)
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    
    UNION ALL
    
    SELECT 'add_to_cart', SUM(add_to_carts)
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    
    UNION ALL
    
    SELECT 'purchase', SUM(purchases)
    FROM iceberg_data.affiliate_junction.user_activity_analytics
)
SELECT 
    COALESCE(h.action_type, i.action_type) as action_type,
    COALESCE(h.count, 0) as hcd_count,
    COALESCE(i.count, 0) as iceberg_count,
    COALESCE(h.count, 0) + COALESCE(i.count, 0) as total_count
FROM hcd_activity h
FULL OUTER JOIN iceberg_activity i ON h.action_type = i.action_type
ORDER BY total_count DESC;
```

**Understanding the Query:**

**CTEs (Common Table Expressions):**
```sql
WITH hcd_activity AS (...), iceberg_activity AS (...)
```
- Named subqueries for readability
- Can reference each other
- Executed once, reused multiple times

**FULL OUTER JOIN:**
- Includes all records from both sides
- NULL if no match
- `COALESCE` handles NULLs

**Expected Output:**
```
action_type  | hcd_count | iceberg_count | total_count
-------------+-----------+---------------+------------
page_view    | 523       | 523           | 1046
click        | 387       | 387           | 774
scroll       | 201       | 201           | 402
add_to_cart  | 118       | 118           | 236
purchase     | 18        | 18            | 36
```

---

## Part 3: Cross-Catalog Joins (10 minutes)

### Step 4: Join Real-Time with Historical

**Find users active now who have historical data:**

```sql
SELECT 
    h.user_id,
    h.session_id as current_session,
    COUNT(DISTINCT h.action_type) as current_action_types,
    i.total_sessions as historical_sessions,
    i.total_activities as historical_activities,
    i.total_purchases as historical_purchases,
    ROUND(CAST(i.total_purchases AS DOUBLE) / NULLIF(i.total_sessions, 0) * 100, 2) as historical_conversion_rate
FROM hcd.affiliate_junction.user_activity_tracking h
JOIN (
    SELECT 
        user_id,
        COUNT(*) as total_sessions,
        SUM(total_activities) as total_activities,
        SUM(purchases) as total_purchases
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    GROUP BY user_id
) i ON h.user_id = i.user_id
GROUP BY h.user_id, h.session_id, i.total_sessions, i.total_activities, i.total_purchases
ORDER BY historical_conversion_rate DESC NULLS LAST
LIMIT 10;
```

**Understanding the Query:**

**Cross-Catalog JOIN:**
```sql
FROM hcd.affiliate_junction.user_activity_tracking h
JOIN (...) i ON h.user_id = i.user_id
```
- Joins data from HCD with Iceberg
- Presto coordinates the join
- Data stays in original systems

**Subquery in JOIN:**
- Pre-aggregates Iceberg data
- Reduces data transferred
- More efficient than joining raw data

**Use Case:**
- Identify high-value users currently active
- Personalize experience based on history
- Real-time targeting

### Step 5: Session Continuation Analysis

**Find sessions that span both systems:**

```sql
WITH current_sessions AS (
    SELECT 
        user_id,
        session_id,
        MIN(timestamp) as session_start,
        MAX(timestamp) as session_end,
        COUNT(*) as activity_count
    FROM hcd.affiliate_junction.user_activity_tracking
    GROUP BY user_id, session_id
)
SELECT 
    cs.user_id,
    cs.session_id,
    cs.session_start as current_start,
    cs.session_end as current_end,
    cs.activity_count as current_activities,
    ia.session_start as historical_start,
    ia.total_activities as historical_activities,
    ia.converted as historical_converted,
    CASE 
        WHEN cs.session_id = ia.session_id THEN 'Continuing Session'
        ELSE 'New Session'
    END as session_status
FROM current_sessions cs
LEFT JOIN iceberg_data.affiliate_junction.user_activity_analytics ia
    ON cs.user_id = ia.user_id
    AND cs.session_id = ia.session_id
ORDER BY cs.session_start DESC
LIMIT 20;
```

**Understanding the Query:**

**LEFT JOIN:**
- Includes all current sessions
- Matches with historical if exists
- NULL if no historical match

**Use Case:**
- Track session lifecycle
- Identify new vs returning sessions
- Monitor session continuation

---

## Part 4: CSV Data Import and Integration (15 minutes)

### Step 6: Import User Profile CSV

**Create user profile CSV:**

```bash
# SSH to VM
ssh -p <port> watsonx@<hostname>

# Create user profiles
cat > /tmp/user_profiles.csv << 'EOF'
user_id,user_name,user_tier,signup_date,country,preferred_device
user_001,Alice Johnson,Premium,2026-01-15,US,desktop
user_002,Bob Smith,Standard,2026-02-20,UK,mobile
user_003,Carol White,Premium,2026-01-10,CA,desktop
user_004,David Brown,Standard,2026-03-05,US,mobile
user_005,Eve Davis,Premium,2026-01-25,AU,tablet
user_006,Frank Miller,Standard,2026-02-15,UK,desktop
user_007,Grace Lee,Premium,2026-01-30,US,mobile
user_008,Henry Wilson,Standard,2026-03-10,CA,desktop
user_009,Iris Moore,Premium,2026-02-01,US,tablet
user_010,Jack Taylor,Standard,2026-03-15,UK,mobile
EOF
```

**Upload to Minio:**

```bash
# Get Minio credentials
export MINIO_ACCESS_KEY=$(kubectl get secret minio-secret -n wxd -o jsonpath='{.data.accesskey}' | base64 -d)
export MINIO_SECRET_KEY=$(kubectl get secret minio-secret -n wxd -o jsonpath='{.data.secretkey}' | base64 -d)

# Configure mc (Minio client)
mc alias set myminio http://localhost:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY

# Create bucket
mc mb myminio/csv-imports --ignore-existing

# Upload CSV
mc cp /tmp/user_profiles.csv myminio/csv-imports/
```

### Step 7: Create External Table for CSV

**In Query Workspace:**

```sql
-- Create schema for reference data
CREATE SCHEMA IF NOT EXISTS iceberg_data.reference_data
WITH (location = 's3a://iceberg-bucket/reference_data/');

-- Create external table pointing to CSV
CREATE TABLE IF NOT EXISTS iceberg_data.reference_data.user_profiles_csv (
    user_id VARCHAR,
    user_name VARCHAR,
    user_tier VARCHAR,
    signup_date VARCHAR,
    country VARCHAR,
    preferred_device VARCHAR
) WITH (
    external_location = 's3a://csv-imports/',
    format = 'CSV',
    csv_separator = ',',
    skip_header_line_count = 1
);
```

**Explanation:**

**External Table:**
- Points to existing CSV files
- No data copying
- Schema-on-read
- Useful for ad-hoc analysis

**CSV Format Options:**
- `csv_separator` - Column delimiter
- `skip_header_line_count` - Skip header row
- `format = 'CSV'` - File format

**Verify CSV data:**

```sql
SELECT * FROM iceberg_data.reference_data.user_profiles_csv LIMIT 10;
```

### Step 8: Convert CSV to Iceberg Format

**Create Iceberg table:**

```sql
CREATE TABLE IF NOT EXISTS iceberg_data.reference_data.user_profiles (
    user_id VARCHAR,
    user_name VARCHAR,
    user_tier VARCHAR,
    signup_date DATE,
    country VARCHAR,
    preferred_device VARCHAR
) WITH (
    format = 'PARQUET'
);
```

**Load data from CSV:**

```sql
INSERT INTO iceberg_data.reference_data.user_profiles
SELECT 
    user_id,
    user_name,
    user_tier,
    CAST(signup_date AS DATE),
    country,
    preferred_device
FROM iceberg_data.reference_data.user_profiles_csv;
```

**Explanation:**

**Why Convert to Iceberg?**
- ✅ Better query performance
- ✅ Schema enforcement
- ✅ Type conversion (VARCHAR → DATE)
- ✅ Compression
- ✅ Indexing

**Verify conversion:**

```sql
SELECT 
    'CSV External' as source,
    COUNT(*) as record_count
FROM iceberg_data.reference_data.user_profiles_csv

UNION ALL

SELECT 
    'Iceberg' as source,
    COUNT(*) as record_count
FROM iceberg_data.reference_data.user_profiles;
```

---

## Part 5: Complete Federated Analytics (10 minutes)

### Step 9: Three-Way Federation

**Join HCD + Iceberg + CSV:**

```sql
SELECT 
    up.user_name,
    up.user_tier,
    up.country,
    up.preferred_device,
    COUNT(DISTINCT h.session_id) as current_sessions,
    COUNT(h.action_type) as current_activities,
    ia.total_sessions as historical_sessions,
    ia.total_activities as historical_activities,
    ia.total_purchases as historical_purchases,
    ROUND(CAST(ia.total_purchases AS DOUBLE) / NULLIF(ia.total_sessions, 0) * 100, 2) as conversion_rate,
    CASE 
        WHEN up.preferred_device = h.metadata THEN 'Preferred Device'
        ELSE 'Other Device'
    END as device_match
FROM iceberg_data.reference_data.user_profiles up
LEFT JOIN hcd.affiliate_junction.user_activity_tracking h
    ON up.user_id = h.user_id
LEFT JOIN (
    SELECT 
        user_id,
        COUNT(*) as total_sessions,
        SUM(total_activities) as total_activities,
        SUM(purchases) as total_purchases
    FROM iceberg_data.affiliate_junction.user_activity_analytics
    GROUP BY user_id
) ia ON up.user_id = ia.user_id
GROUP BY 
    up.user_name, up.user_tier, up.country, up.preferred_device,
    ia.total_sessions, ia.total_activities, ia.total_purchases, h.metadata
ORDER BY historical_purchases DESC NULLS LAST
LIMIT 10;
```

**Understanding the Query:**

**Three Data Sources:**
1. `user_profiles` (CSV → Iceberg) - Reference data
2. `user_activity_tracking` (HCD) - Real-time operational
3. `user_activity_analytics` (Iceberg) - Historical analytical

**Query Pattern:**
```
CSV Reference Data (user profiles)
        ↓
    LEFT JOIN
        ↓
HCD Real-Time (current activity)
        ↓
    LEFT JOIN
        ↓
Iceberg Historical (session analytics)
```

**Use Case:**
- Complete user profile with activity
- Personalization based on tier and history
- Device preference analysis
- Conversion optimization

### Step 10: Advanced Analytics Query

**User Segmentation with Complete Data:**

```sql
WITH user_complete_profile AS (
    SELECT 
        up.user_id,
        up.user_name,
        up.user_tier,
        up.signup_date,
        up.country,
        COALESCE(ia.total_sessions, 0) as total_sessions,
        COALESCE(ia.total_activities, 0) as total_activities,
        COALESCE(ia.total_purchases, 0) as total_purchases,
        COALESCE(ia.total_page_views, 0) as total_page_views,
        CURRENT_DATE - up.signup_date as days_since_signup
    FROM iceberg_data.reference_data.user_profiles up
    LEFT JOIN (
        SELECT 
            user_id,
            COUNT(*) as total_sessions,
            SUM(total_activities) as total_activities,
            SUM(purchases) as total_purchases,
            SUM(page_views) as total_page_views
        FROM iceberg_data.affiliate_junction.user_activity_analytics
        GROUP BY user_id
    ) ia ON up.user_id = ia.user_id
),
current_activity AS (
    SELECT 
        user_id,
        COUNT(DISTINCT session_id) as active_sessions,
        COUNT(*) as recent_activities
    FROM hcd.affiliate_junction.user_activity_tracking
    GROUP BY user_id
)
SELECT 
    ucp.user_tier,
    ucp.country,
    COUNT(DISTINCT ucp.user_id) as user_count,
    ROUND(AVG(ucp.total_sessions), 2) as avg_sessions,
    ROUND(AVG(ucp.total_activities), 2) as avg_activities,
    ROUND(AVG(ucp.total_purchases), 2) as avg_purchases,
    ROUND(AVG(CAST(ucp.total_purchases AS DOUBLE) / NULLIF(ucp.total_sessions, 0)) * 100, 2) as avg_conversion_rate,
    COUNT(ca.user_id) as currently_active_users,
    ROUND(CAST(COUNT(ca.user_id) AS DOUBLE) / COUNT(DISTINCT ucp.user_id) * 100, 2) as active_percentage
FROM user_complete_profile ucp
LEFT JOIN current_activity ca ON ucp.user_id = ca.user_id
GROUP BY ucp.user_tier, ucp.country
ORDER BY avg_conversion_rate DESC NULLS LAST;
```

**Understanding the Query:**

**Multi-Level CTEs:**
1. `user_complete_profile` - Combines CSV + Iceberg historical
2. `current_activity` - Aggregates HCD real-time
3. Final SELECT - Segments and analyzes

**Metrics Calculated:**
- User counts by segment
- Average engagement metrics
- Conversion rates
- Current activity percentage

**Use Case:**
- Market segmentation
- Tier performance analysis
- Geographic insights
- Real-time engagement tracking

---

## Lab Summary

### What You've Accomplished

✅ **Executed federated queries** across HCD and Iceberg  
✅ **Joined operational and analytical data** in single queries  
✅ **Imported CSV reference data** via external tables  
✅ **Built complete analytics** combining all three sources  
✅ **Created user segmentation** with real-time + historical + reference data  

### Key Concepts Learned

**1. Query Federation**
- Single SQL interface across multiple systems
- No data movement required
- Real-time results
- Unified view

**2. Cross-Catalog Joins**
- JOIN across HCD and Iceberg
- Presto coordinates execution
- Efficient query planning
- Data stays in place

**3. CSV Integration**
- External tables for quick access
- Convert to Iceberg for performance
- Schema-on-read flexibility
- Reference data patterns

**4. Multi-Source Analytics**
- Three-way joins (HCD + Iceberg + CSV)
- Complete user profiles
- Real-time + historical + reference
- Business intelligence queries

**5. Performance Patterns**
- Use CTEs for readability
- Pre-aggregate before joining
- Leverage partitioning
- Monitor query plans

### Your Complete Data Architecture

```
┌─────────────────┐
│  CSV Reference  │ ← User profiles, benchmarks
└────────┬────────┘
         │
         ↓ JOIN
┌─────────────────┐
│  HCD Real-Time  │ ← Current activity (10 min)
└────────┬────────┘
         │
         ↓ JOIN
┌─────────────────┐
│Iceberg Analytics│ ← Historical sessions
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Federated Query │ ← Complete picture
└─────────────────┘
```

---

## Performance Best Practices

### ✅ DO:

**1. Use Partition Pruning:**
```sql
WHERE session_start > CURRENT_TIMESTAMP - INTERVAL '1' HOUR
```

**2. Pre-Aggregate Before Joining:**
```sql
JOIN (
    SELECT user_id, SUM(purchases) as total_purchases
    FROM iceberg_table
    GROUP BY user_id
) agg ON ...
```

**3. Use CTEs for Readability:**
```sql
WITH hcd_data AS (...), iceberg_data AS (...)
SELECT * FROM hcd_data JOIN iceberg_data ...
```

**4. Limit Result Sets:**
```sql
LIMIT 1000
```

**5. Use EXPLAIN to Understand Query Plans:**
```sql
EXPLAIN SELECT ...
```

### ❌ DON'T:

**1. Avoid Full Table Scans:**
```sql
-- Bad: Scans entire table
SELECT * FROM large_table;
```

**2. Don't Join Large Tables Without Filters:**
```sql
-- Bad: Joins billions of records
SELECT * FROM hcd_table JOIN iceberg_table ON ...;
```

**3. Avoid SELECT * in Production:**
```sql
-- Bad: Retrieves all columns
SELECT * FROM table;

-- Good: Select only needed columns
SELECT user_id, session_id, timestamp FROM table;
```

---

## Troubleshooting

### Query Timeout

**Error:** `Query exceeded maximum time limit`

**Solutions:**
1. Add time filters to reduce data scanned
2. Use partition pruning
3. Pre-aggregate before joining
4. Increase query timeout (if allowed)

### Catalog Not Found

**Error:** `Catalog 'hcd' does not exist`

**Solution:**
Verify catalogs:
```sql
SHOW CATALOGS;
SHOW SCHEMAS FROM hcd;
SHOW SCHEMAS FROM iceberg_data;
```

### Join Performance Issues

**Symptoms:**
- Query runs for minutes
- High memory usage
- Timeout errors

**Solutions:**
1. Add WHERE clauses to both sides of JOIN
2. Use smaller time windows
3. Pre-aggregate data
4. Check partition alignment

### CSV Import Failed

**Error:** `Unable to read CSV file`

**Solutions:**
1. Verify file uploaded to Minio: `mc ls myminio/csv-imports/`
2. Check CSV format (commas, quotes, headers)
3. Verify external_location path
4. Check file permissions

---

## Next Steps

### Congratulations! 🎉

You've completed all 4 labs and built a complete data pipeline:

1. ✅ **Lab 1**: Created real-time data ingestion
2. ✅ **Lab 2**: Mastered operational queries in HCD
3. ✅ **Lab 3**: Built ETL pipeline to Iceberg
4. ✅ **Lab 4**: Executed federated queries across all sources

### Continue Learning

**Explore More:**
- [FEDERATED_QUERIES.md](../FEDERATED_QUERIES.md) - 15+ query examples
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Complete system architecture
- [DEMO_SCRIPT.md](../DEMO_SCRIPT.md) - Full demo walkthrough
- [SERVICES.md](../SERVICES.md) - Service documentation

**Try These Challenges:**
1. Create your own CSV dataset and integrate it
2. Build a dashboard using federated queries
3. Implement real-time alerting based on patterns
4. Design a recommendation engine using all data sources
5. Create materialized views for common queries

---

## Additional Resources

- [Presto Documentation](https://prestodb.io/docs/current/) - Presto SQL reference
- [Iceberg Documentation](https://iceberg.apache.org/) - Apache Iceberg
- [watsonx.data Documentation](https://www.ibm.com/docs/en/watsonxdata) - Official docs
- [SQL Best Practices](https://mode.com/sql-tutorial/) - SQL optimization

---

**All Labs Complete!** ✅

You now have hands-on experience with watsonx.data's federated architecture, from real-time ingestion through ETL to advanced analytics. You've built a complete data pipeline that demonstrates the power of querying data where it lives.

**Thank you for completing the Affiliate Junction labs!**