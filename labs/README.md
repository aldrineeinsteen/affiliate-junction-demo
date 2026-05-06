# Affiliate Junction - Self-Guided Labs

**Complete hands-on workshop for watsonx.data federated architecture**

---

## Overview

These self-guided labs provide hands-on experience with watsonx.data's federated architecture through a real-world affiliate marketing use case. Each lab builds progressively, teaching you to create, query, and analyze data across operational and analytical systems.

**Total Duration:** 2.5 - 3 hours  
**Difficulty:** Beginner to Advanced  
**Format:** Self-paced, hands-on exercises

---

## Prerequisites

Before starting these labs, ensure you have:

✅ **Working Environment:**
- VM with watsonx.data Developer Edition (Kubernetes-based)
- HCD (IBM Cassandra) installed and running
- Affiliate Junction application deployed
- All services running (verify with `systemctl status`)

✅ **Access:**
- watsonx.data UI: `https://<hostname>:9443` (Login: `ibmadmin` / `password`)
- Affiliate Junction WUI: `http://<hostname>:10000` (Login: `watsonx` / `watsonx.data`)
- SSH access to VM

✅ **Knowledge:**
- Basic SQL
- Basic Python (for Lab 1 & 3)
- Understanding of databases

---

## Lab Structure

### [Lab 1: Real-Time Data Ingestion](1-real-time-data.md)
**Duration:** 30-40 minutes | **Difficulty:** Beginner

**What You'll Build:**
- Custom operational table in HCD with TTL
- Python script for continuous data generation
- Real-time monitoring dashboard

**Key Concepts:**
- Partition keys and clustering keys
- TTL-based data lifecycle
- High-velocity writes
- Prepared statements

**Hands-On Activities:**
1. ✅ CREATE custom tracking table
2. ✅ INSERT data via SQL
3. ✅ WRITE Python data generator
4. ✅ MONITOR real-time data flow
5. ✅ OBSERVE TTL expiration

---

### [Lab 2: Operational Data in HCD](2-operational-data.md)
**Duration:** 30-40 minutes | **Difficulty:** Intermediate

**What You'll Learn:**
- Efficient partition-targeted queries
- Bucketing strategies for high-volume data
- Pre-computed statistics patterns
- Performance best practices

**Key Concepts:**
- Partition-based querying
- Time-based bucketing
- ALLOW FILTERING (when and why)
- Batch operations

**Hands-On Activities:**
1. ✅ WRITE efficient partition queries
2. ✅ EXPLORE bucketing strategies
3. ✅ CREATE statistics tables
4. ✅ USE advanced CQL features
5. ✅ MONITOR performance

---

### [Lab 3: Transformation (ETL)](3-transformation-etl.md)
**Duration:** 40-50 minutes | **Difficulty:** Intermediate to Advanced

**What You'll Build:**
- Iceberg tables for analytics
- PySpark ETL script
- Continuous ETL service

**Key Concepts:**
- Extract, Transform, Load pattern
- Iceberg table format
- PySpark transformations
- Aggregations and enrichment

**Hands-On Activities:**
1. ✅ CREATE Iceberg analytics tables
2. ✅ WRITE PySpark ETL script
3. ✅ IMPLEMENT aggregations
4. ✅ RUN ETL pipeline
5. ✅ VERIFY data in Iceberg

---

### [Lab 4: Query Federation](4-query-federation.md)
**Duration:** 40-50 minutes | **Difficulty:** Intermediate to Advanced

**What You'll Master:**
- Federated queries across HCD and Iceberg
- Cross-catalog joins
- CSV data import and integration
- Complete multi-source analytics

**Key Concepts:**
- Query federation
- Cross-catalog joins
- External tables
- Multi-source analytics

**Hands-On Activities:**
1. ✅ EXECUTE federated queries
2. ✅ JOIN operational + analytical data
3. ✅ IMPORT CSV reference data
4. ✅ BUILD three-way federated queries
5. ✅ CREATE user segmentation

---

## Learning Path

### Progressive Complexity

```
Lab 1: Real-Time Data
    ↓
  CREATE operational table
  INSERT data
  MONITOR flow
    ↓
Lab 2: Operational Queries
    ↓
  QUERY efficiently
  UNDERSTAND partitioning
  OPTIMIZE performance
    ↓
Lab 3: ETL Pipeline
    ↓
  CREATE analytical tables
  TRANSFORM data
  LOAD to Iceberg
    ↓
Lab 4: Federation
    ↓
  QUERY across systems
  JOIN multiple sources
  COMPLETE analytics
```

### What You'll Have Built

By completing all labs, you will have created:

1. ✅ **Operational Layer (HCD)**
   - `user_activity_tracking` table
   - `user_activity_by_minute` bucketed table
   - `user_activity_stats` statistics table
   - Python data generator script

2. ✅ **Analytical Layer (Iceberg)**
   - `user_activity_analytics` session table
   - `user_activity_hourly` summary table
   - `user_profiles` reference table

3. ✅ **ETL Pipeline**
   - PySpark transformation script
   - Continuous ETL service
   - Aggregation logic

4. ✅ **Federated Queries**
   - Cross-catalog joins
   - Multi-source analytics
   - Complete user profiles

---

## Quick Start

### Option 1: Complete All Labs (Recommended)

Follow labs in order for full learning experience:

```bash
# Start with Lab 1
cd labs
cat 1-real-time-data.md

# Progress through each lab
# Lab 1 → Lab 2 → Lab 3 → Lab 4
```

### Option 2: Jump to Specific Topic

Each lab is self-contained with prerequisites listed:

- **Want to learn data ingestion?** → Start with Lab 1
- **Need to optimize queries?** → Jump to Lab 2
- **Building ETL pipelines?** → Go to Lab 3
- **Exploring federation?** → Try Lab 4

