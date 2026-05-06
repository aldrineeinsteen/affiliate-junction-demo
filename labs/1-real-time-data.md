# Lab 1: Real-Time Data Ingestion

**Duration:** 30-40 minutes  
**Difficulty:** Beginner  
**Environment:** watsonx.data Query Workspace

---

## Lab Overview

In this lab, you will create your own real-time data tracking system alongside the existing Affiliate Junction demo. You'll learn how to:

1. Create operational tables in HCD (Cassandra) with TTL
2. Insert data using SQL through watsonx.data Query Workspace
3. Write a Python script to simulate continuous data ingestion
4. Monitor your data flowing through the system in real-time

**What You'll Build:**
A user activity tracking system that captures page views, clicks, and session data with automatic expiration.

---

## Prerequisites

✅ Access to watsonx.data UI at `https://<hostname>:9443`  
✅ Login credentials: `ibmadmin` / `password`  
✅ HCD catalog configured in watsonx.data  
✅ Basic understanding of SQL

---

## Part 1: Understanding the Existing System (5 minutes)

### Step 1: Access watsonx.data Query Workspace

1. Open browser and navigate to: `https://<hostname>:9443`
2. Login with `ibmadmin` / `password`
3. Click on **"Query workspace"** tab in the top navigation

**What is Query Workspace?**
The Query Workspace is watsonx.data's SQL interface where you can:
- Write and execute SQL queries
- Browse catalogs and tables
- View query results
- Access both HCD (operational) and Iceberg (analytical) data

### Step 2: Explore Existing Tables

In the left sidebar, you'll see the catalog browser. Expand:

```
📁 hcd (Cassandra catalog)
  └── 📁 affiliate_junction (keyspace)
      ├── 📄 impression_tracking
      ├── 📄 conversion_tracking
      ├── 📄 impressions_by_minute
      ├── 📄 conversions_by_minute
      ├── 📄 publishers
      ├── 📄 advertisers
      └── 📄 services
```

**Execute this query to see live data:**

```sql
SELECT * FROM hcd.affiliate_junction.impression_tracking LIMIT 10;
```

**What You're Seeing:**
- Real-time impression data from the traffic generator
- Data is only 5 minutes old (TTL = 300 seconds)
- Thousands of records flowing through continuously

---

## Part 2: Create Your Own Tracking Table (10 minutes)

### Step 3: Design Your Table Schema

You'll create a `user_activity_tracking` table to track user sessions on a website.

**Table Design:**
- **user_id**: Unique identifier for each user
- **session_id**: Unique session identifier
- **page_url**: Page being viewed
- **action_type**: Type of action (view, click, scroll, etc.)
- **timestamp**: When the action occurred
- **metadata**: Additional JSON data

**Why This Design?**
- **Partition Key**: `(user_id, session_id)` - Groups all actions for a user session together
- **Clustering Key**: `timestamp DESC` - Orders actions chronologically within a session
- **TTL**: 600 seconds (10 minutes) - Automatically expires old data

### Step 4: Create the Table

**Copy and execute this SQL in Query Workspace:**

```sql
CREATE TABLE IF NOT EXISTS hcd.affiliate_junction.user_activity_tracking (
    user_id VARCHAR,
    session_id VARCHAR,
    page_url VARCHAR,
    action_type VARCHAR,
    timestamp TIMESTAMP,
    metadata VARCHAR,
    PRIMARY KEY ((user_id, session_id), timestamp)
) WITH (
    clustering_order_by = 'timestamp DESC',
    default_time_to_live = 600,
    gc_grace_seconds = 0
);
```

**Understanding Each Part:**

**`CREATE TABLE IF NOT EXISTS`**
- Creates table only if it doesn't already exist
- Safe to run multiple times

**`hcd.affiliate_junction.user_activity_tracking`**
- `hcd` = Catalog name (HCD/Cassandra)
- `affiliate_junction` = Keyspace (like a database schema)
- `user_activity_tracking` = Table name

**`PRIMARY KEY ((user_id, session_id), timestamp)`**
- `(user_id, session_id)` = **Partition Key** - Determines which node stores the data
- `timestamp` = **Clustering Key** - Orders data within the partition

**`clustering_order_by = 'timestamp DESC'`**
- Stores newest records first
- Efficient for "recent activity" queries

