# Lab 3: Transformation (ETL)

**Duration:** 40-50 minutes  
**Difficulty:** Intermediate to Advanced  
**Environment:** watsonx.data Query Workspace + SSH/Python

---

## Lab Overview

In this lab, you'll build an ETL (Extract, Transform, Load) pipeline to move data from operational storage (HCD) to analytical storage (Iceberg). You'll learn:

1. How to create Iceberg tables for analytics
2. Writing PySpark scripts for data transformation
3. Implementing aggregations and enrichment
4. Scheduling continuous ETL processes
5. Monitoring ETL performance

**Building on Labs 1 & 2:**
You created `user_activity_tracking` in HCD. Now you'll transform it into analytical format in Iceberg.

---

## Prerequisites

✅ Completed Labs 1 & 2  
✅ User activity data in HCD  
✅ Access to watsonx.data Query Workspace  
✅ SSH access to VM  
✅ Basic Python knowledge

---

## Part 1: Understanding ETL Architecture (5 minutes)

### The ETL Pattern

**Extract, Transform, Load:**

```
┌─────────────┐
│     HCD     │  ← Operational Data (5-10 min TTL)
│ (Cassandra) │     • High-velocity writes
└──────┬──────┘     • Short retention
       │            • Real-time queries
       │ EXTRACT
       ↓
┌─────────────┐
│   PySpark   │  ← Transformation Layer
│     ETL     │     • Aggregations
└──────┬──────┘     • Enrichment
       │            • Filtering
       │ TRANSFORM
       ↓
┌─────────────┐
│   Iceberg   │  ← Analytical Data (permanent)
│  (Presto)   │     • Historical storage
└─────────────┘     • Complex analytics
                    • Long-term retention
```

### Why ETL?

**Extract:**
- Read data from HCD before TTL expiration
- Capture minute-bucketed data
- Handle high-volume reads efficiently

**Transform:**
- Aggregate by time windows
- Calculate conversion rates
- Identify patterns and trends
- Enrich with metadata

**Load:**
- Write to partitioned Iceberg tables
- Store for long-term analytics
- Enable complex queries
- Support historical analysis

### ETL Services in This Demo

**1. `hcd_to_presto.service`**
- Reads: Raw impressions from HCD
- Transforms: Aggregates by minute
- Writes: To Iceberg tables
- Technology: PySpark
- Frequency: Continuous

**2. `presto_to_hcd.service`**
- Reads: Analytics from Presto
- Transforms: Calculates summaries
- Writes: Back to HCD for serving
- Technology: Python + Presto
- Frequency: Continuous

---

## Part 2: Create Iceberg Tables for Analytics (10 minutes)

### Step 1: Understand Iceberg Table Format

**Iceberg Benefits:**
- ✅ **Schema evolution** - Add/modify columns safely
- ✅ **Time travel** - Query historical versions
- ✅ **Partitioning** - Efficient data organization
- ✅ **ACID transactions** - Data consistency
- ✅ **Metadata management** - Fast query planning

### Step 2: Create Your Analytics Schema

Open watsonx.data Query Workspace and create your analytics tables:

**Create schema (if needed):**

```sql
CREATE SCHEMA IF NOT EXISTS iceberg_data.affiliate_junction
WITH (location = 's3a://iceberg-bucket/affiliate_junction/');
```

**Explanation:**
- `iceberg_data` - Catalog name for Iceberg tables
- `affiliate_junction` - Schema name (matches HCD keyspace)
- `s3a://iceberg-bucket/` - S3-compatible storage location (Minio)

### Step 3: Create User Activity Analytics Table

```sql
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.user_activity_analytics (
    user_id VARCHAR,
    session_id VARCHAR,
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    session_duration_seconds BIGINT,
    total_activities BIGINT,
    page_views BIGINT,
    clicks BIGINT,
    scrolls BIGINT,
    add_to_carts BIGINT,
    purchases BIGINT,
    pages_visited BIGINT,
    unique_pages ARRAY(VARCHAR),
    first_page VARCHAR,
    last_page VARCHAR,
    converted BOOLEAN,
    device_type VARCHAR,
    browser_type VARCHAR,
    created_at TIMESTAMP
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['hour(session_start)', 'bucket(user_id, 5)']
);
```

**Understanding the Schema:**

**Aggregated Metrics:**
- `total_activities` - Count of all actions
- `page_views`, `clicks`, etc. - Breakdown by action type
- `pages_visited` - Count of unique pages
- `session_duration_seconds` - Time spent in session

