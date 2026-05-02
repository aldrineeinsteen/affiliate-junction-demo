# Services Documentation - Affiliate Junction Demo

Complete guide to all systemd services in the Affiliate Junction demo, their purpose, data flow, and troubleshooting.

## Table of Contents

1. [Service Overview](#service-overview)
2. [Service Dependencies](#service-dependencies)
3. [Detailed Service Documentation](#detailed-service-documentation)
4. [Data Flow](#data-flow)
5. [Troubleshooting](#troubleshooting)

---

## Service Overview

The Affiliate Junction demo uses 7 systemd services that work together to demonstrate a complete data pipeline:

| Service | Purpose | Technology | Java Version |
|---------|---------|------------|--------------|
| `hcd.service` | Operational database | HCD (Cassandra) | Java 11 |
| `generate_traffic.service` | Synthetic data generation | Python | N/A |
| `hcd_to_presto.service` | ETL: HCD → Iceberg | PySpark | Java 17 |
| `presto_to_hcd.service` | ETL: Iceberg → HCD | PySpark | Java 17 |
| `presto_insights.service` | Analytics processing | Python/Presto | N/A |
| `presto_cleanup.service` | Data lifecycle management | Python/Presto | N/A |
| `uvicorn.service` | Web UI server | FastAPI/Uvicorn | N/A |

---

## Service Dependencies

```
hcd.service (HCD Database)
  └─ generate_traffic.service (Data Generator)
       └─ hcd_to_presto.service (ETL: HCD → Iceberg)
            ├─ presto_to_hcd.service (ETL: Iceberg → HCD)
            │    └─ uvicorn.service (Web UI)
            ├─ presto_insights.service (Analytics)
            └─ presto_cleanup.service (Cleanup)
```

**Startup Order:**
1. HCD starts first (database must be ready)
2. Traffic generator waits 30s, then starts generating data
3. HCD→Presto ETL waits 60s, then starts moving data to Iceberg
4. Presto→HCD ETL starts after HCD→Presto is running
5. Web UI, insights, and cleanup services start in parallel

---

## Detailed Service Documentation

### 1. HCD Service (`hcd.service`)

**Purpose:** Provides the operational database for real-time data storage.

**Technology:** HCD 1.2.5 (IBM's Cassandra distribution)

**Configuration:**
- **Port:** 9042 (CQL)
- **Data Directory:** `/opt/hcd-1.2.5/data`
- **Config:** `/opt/hcd-1.2.5/conf/cassandra.yaml`
- **Java:** Java 11 (required by Cassandra)

**Tables:**
- `impression_tracking` - Raw impression events (TTL: 5 min)
- `impressions_by_minute` - Bucketed impressions (TTL: 10 min)
- `conversion_tracking` - Raw conversion events (TTL: 5 min)
- `conversions_by_minute` - Bucketed conversions (TTL: 10 min)
- `publishers` - Aggregated publisher metrics (no TTL)
- `advertisers` - Aggregated advertiser metrics (no TTL)

**Key Features:**
- **TTL-based expiration:** Operational data expires automatically
- **Partition strategy:** Composite keys for efficient queries
- **TIMEUUID clustering:** Time-ordered data retrieval

**Management Commands:**
```bash
# Service control
systemctl status hcd
systemctl restart hcd

# CQL shell
/opt/hcd-1.2.5/bin/cqlsh

# Check cluster status
/opt/hcd-1.2.5/bin/nodetool status

# View logs
journalctl -u hcd -f
```

**Common Issues:**
- **Java version mismatch:** HCD requires Java 11, not Java 17
- **Port conflicts:** Ensure port 9042 is not in use
- **Memory:** Requires at least 4GB RAM

---

### 2. Generate Traffic Service (`generate_traffic.service`)

**Purpose:** Generates synthetic affiliate marketing data to simulate real-world traffic.

**Technology:** Python 3.9 with Cassandra driver

**Script:** [`generate_traffic.py`](generate_traffic.py)

**Data Generation:**
- **Publishers:** 50 publishers with varying traffic patterns
- **Advertisers:** 10 advertisers with different conversion rates
- **Impressions:** 1000-5000 per cycle
- **Conversions:** 50-200 per cycle (2-4% conversion rate)
- **Cycle:** Runs every 60 seconds

**Data Flow:**
1. Generates random impressions with:
   - Publisher ID, Advertiser ID, Cookie ID
   - Timestamp (TIMEUUID)
   - Bucket (minute of hour: 0-59)
2. Generates conversions based on impressions:
   - Links to impression via cookie_id
   - Adds conversion value ($10-$500)
3. Writes to HCD tables:
   - `impression_tracking` (raw events)
   - `impressions_by_minute` (bucketed)
   - `conversion_tracking` (raw events)
   - `conversions_by_minute` (bucketed)

**Batch Operations:**
- Uses `BatchStatement` for efficient writes
- Batch size: 100 records per batch
- Prepared statements for performance

**Configuration:**
```ini
[Service]
Environment=PATH=/root/affiliate-junction-demo/.venv/bin:...
Environment=VIRTUAL_ENV=/root/affiliate-junction-demo/.venv
WorkingDirectory=/root/affiliate-junction-demo
ExecStartPre=/bin/sleep 30  # Wait for HCD to be ready
ExecStart=.venv/bin/python generate_traffic.py
Restart=on-failure
```

**Monitoring:**
```bash
# View logs
journalctl -u generate_traffic -f

# Check last 20 entries
journalctl -u generate_traffic -n 20 --no-pager

# Verify data is being written
/opt/hcd-1.2.5/bin/cqlsh -e "SELECT COUNT(*) FROM affiliate_junction.impression_tracking"
```

**Key Metrics:**
- Impressions per cycle: ~3000
- Conversions per cycle: ~100
- Batch operations: ~30-50 per cycle
- Cycle time: 60 seconds

---

### 3. HCD to Presto Service (`hcd_to_presto.service`)

**Purpose:** ETL service that moves data from HCD operational tables to Presto Iceberg for analytics.

**Technology:** PySpark 3.5.0 with Cassandra and Iceberg connectors

**Script:** [`hcd_to_presto.py`](hcd_to_presto.py)

**Java Requirement:** Java 17 (required by PySpark)

**Data Flow:**
1. **Read from HCD:**
   - `impression_tracking` → Spark DataFrame
   - `conversion_tracking` → Spark DataFrame
   - Uses Cassandra Spark connector
   - Reads data from last 5 minutes

2. **Transform:**
   - Converts TIMEUUID to timestamp
   - Adds partition columns (hour, bucket)
   - Deduplicates records

3. **Write to Iceberg:**
   - `iceberg_data.affiliate_junction.impressions`
   - `iceberg_data.affiliate_junction.conversions`
   - Append mode (preserves history)
   - Partitioned by hour and publisher bucket

**Spark Configuration:**
```python
spark = SparkSession.builder \
    .appName("HCD to Presto ETL") \
    .config("spark.jars.packages", 
            "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0,"
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0") \
    .config("spark.sql.extensions", 
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.iceberg_data", 
            "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.iceberg_data.type", "hive") \
    .getOrCreate()
```

**Service Configuration:**
```ini
[Service]
Environment=JAVA_HOME=/usr/lib/jvm/java-17-openjdk-...
Environment=PATH=...
ExecStartPre=/bin/sleep 60  # Wait for data to accumulate
ExecStart=.venv/bin/python hcd_to_presto.py
Restart=on-failure
TimeoutStartSec=120  # PySpark startup can be slow
```

**Monitoring:**
```bash
# View logs
journalctl -u hcd_to_presto -f

# Check for errors
journalctl -u hcd_to_presto | grep -i error

# Verify data in Iceberg
kubectl exec -n wxd <presto-pod> -- presto-cli \
  --server https://localhost:8443 \
  --user ibmlhadmin \
  --execute "SELECT COUNT(*) FROM iceberg_data.affiliate_junction.impressions"
```

**Performance:**
- Processes ~3000 impressions per cycle
- Processes ~100 conversions per cycle
- Cycle time: ~60 seconds
- Spark overhead: ~10-15 seconds

**Common Issues:**
- **Java version:** Must use Java 17, not Java 11
- **Memory:** Requires 2-4GB for Spark
- **Connector versions:** Must match Spark version (3.5.0)

---

### 4. Presto to HCD Service (`presto_to_hcd.service`)

**Purpose:** ETL service that aggregates data from Presto Iceberg and writes summary tables back to HCD.

**Technology:** PySpark 3.5.0 with Iceberg and Cassandra connectors

**Script:** [`presto_to_hcd.py`](presto_to_hcd.py)

**Java Requirement:** Java 17 (required by PySpark)

**Data Flow:**
1. **Read from Iceberg:**
   - Query `iceberg_data.affiliate_junction.impressions`
   - Query `iceberg_data.affiliate_junction.conversions`
   - Aggregate by publisher and advertiser

2. **Aggregate:**
   - **Publishers:**
     - Total impressions
     - Total conversions
     - Conversion rate
     - Total revenue
     - Timeseries data (last 90 datapoints)
   - **Advertisers:**
     - Total impressions
     - Total conversions
     - Conversion rate
     - Total spend
     - Timeseries data (last 90 datapoints)

3. **Write to HCD:**
   - `affiliate_junction.publishers` (no TTL)
   - `affiliate_junction.advertisers` (no TTL)
   - Upsert mode (updates existing records)

**Aggregation Logic:**
```python
# Publisher aggregation
publishers_df = impressions_df.groupBy("publishers_id").agg(
    count("*").alias("total_impressions"),
    countDistinct("cookie_id").alias("unique_visitors")
).join(
    conversions_df.groupBy("publishers_id").agg(
        count("*").alias("total_conversions"),
        sum("conversion_value").alias("total_revenue")
    ),
    on="publishers_id",
    how="left"
)
```

**Timeseries Format:**
```json
[
  [1714636800000, 1234],  // [timestamp_ms, value]
  [1714636860000, 1456],
  ...
]
```

**Service Configuration:**
```ini
[Service]
Environment=JAVA_HOME=/usr/lib/jvm/java-17-openjdk-...
ExecStart=.venv/bin/python presto_to_hcd.py
Restart=on-failure
```

**Monitoring:**
```bash
# View logs
journalctl -u presto_to_hcd -f

# Verify aggregated data
/opt/hcd-1.2.5/bin/cqlsh -e "SELECT * FROM affiliate_junction.publishers LIMIT 5"
/opt/hcd-1.2.5/bin/cqlsh -e "SELECT * FROM affiliate_junction.advertisers LIMIT 5"
```

**Key Metrics:**
- Processes 50 publishers per cycle
- Processes 10 advertisers per cycle
- Cycle time: ~60 seconds
- Timeseries: 90 datapoints per entity

---

### 5. Presto Insights Service (`presto_insights.service`)

**Purpose:** Runs analytical queries on Iceberg data to generate insights and detect anomalies.

**Technology:** Python 3.9 with Presto Python client

**Script:** [`presto_insights.py`](presto_insights.py)

**Queries Executed:**
1. **Top Publishers by Revenue:**
   ```sql
   SELECT publishers_id, SUM(conversion_value) as revenue
   FROM iceberg_data.affiliate_junction.conversions
   GROUP BY publishers_id
   ORDER BY revenue DESC
   LIMIT 10
   ```

2. **Conversion Rate by Hour:**
   ```sql
   SELECT hour(timestamp) as hour,
          COUNT(DISTINCT i.cookie_id) as impressions,
          COUNT(DISTINCT c.cookie_id) as conversions,
          CAST(COUNT(DISTINCT c.cookie_id) AS DOUBLE) / 
          COUNT(DISTINCT i.cookie_id) * 100 as conversion_rate
   FROM iceberg_data.affiliate_junction.impressions i
   LEFT JOIN iceberg_data.affiliate_junction.conversions c
     ON i.cookie_id = c.cookie_id
   GROUP BY hour(timestamp)
   ```

3. **Fraud Detection:**
   ```sql
   SELECT publishers_id, COUNT(*) as suspicious_conversions
   FROM iceberg_data.affiliate_junction.conversions
   WHERE conversion_value > 1000  -- Unusually high value
   GROUP BY publishers_id
   HAVING COUNT(*) > 10
   ```

**Service Configuration:**
```ini
[Service]
Environment=PATH=/root/affiliate-junction-demo/.venv/bin:...
ExecStart=.venv/bin/python presto_insights.py
Restart=on-failure
```

**Output:**
- Logs insights to systemd journal
- Can be extended to write to database or send alerts

**Monitoring:**
```bash
# View insights
journalctl -u presto_insights -f

# Check last insights
journalctl -u presto_insights -n 50 --no-pager
```

---

### 6. Presto Cleanup Service (`presto_cleanup.service`)

**Purpose:** Manages data lifecycle by removing old data from Iceberg tables.

**Technology:** Python 3.9 with Presto Python client

**Script:** [`presto_cleanup.py`](presto_cleanup.py)

**Cleanup Logic:**
1. **Delete old impressions:**
   ```sql
   DELETE FROM iceberg_data.affiliate_junction.impressions
   WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '7' DAY
   ```

2. **Delete old conversions:**
   ```sql
   DELETE FROM iceberg_data.affiliate_junction.conversions
   WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '7' DAY
   ```

3. **Compact tables:**
   ```sql
   ALTER TABLE iceberg_data.affiliate_junction.impressions
   EXECUTE optimize
   ```

**Service Configuration:**
```ini
[Service]
Environment=PATH=/root/affiliate-junction-demo/.venv/bin:...
ExecStart=.venv/bin/python presto_cleanup.py
Restart=on-failure
```

**Monitoring:**
```bash
# View cleanup logs
journalctl -u presto_cleanup -f

# Check table sizes
kubectl exec -n wxd <presto-pod> -- presto-cli \
  --server https://localhost:8443 \
  --user ibmlhadmin \
  --execute "SELECT COUNT(*) FROM iceberg_data.affiliate_junction.impressions"
```

**Retention Policy:**
- Impressions: 7 days
- Conversions: 7 days
- Cleanup runs: Every 24 hours

---

### 7. Uvicorn Service (`uvicorn.service`)

**Purpose:** Serves the Affiliate Junction web UI using FastAPI.

**Technology:** FastAPI + Uvicorn + Jinja2 templates

**Script:** [`web/main.py`](web/main.py)

**Features:**
- **Publisher Dashboard:** View publisher metrics and charts
- **Advertiser Dashboard:** View advertiser metrics and charts
- **Fraud Dashboard:** Detect and visualize suspicious activity
- **Query Panel:** Real-time database query monitoring
- **Responsive UI:** Works on desktop and mobile

**Endpoints:**
- `/` - Login page
- `/index` - Main dashboard
- `/publisher/<id>` - Publisher details
- `/advertiser/<id>` - Advertiser details
- `/fraud` - Fraud detection dashboard

**Service Configuration:**
```ini
[Service]
Environment=PATH=/root/affiliate-junction-demo/.venv/bin:...
ExecStart=.venv/bin/uvicorn web.main:app --reload --host 0.0.0.0 --port 10000
Restart=on-failure
```

**Access:**
```
http://<VM_IP>:10000
```

**Monitoring:**
```bash
# View logs
journalctl -u uvicorn -f

# Check if running
curl -I http://localhost:10000

# Restart
systemctl restart uvicorn
```

---

## Data Flow

### Complete Pipeline

```
1. generate_traffic.py
   ↓ Writes to HCD
   - impression_tracking (TTL: 5 min)
   - conversion_tracking (TTL: 5 min)

2. hcd_to_presto.py (PySpark)
   ↓ Reads from HCD, writes to Iceberg
   - iceberg_data.affiliate_junction.impressions
   - iceberg_data.affiliate_junction.conversions

3. presto_to_hcd.py (PySpark)
   ↓ Aggregates Iceberg, writes to HCD
   - affiliate_junction.publishers (no TTL)
   - affiliate_junction.advertisers (no TTL)

4. web/main.py (FastAPI)
   ↓ Reads from HCD
   - Displays publishers and advertisers
   - Shows metrics and charts

5. presto_insights.py
   ↓ Analyzes Iceberg data
   - Generates insights
   - Detects anomalies

6. presto_cleanup.py
   ↓ Manages Iceberg data
   - Deletes old data
   - Compacts tables
```

### Data Lifecycle

| Stage | Storage | TTL | Purpose |
|-------|---------|-----|---------|
| Raw Events | HCD operational tables | 5-10 min | Real-time ingestion |
| Historical | Iceberg tables | 7 days | Analytics |
| Aggregated | HCD summary tables | None | Web UI display |

---

## Troubleshooting

### All Services

```bash
# Check all service statuses
for service in hcd generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn; do
    echo "=== $service ==="
    systemctl is-active $service
done

# View all logs
journalctl -u hcd -u generate_traffic -u hcd_to_presto -u presto_to_hcd -u uvicorn -f
```

### Service Won't Start

```bash
# Check service status
systemctl status <service-name>

# View detailed logs
journalctl -u <service-name> -n 100 --no-pager

# Check for port conflicts
lsof -i :<port>

# Restart service
systemctl restart <service-name>
```

### Java Version Issues

```bash
# Check Java versions
alternatives --display java

# For HCD (needs Java 11)
systemctl show hcd | grep Environment

# For PySpark services (need Java 17)
systemctl show hcd_to_presto | grep Environment
```

### Data Not Flowing

```bash
# 1. Check HCD has data
/opt/hcd-1.2.5/bin/cqlsh -e "SELECT COUNT(*) FROM affiliate_junction.impression_tracking"

# 2. Check Iceberg has data
kubectl exec -n wxd <presto-pod> -- presto-cli \
  --server https://localhost:8443 \
  --user ibmlhadmin \
  --execute "SELECT COUNT(*) FROM iceberg_data.affiliate_junction.impressions"

# 3. Check aggregated data
/opt/hcd-1.2.5/bin/cqlsh -e "SELECT COUNT(*) FROM affiliate_junction.publishers"

# 4. Check service logs for errors
journalctl -u hcd_to_presto | grep -i error
journalctl -u presto_to_hcd | grep -i error
```

### Performance Issues

```bash
# Check system resources
top
free -h
df -h

# Check service resource usage
systemctl status <service-name>

# Increase service timeout if needed
systemctl edit <service-name>
# Add: TimeoutStartSec=300
```

---

## Service Management

### Start All Services

```bash
systemctl start hcd
sleep 30
systemctl start generate_traffic
sleep 60
systemctl start hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn
```

### Stop All Services

```bash
systemctl stop uvicorn presto_cleanup presto_insights presto_to_hcd hcd_to_presto generate_traffic hcd
```

### Restart All Services

```bash
systemctl restart hcd
sleep 30
systemctl restart generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn
```

### Enable/Disable Auto-start

```bash
# Enable
systemctl enable <service-name>

# Disable
systemctl disable <service-name>
```

---

## Additional Resources

- **Main Documentation:** [README.md](README.md)
- **Deployment Guide:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Demo Script:** [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- **Developer Guide:** [DEVELOPER.md](DEVELOPER.md)