**`default_time_to_live = 600`**
- Data automatically expires after 600 seconds (10 minutes)
- No manual cleanup needed
- Perfect for operational/real-time data

**`gc_grace_seconds = 0`**
- Tombstones (deletion markers) removed immediately
- Safe because we're using TTL (no manual deletes)

**Expected Output:**
```
Query successful
```

### Step 5: Verify Table Creation

```sql
DESCRIBE TABLE hcd.affiliate_junction.user_activity_tracking;
```

**Expected Output:**
You'll see the complete table definition including all columns and properties.

---

## Part 3: Insert Sample Data (10 minutes)

### Step 6: Insert Your First Record

**Execute this INSERT statement:**

```sql
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
(user_id, session_id, page_url, action_type, timestamp, metadata)
VALUES (
    'user_001',
    'session_' || CAST(FLOOR(RANDOM() * 10000) AS VARCHAR),
    '/products/laptop',
    'page_view',
    CURRENT_TIMESTAMP,
    '{"device": "desktop", "browser": "chrome"}'
);
```

**Understanding the INSERT:**

**`INSERT INTO ... VALUES`**
- Standard SQL insert syntax
- Inserts one row at a time

**`'session_' || CAST(FLOOR(RANDOM() * 10000) AS VARCHAR)`**
- Generates random session ID like "session_4523"
- `RANDOM()` = Random number between 0 and 1
- `FLOOR(RANDOM() * 10000)` = Random integer 0-9999
- `||` = String concatenation operator

**`CURRENT_TIMESTAMP`**
- Built-in function that returns current time
- Automatically uses server time

**`'{"device": "desktop", "browser": "chrome"}'`**
- JSON string stored as VARCHAR
- Can store any additional metadata

**Expected Output:**
```
1 row inserted
```

### Step 7: Query Your Data

```sql
SELECT * FROM hcd.affiliate_junction.user_activity_tracking 
WHERE user_id = 'user_001'
LIMIT 10;
```

**Expected Output:**
You should see the record you just inserted.

### Step 8: Insert Multiple Records

**Execute this to insert 5 different actions:**

```sql
-- Page view
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
VALUES ('user_001', 'session_1001', '/home', 'page_view', CURRENT_TIMESTAMP, '{"referrer": "google"}');

-- Click action
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
VALUES ('user_001', 'session_1001', '/products', 'click', CURRENT_TIMESTAMP, '{"element": "nav_menu"}');

-- Scroll action
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
VALUES ('user_001', 'session_1001', '/products', 'scroll', CURRENT_TIMESTAMP, '{"depth": "75%"}');

-- Add to cart
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
VALUES ('user_001', 'session_1001', '/products/laptop', 'add_to_cart', CURRENT_TIMESTAMP, '{"product_id": "LAP123"}');

-- Purchase
INSERT INTO hcd.affiliate_junction.user_activity_tracking 
VALUES ('user_001', 'session_1001', '/checkout', 'purchase', CURRENT_TIMESTAMP, '{"amount": 999.99}');
```

**Query to see the session timeline:**

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

**What You're Seeing:**
- Complete user journey through your website
- Actions ordered chronologically (newest first)
- All data for one session grouped together

---

## Part 4: Simulate Continuous Data Flow (10 minutes)

### Step 9: Create a Data Generation Script

Now let's create a Python script that continuously inserts data, simulating real-time traffic.

**SSH to your VM:**

```bash
ssh -p <port> watsonx@<hostname>
```

**Create the script:**