**Enrichment Fields:**
- `unique_pages` - ARRAY of all pages visited
- `first_page` / `last_page` - Entry and exit pages
- `converted` - Boolean flag for purchase
- `device_type` / `browser_type` - Extracted from metadata

**Partitioning Strategy:**
```sql
partitioning = ARRAY['hour(session_start)', 'bucket(user_id, 5)']
```

**Explanation:**
- `hour(session_start)` - Partition by hour for time-based queries
- `bucket(user_id, 5)` - Distribute users across 5 buckets
- Enables efficient pruning for both time and user queries

**Why PARQUET format?**
- ✅ Columnar storage - Fast for analytics
- ✅ Compression - Saves storage space
- ✅ Schema embedded - Self-describing
- ✅ Predicate pushdown - Efficient filtering

### Step 4: Create Hourly Summary Table

```sql
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.user_activity_hourly (
    hour_bucket TIMESTAMP,
    total_users BIGINT,
    total_sessions BIGINT,
    total_activities BIGINT,
    total_page_views BIGINT,
    total_clicks BIGINT,
    total_purchases BIGINT,
    conversion_rate DOUBLE,
    avg_session_duration_seconds DOUBLE,
    avg_activities_per_session DOUBLE,
    top_pages ARRAY(ROW(page_url VARCHAR, view_count BIGINT)),
    created_at TIMESTAMP
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['hour(hour_bucket)']
);
```

**Understanding Hourly Aggregations:**

**Metrics:**
- Counts: users, sessions, activities
- Rates: conversion_rate
- Averages: session duration, activities per session

**Complex Types:**
- `ARRAY(ROW(...))` - Nested structure for top pages
- Stores multiple values in single column
- Efficient for dashboard queries

---

## Part 3: Write PySpark ETL Script (15 minutes)

### Step 5: Create ETL Script

SSH to your VM and create the ETL script:

```bash
ssh -p <port> watsonx@<hostname>

cat > ~/user_activity_etl.py << 'EOF'
#!/usr/bin/env python3
"""
User Activity ETL
Extracts user activity from HCD, transforms to session analytics, loads to Iceberg
"""

import os
import sys
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Configuration
HCD_HOST = '172.17.0.1'
HCD_PORT = 9042
HCD_USER = 'cassandra'
HCD_PASSWD = 'cassandra'
HCD_KEYSPACE = 'affiliate_junction'
HCD_TABLE = 'user_activity_tracking'

ICEBERG_CATALOG = 'iceberg_data'
ICEBERG_SCHEMA = 'affiliate_junction'
ICEBERG_TABLE = 'user_activity_analytics'

def create_spark_session():
    """Create Spark session with Iceberg support"""
    print("Creating Spark session...")
    
    spark = SparkSession.builder \
        .appName("UserActivityETL") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.iceberg_data", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.iceberg_data.type", "hadoop") \
        .config("spark.sql.catalog.iceberg_data.warehouse", "s3a://iceberg-bucket/") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ACCESS_KEY", "admin")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_SECRET_KEY", "password")) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()
    
    print(f"Spark version: {spark.version}")
    return spark

def extract_from_hcd():
    """Extract user activity data from HCD"""
    print(f"\nExtracting data from HCD...")
    print(f"  Host: {HCD_HOST}:{HCD_PORT}")
    print(f"  Keyspace: {HCD_KEYSPACE}")
    print(f"  Table: {HCD_TABLE}")
    
    # Connect to HCD
    auth_provider = PlainTextAuthProvider(username=HCD_USER, password=HCD_PASSWD)
    cluster = Cluster([HCD_HOST], port=HCD_PORT, auth_provider=auth_provider)
    session = cluster.connect(HCD_KEYSPACE)
    
    # Query all recent activity
    query = f"SELECT * FROM {HCD_TABLE}"
    rows = session.execute(query)
    
    # Convert to list of dicts
    data = []
    for row in rows:
        data.append({
            'user_id': row.user_id,
            'session_id': row.session_id,
            'page_url': row.page_url,
            'action_type': row.action_type,
            'timestamp': row.timestamp,
            'metadata': row.metadata
        })
    
    session.shutdown()
    cluster.shutdown()
    
    print(f"  Extracted {len(data)} records")
    return data

def transform_to_session_analytics(spark, raw_data):
    """Transform raw activity into session analytics"""
    print(f"\nTransforming data...")
    
    if not raw_data:
        print("  No data to transform")
        return None
    
    # Create DataFrame from raw data
    df = spark.createDataFrame(raw_data)
    
    print(f"  Raw records: {df.count()}")
    
    # Parse metadata JSON
    df = df.withColumn("metadata_parsed", from_json(col("metadata"), 
        StructType([
            StructField("device", StringType()),
            StructField("browser", StringType()),
            StructField("duration_ms", IntegerType())
        ])
    ))
    
    # Extract device and browser
    df = df.withColumn("device_type", col("metadata_parsed.device")) \
           .withColumn("browser_type", col("metadata_parsed.browser"))
    
    # Aggregate by session
    session_analytics = df.groupBy("user_id", "session_id") \
        .agg(
            min("timestamp").alias("session_start"),
            max("timestamp").alias("session_end"),
            count("*").alias("total_activities"),
            sum(when(col("action_type") == "page_view", 1).otherwise(0)).alias("page_views"),
            sum(when(col("action_type") == "click", 1).otherwise(0)).alias("clicks"),
            sum(when(col("action_type") == "scroll", 1).otherwise(0)).alias("scrolls"),
            sum(when(col("action_type") == "add_to_cart", 1).otherwise(0)).alias("add_to_carts"),
            sum(when(col("action_type") == "purchase", 1).otherwise(0)).alias("purchases"),
            countDistinct("page_url").alias("pages_visited"),
            collect_set("page_url").alias("unique_pages"),
            first("page_url").alias("first_page"),
            last("page_url").alias("last_page"),
            first("device_type").alias("device_type"),
            first("browser_type").alias("browser_type")
        )
    
    # Calculate session duration
    session_analytics = session_analytics.withColumn(
        "session_duration_seconds",
        (unix_timestamp("session_end") - unix_timestamp("session_start"))
    )
    
    # Add converted flag
    session_analytics = session_analytics.withColumn(
        "converted",
        when(col("purchases") > 0, True).otherwise(False)
    )
    
    # Add created_at timestamp
    session_analytics = session_analytics.withColumn(
        "created_at",
        current_timestamp()
    )
    
    print(f"  Transformed to {session_analytics.count()} sessions")
    
    # Show sample
    print("\n  Sample transformed data:")
    session_analytics.select(
        "user_id", "session_id", "total_activities", 
        "page_views", "clicks", "purchases", "converted"
    ).show(5, truncate=False)
    
    return session_analytics

def load_to_iceberg(spark, df):
    """Load transformed data to Iceberg table"""
    if df is None or df.count() == 0:
        print("\nNo data to load")
        return
    
    print(f"\nLoading to Iceberg...")
    print(f"  Catalog: {ICEBERG_CATALOG}")
    print(f"  Schema: {ICEBERG_SCHEMA}")
    print(f"  Table: {ICEBERG_TABLE}")
    
    table_name = f"{ICEBERG_CATALOG}.{ICEBERG_SCHEMA}.{ICEBERG_TABLE}"
    
    # Write to Iceberg table
    df.writeTo(table_name) \
        .using("iceberg") \
        .append()
    
    print(f"  Loaded {df.count()} records")

def create_hourly_summary(spark):
    """Create hourly summary from session analytics"""
    print(f"\nCreating hourly summary...")
    
    table_name = f"{ICEBERG_CATALOG}.{ICEBERG_SCHEMA}.{ICEBERG_TABLE}"
    
    # Read session analytics
    df = spark.read.format("iceberg").load(table_name)
    
    if df.count() == 0:
        print("  No data for summary")
        return
    
    # Aggregate by hour
    hourly = df.withColumn("hour_bucket", date_trunc("hour", col("session_start"))) \
        .groupBy("hour_bucket") \
        .agg(
            countDistinct("user_id").alias("total_users"),
            count("session_id").alias("total_sessions"),
            sum("total_activities").alias("total_activities"),
            sum("page_views").alias("total_page_views"),
            sum("clicks").alias("total_clicks"),
            sum("purchases").alias("total_purchases"),
            avg("session_duration_seconds").alias("avg_session_duration_seconds"),
            avg("total_activities").alias("avg_activities_per_session"),
            lit(None).cast("array<struct<page_url:string,view_count:bigint>>").alias("top_pages")
        )
    
    # Calculate conversion rate
    hourly = hourly.withColumn(
        "conversion_rate",
        round(col("total_purchases") / col("total_sessions") * 100, 2)
    )
    
    # Add created_at
    hourly = hourly.withColumn("created_at", current_timestamp())
    
    print(f"  Created {hourly.count()} hourly summaries")
    
    # Show results
    print("\n  Hourly Summary:")
    hourly.select(
        "hour_bucket", "total_users", "total_sessions", 
        "total_activities", "conversion_rate"
    ).show(truncate=False)
    
    # Write to hourly table
    hourly_table = f"{ICEBERG_CATALOG}.{ICEBERG_SCHEMA}.user_activity_hourly"
    hourly.writeTo(hourly_table) \
        .using("iceberg") \
        .append()
    
    print(f"  Loaded to {hourly_table}")

def main():
    """Main ETL execution"""
    print("=" * 60)
    print("User Activity ETL")
    print("=" * 60)
    
    try:
        # Create Spark session
        spark = create_spark_session()
        
        # Extract from HCD
        raw_data = extract_from_hcd()
        
        # Transform to session analytics
        session_analytics = transform_to_session_analytics(spark, raw_data)
        
        # Load to Iceberg
        load_to_iceberg(spark, session_analytics)
        
        # Create hourly summary
        create_hourly_summary(spark)
        
        print("\n" + "=" * 60)
        print("ETL Complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
EOF

chmod +x ~/user_activity_etl.py
```