### Option 3: Quick Demo (1 hour)

For a quick overview:

1. **Lab 1** - Create table and insert data (15 min)
2. **Lab 2** - Run a few queries (15 min)
3. **Lab 3** - Execute pre-built ETL (15 min)
4. **Lab 4** - Try federated queries (15 min)

---

## Lab Format

Each lab follows this structure:

### 1. Overview
- What you'll learn
- What you'll build
- Time estimate

### 2. Prerequisites
- Required setup
- Access credentials
- Knowledge needed

### 3. Hands-On Steps
- Step-by-step instructions
- Complete code examples
- Detailed explanations

### 4. Understanding Results
- What to expect
- How to interpret output
- Key takeaways

### 5. Troubleshooting
- Common issues
- Solutions
- Debugging tips

### 6. Summary
- What you accomplished
- Key concepts learned
- Next steps

---

## Teaching Approach

### Explain Everything

Every command and concept is explained:

```sql
CREATE TABLE user_activity (
    user_id VARCHAR,           -- Unique user identifier
    session_id VARCHAR,        -- Session identifier
    PRIMARY KEY (user_id)      -- Partition key for distribution
) WITH (
    default_time_to_live = 600 -- Data expires after 10 minutes
);
```

### Use Existing Functions

Labs leverage existing demo infrastructure:

- ✅ Reuse database connections
- ✅ Follow established patterns
- ✅ Use existing services as examples
- ✅ Build alongside demo data

### Query Workspace Focus

All SQL executed in watsonx.data Query Workspace:

- ✅ No command-line complexity
- ✅ Visual query interface
- ✅ Immediate results
- ✅ Easy to follow

---

## Support Resources

### Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [FEDERATED_QUERIES.md](../FEDERATED_QUERIES.md) - 15+ query examples
- [SERVICES.md](../SERVICES.md) - Service documentation
- [DEMO_SCRIPT.md](../DEMO_SCRIPT.md) - Demo walkthrough

### Sample Data

- [workshop_data/](../workshop_data/) - CSV files for import
- [hcd_schema.cql](../hcd_schema.cql) - HCD schema reference
- [presto_schema.sql](../presto_schema.sql) - Iceberg schema reference

### Code Examples

- [generate_traffic.py](../generate_traffic.py) - Traffic generator
- [hcd_to_presto.py](../hcd_to_presto.py) - ETL example
- [presto_to_hcd.py](../presto_to_hcd.py) - Reverse ETL

---

## Tips for Success

### 1. Follow the Order

Labs build on each other:
- Lab 1 creates data used in Lab 2
- Lab 2 queries data transformed in Lab 3
- Lab 3 creates tables queried in Lab 4

### 2. Read Explanations

Don't just copy-paste:
- Understand WHY, not just HOW
- Read the "Understanding" sections
- Experiment with variations

### 3. Check Prerequisites

Before each lab:
- Verify services running
- Confirm access to UIs
- Test SSH connection

### 4. Save Your Work

Keep your scripts:
```bash
# Create personal directory
mkdir ~/my-labs
cp ~/user_activity_generator.py ~/my-labs/
cp ~/user_activity_etl.py ~/my-labs/
```

### 5. Experiment

After completing labs:
- Modify queries
- Try different parameters
- Create your own tables
- Build custom analytics

---

## Common Issues

### Services Not Running

```bash
# Check all services
systemctl status hcd
systemctl status generate_traffic
systemctl status uvicorn

# Restart if needed
sudo systemctl restart <service-name>
```

### Can't Access UI

1. Verify port forwarding (if needed)
2. Check firewall rules
3. Confirm service is running
4. Try different browser

### Data Not Showing

1. Check if generator is running
2. Verify TTL hasn't expired
3. Confirm correct table name
4. Query with COUNT(*) first

### Query Errors

1. Check catalog name (hcd vs iceberg_data)
2. Verify table exists (SHOW TABLES)
3. Review error message carefully
4. Check syntax in examples

---

## Feedback and Improvements

Found an issue or have suggestions?

1. Check troubleshooting sections
2. Review documentation
3. Verify prerequisites
4. Contact workshop organizer

---

## Next Steps After Labs

### Explore More

1. **Try Advanced Queries**
   - See [FEDERATED_QUERIES.md](../FEDERATED_QUERIES.md)
   - Experiment with window functions
   - Build complex analytics

2. **Customize the Demo**
   - Add your own tables
   - Create custom dashboards
   - Implement new features

3. **Learn More About**
   - [watsonx.data](https://www.ibm.com/docs/en/watsonxdata)
   - [Apache Iceberg](https://iceberg.apache.org/)
   - [Presto](https://prestodb.io/)
   - [Cassandra](https://cassandra.apache.org/)

4. **Build Your Own**
   - Design your use case
   - Implement data pipeline
   - Create analytics queries
   - Share with community

---

## Lab Completion Checklist

Track your progress:

- [ ] Lab 1: Real-Time Data Ingestion
  - [ ] Created user_activity_tracking table
  - [ ] Wrote Python generator script
  - [ ] Observed TTL expiration
  
- [ ] Lab 2: Operational Data in HCD
  - [ ] Wrote partition-targeted queries
  - [ ] Created bucketed table
  - [ ] Used advanced CQL features
  
- [ ] Lab 3: Transformation (ETL)
  - [ ] Created Iceberg analytics tables
  - [ ] Wrote PySpark ETL script
  - [ ] Ran successful ETL
  
- [ ] Lab 4: Query Federation
  - [ ] Executed federated queries
  - [ ] Imported CSV data
  - [ ] Built three-way joins

---

**Ready to start? Begin with [Lab 1: Real-Time Data Ingestion](1-real-time-data.md)**

Good luck and enjoy the labs! 🚀