```bash
cat > ~/user_activity_generator.py << 'EOF'
#!/usr/bin/env python3
"""
User Activity Generator
Simulates continuous user activity data insertion into HCD
"""

import time
import random
from datetime import datetime
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Configuration
HCD_HOST = 'localhost'
HCD_PORT = 9042
KEYSPACE = 'affiliate_junction'
TABLE = 'user_activity_tracking'

# Sample data for realistic simulation
USERS = [f'user_{str(i).zfill(3)}' for i in range(1, 51)]  # 50 users
PAGES = [
    '/home', '/products', '/products/laptop', '/products/phone',
    '/products/tablet', '/cart', '/checkout', '/account', '/support'
]
ACTIONS = ['page_view', 'click', 'scroll', 'add_to_cart', 'remove_from_cart', 'purchase']
DEVICES = ['desktop', 'mobile', 'tablet']
BROWSERS = ['chrome', 'firefox', 'safari', 'edge']

def connect_to_hcd():
    """Connect to HCD (Cassandra)"""
    print(f"Connecting to HCD at {HCD_HOST}:{HCD_PORT}...")
    cluster = Cluster([HCD_HOST], port=HCD_PORT)
    session = cluster.connect(KEYSPACE)
    print(f"Connected to keyspace: {KEYSPACE}")
    return cluster, session

def prepare_insert_statement(session):
    """Prepare INSERT statement for better performance"""
    query = f"""
        INSERT INTO {TABLE} 
        (user_id, session_id, page_url, action_type, timestamp, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    return session.prepare(query)

def generate_activity():
    """Generate random user activity data"""
    user_id = random.choice(USERS)
    session_id = f"session_{random.randint(1000, 9999)}"
    page_url = random.choice(PAGES)
    action_type = random.choice(ACTIONS)
    timestamp = datetime.now()
    
    # Generate realistic metadata
    metadata = {
        'device': random.choice(DEVICES),
        'browser': random.choice(BROWSERS),
        'duration_ms': random.randint(100, 5000)
    }
    
    return (user_id, session_id, page_url, action_type, timestamp, str(metadata))

def main():
    """Main execution loop"""
    print("=" * 60)
    print("User Activity Generator")
    print("=" * 60)
    
    # Connect to HCD
    cluster, session = connect_to_hcd()
    
    # Prepare statement
    prepared_stmt = prepare_insert_statement(session)
    
    print(f"\nGenerating user activity data...")
    print(f"Target: ~10 activities per second")
    print(f"Press Ctrl+C to stop\n")
    
    count = 0
    start_time = time.time()
    
    try:
        while True:
            # Generate and insert activity
            activity_data = generate_activity()
            session.execute(prepared_stmt, activity_data)
            
            count += 1
            
            # Print progress every 10 records
            if count % 10 == 0:
                elapsed = time.time() - start_time
                rate = count / elapsed if elapsed > 0 else 0
                print(f"Inserted {count} activities | Rate: {rate:.1f}/sec | "
                      f"Latest: {activity_data[0]} - {activity_data[3]}")
            
            # Sleep to control rate (~10 per second)
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print(f"\n\nStopping generator...")
        print(f"Total activities inserted: {count}")
        print(f"Total time: {time.time() - start_time:.1f} seconds")
    
    finally:
        session.shutdown()
        cluster.shutdown()
        print("Disconnected from HCD")

if __name__ == "__main__":
    main()
EOF

chmod +x ~/user_activity_generator.py
```

**Understanding the Script:**

**Connection Setup:**
```python
cluster = Cluster([HCD_HOST], port=HCD_PORT)
session = cluster.connect(KEYSPACE)
```
- Uses existing `cassandra-driver` library (already installed)
- Connects to local HCD instance
- Reuses connection for all inserts (efficient)

**Prepared Statements:**
```python
prepared_stmt = session.prepare(query)
```
- Compiles query once, executes many times
- Much faster than parsing query each time
- Best practice for high-throughput inserts

**Data Generation:**
```python
user_id = random.choice(USERS)
```
- Randomly selects from predefined lists
- Creates realistic patterns
- Simulates 50 concurrent users

**Rate Control:**
```python
time.sleep(0.1)  # 100ms delay = ~10 inserts/sec
```
- Controls insertion rate
- Prevents overwhelming the system
- Adjust for different throughput

### Step 10: Run the Generator

```bash
python3 ~/user_activity_generator.py
```

**Expected Output:**
```
============================================================
User Activity Generator
============================================================
Connecting to HCD at localhost:9042...
Connected to keyspace: affiliate_junction

Generating user activity data...
Target: ~10 activities per second
Press Ctrl+C to stop

Inserted 10 activities | Rate: 10.2/sec | Latest: user_023 - click
Inserted 20 activities | Rate: 10.1/sec | Latest: user_045 - page_view
Inserted 30 activities | Rate: 10.0/sec | Latest: user_012 - scroll
...
```

**Let it run for 1-2 minutes, then press Ctrl+C to stop.**

---