**Understanding the ETL Script:**

**1. Spark Session Creation:**
```python
.config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
```
- Enables Iceberg support in Spark
- Required for reading/writing Iceberg tables

**2. Extract from HCD:**
```python
query = f"SELECT * FROM {HCD_TABLE}"
rows = session.execute(query)
```
- Reads all current data from HCD
- Before TTL expiration
- Converts to Python dicts

**3. Transform with PySpark:**
```python
df.groupBy("user_id", "session_id").agg(...)
```
- Groups by session
- Aggregates metrics
- Calculates derived fields

**4. Load to Iceberg:**
```python
df.writeTo(table_name).using("iceberg").append()
```
- Appends to existing table
- Maintains partitioning
- ACID transaction

---

## Part 4: Run the ETL (10 minutes)

### Step 6: Execute ETL Script

**Make sure you have data in HCD:**

```bash
# Run your activity generator from Lab 1
python3 ~/user_activity_generator.py
# Let it run for 1-2 minutes, then Ctrl+C
```

**Run the ETL:**

```bash
python3 ~/user_activity_etl.py
```

**Expected Output:**
```
============================================================
User Activity ETL
============================================================
Creating Spark session...
Spark version: 3.3.2

Extracting data from HCD...
  Host: 172.17.0.1:9042
  Keyspace: affiliate_junction
  Table: user_activity_tracking
  Extracted 1247 records

Transforming data...
  Raw records: 1247
  Transformed to 156 sessions

  Sample transformed data:
+--------+-----------+----------------+----------+------+----------+----------+
|user_id |session_id |total_activities|page_views|clicks|purchases |converted |
+--------+-----------+----------------+----------+------+----------+----------+
|user_001|session_1234|15             |8         |5     |1         |true      |
|user_002|session_5678|23             |12        |8     |0         |false     |
...

Loading to Iceberg...
  Catalog: iceberg_data
  Schema: affiliate_junction
  Table: user_activity_analytics
  Loaded 156 records

Creating hourly summary...
  Created 2 hourly summaries

  Hourly Summary:
+-------------------+-----------+--------------+----------------+---------------+
|hour_bucket        |total_users|total_sessions|total_activities|conversion_rate|
+-------------------+-----------+--------------+----------------+---------------+
|2026-05-06 10:00:00|45         |78            |1089            |12.82          |
|2026-05-06 11:00:00|38         |78            |158             |10.26          |
+-------------------+-----------+--------------+----------------+---------------+
  Loaded to iceberg_data.affiliate_junction.user_activity_hourly

============================================================
ETL Complete!
============================================================
```

### Step 7: Verify Data in Iceberg

**Query session analytics:**

```sql
SELECT 
    user_id,
    session_id,
    session_start,
    total_activities,
    page_views,
    clicks,
    purchases,
    converted,
    device_type
FROM iceberg_data.affiliate_junction.user_activity_analytics
ORDER BY session_start DESC
LIMIT 10;
```

**Query hourly summary:**