## Part 5: Monitor Your Data (5 minutes)

### Step 11: Query Real-Time Statistics

While the generator is running (or after), execute these queries in Query Workspace:

**Count total activities:**

```sql
SELECT COUNT(*) as total_activities
FROM hcd.affiliate_junction.user_activity_tracking;
```

**Top active users:**

```sql
SELECT 
    user_id,
    COUNT(*) as activity_count,
    COUNT(DISTINCT session_id) as session_count
FROM hcd.affiliate_junction.user_activity_tracking
GROUP BY user_id
ORDER BY activity_count DESC
LIMIT 10;
```

**Activity breakdown by type:**

```sql
SELECT 
    action_type,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM hcd.affiliate_junction.user_activity_tracking
GROUP BY action_type
ORDER BY count DESC;
```

**Recent activity timeline:**

```sql
SELECT 
    user_id,
    session_id,
    action_type,
    page_url,
    timestamp
FROM hcd.affiliate_junction.user_activity_tracking
ORDER BY timestamp DESC
LIMIT 20;
```

### Step 12: Observe TTL Expiration

Your data has a 10-minute TTL. Let's observe it expiring:

**Check current count:**

```sql
SELECT COUNT(*) as current_count
FROM hcd.affiliate_junction.user_activity_tracking;
```

**Wait 5 minutes and check again:**

```sql
SELECT COUNT(*) as current_count
FROM hcd.affiliate_junction.user_activity_tracking;
```

**Wait another 5 minutes (total 10 minutes):**

```sql
SELECT COUNT(*) as current_count
FROM hcd.affiliate_junction.user_activity_tracking;
```

**What You Should See:**
- Count decreases as old data expires
- If generator is stopped, count eventually reaches 0
- If generator is running, count stabilizes (new data = expired data)

**This demonstrates:**
- Automatic data lifecycle management
- No manual cleanup required
- Perfect for operational/real-time data

---

## Lab Summary

### What You've Accomplished

✅ **Created** a custom operational table in HCD with TTL  
✅ **Inserted** data using SQL through Query Workspace  
✅ **Wrote** a Python script for continuous data generation  
✅ **Monitored** real-time data flow and statistics  
✅ **Observed** automatic TTL-based data expiration  

### Key Concepts Learned

**1. Partition Keys**
- Determine data distribution across nodes
- Group related data together
- Critical for query performance

**2. Clustering Keys**
- Order data within partitions
- Enable efficient range queries
- Support time-series patterns

**3. TTL (Time To Live)**
- Automatic data expiration
- No manual cleanup needed
- Perfect for operational data

**4. Prepared Statements**
- Compile once, execute many times
- Significantly faster for repeated queries
- Best practice for high throughput

**5. Real-Time Patterns**
- Continuous data ingestion
- Low-latency writes (<10ms)
- Scalable architecture

### Your Data Pipeline

```
Python Script → HCD Table → Automatic Expiration
     ↓              ↓              ↓
  10/sec      Real-time      After 10 min
             Queries
```

---

## Next Steps

Continue to **[Lab 2: Operational Data in HCD](2-operational-data.md)** where you'll:
- Write advanced queries with partitioning
- Explore bucketing strategies
- Understand consistency levels
- Monitor write throughput

---

## Troubleshooting

### Table Creation Failed

**Error:** `Keyspace affiliate_junction does not exist`

**Solution:**
```sql
CREATE KEYSPACE IF NOT EXISTS affiliate_junction
WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1};
```

### Python Script Connection Error

**Error:** `NoHostAvailable: Unable to connect to any servers`

**Check HCD is running:**
```bash
systemctl status hcd
```

**Verify port:**
```bash
netstat -an | grep 9042
```

### No Data Showing

**Possible causes:**
1. Data expired (TTL = 10 minutes)
2. Wrong table name
3. Generator not running

**Verify:**
```sql
SELECT COUNT(*) FROM hcd.affiliate_junction.user_activity_tracking;
```

---

## Additional Resources

- [HCD Schema Design](../hcd_schema.cql) - Complete schema reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [Cassandra Documentation](https://cassandra.apache.org/doc/latest/) - Official docs

---

**Lab 1 Complete!** ✅

You've successfully created a real-time data ingestion pipeline. Continue to Lab 2 to explore advanced operational queries.