```sql
SELECT 
    hour_bucket,
    total_users,
    total_sessions,
    total_activities,
    conversion_rate,
    avg_session_duration_seconds
FROM iceberg_data.affiliate_junction.user_activity_hourly
ORDER BY hour_bucket DESC;
```

**Count records:**

```sql
SELECT 
    'Session Analytics' as table_name,
    COUNT(*) as record_count
FROM iceberg_data.affiliate_junction.user_activity_analytics

UNION ALL

SELECT 
    'Hourly Summary' as table_name,
    COUNT(*) as record_count
FROM iceberg_data.affiliate_junction.user_activity_hourly;
```

---

## Part 5: Schedule Continuous ETL (Optional - 5 minutes)

### Step 8: Create Systemd Service

For continuous ETL, create a systemd service:

```bash
sudo cat > /etc/systemd/system/user-activity-etl.service << 'EOF'
[Unit]
Description=User Activity ETL Service
After=network.target hcd.service

[Service]
Type=simple
User=watsonx
WorkingDirectory=/home/watsonx
ExecStart=/usr/bin/python3 /home/watsonx/user_activity_etl.py
Restart=always
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Start service
sudo systemctl start user-activity-etl

# Check status
sudo systemctl status user-activity-etl

# View logs
journalctl -u user-activity-etl -f
```

**Understanding the Service:**
- Runs ETL every 60 seconds
- Automatically restarts on failure
- Logs to systemd journal
- Starts on boot

---

## Lab Summary

### What You've Accomplished

✅ **Created Iceberg tables** for analytical storage  
✅ **Wrote PySpark ETL script** for data transformation  
✅ **Implemented aggregations** (session analytics, hourly summaries)  
✅ **Loaded data to Iceberg** with partitioning  
✅ **Verified data** in analytical tables  

### Key Concepts Learned

**1. ETL Pattern**
- Extract: Read from operational store
- Transform: Aggregate and enrich
- Load: Write to analytical store

**2. Iceberg Tables**
- Schema evolution support
- Time travel capabilities
- Efficient partitioning
- ACID transactions

**3. PySpark Transformations**
- DataFrame operations
- Aggregations (groupBy, agg)
- Window functions
- Complex types (ARRAY, ROW)

**4. Data Partitioning**
- Time-based partitioning
- Hash-based bucketing
- Query optimization
- Partition pruning

**5. Continuous Processing**
- Systemd services
- Automatic restarts
- Log management
- Scheduling patterns

### Your Data Pipeline

```
HCD (Operational)
      ↓
  PySpark ETL
      ↓
Iceberg (Analytical)
      ↓
  Analytics Queries
```

---

## Next Steps

Continue to **[Lab 4: Query Federation](4-query-federation.md)** where you'll:
- Execute federated queries across HCD and Iceberg
- Join operational and analytical data
- Import CSV reference data
- Build complete analytics combining all sources

---

## Troubleshooting

### Spark Session Creation Failed

**Error:** `java.lang.ClassNotFoundException: org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions`

**Solution:**
Ensure Iceberg JARs are in Spark classpath. Check existing ETL services for correct configuration.

### S3A Connection Error

**Error:** `AmazonS3Exception: Access Denied`

**Solution:**
Check Minio credentials:
```bash
kubectl get secret minio-secret -n wxd -o jsonpath='{.data.accesskey}' | base64 -d
kubectl get secret minio-secret -n wxd -o jsonpath='{.data.secretkey}' | base64 -d
```

### No Data Extracted

**Possible causes:**
1. HCD table empty (run generator first)
2. Data expired (TTL = 10 minutes)
3. Wrong table name

**Verify:**
```sql
SELECT COUNT(*) FROM hcd.affiliate_junction.user_activity_tracking;
```

### ETL Script Hangs

**Possible causes:**
1. Large dataset (be patient)
2. Spark resource constraints
3. Network issues

**Check logs:**
```bash
tail -f ~/user_activity_etl.log
```

---

## Additional Resources

- [PySpark Documentation](https://spark.apache.org/docs/latest/api/python/) - PySpark API reference
- [Iceberg Documentation](https://iceberg.apache.org/) - Apache Iceberg docs
- [hcd_to_presto.py](../hcd_to_presto.py) - Production ETL example
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture

---

**Lab 3 Complete!** ✅

You've built a complete ETL pipeline transforming operational data to analytical format. Continue to Lab 4 to query across both systems with federation.