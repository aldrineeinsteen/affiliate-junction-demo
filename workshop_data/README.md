# Workshop Data Files

This directory contains sample CSV files for use in the Affiliate Junction workshop, specifically for Lab 4B: Advanced Federated Queries & CSV Data Import.

## Files

### publisher_metadata.csv
Publisher reference data including:
- `publisher_id`: Unique publisher identifier
- `publisher_name`: Publisher display name
- `category`: Content category (Technology, Fashion, Gaming, etc.)
- `country`: Publisher's primary country
- `tier`: Publisher tier (Premium, Standard)
- `commission_rate`: Commission rate as decimal (e.g., 0.15 = 15%)

**Use Case:** Enrich operational impression data with publisher metadata for business intelligence queries.

### advertiser_metadata.csv
Advertiser reference data including:
- `advertiser_id`: Unique advertiser identifier
- `advertiser_name`: Advertiser display name
- `industry`: Industry vertical
- `budget_tier`: Budget classification (High, Medium, Low)
- `target_cpa`: Target cost per acquisition in dollars
- `active_campaigns`: Number of currently active campaigns

**Use Case:** Analyze advertiser performance against budget and campaign metrics.

### industry_benchmarks.csv
Industry benchmark data including:
- `industry`: Industry vertical name
- `avg_conversion_rate`: Average conversion rate as decimal
- `avg_time_to_conversion_minutes`: Average time from impression to conversion
- `benchmark_ctr`: Benchmark click-through rate as decimal

**Use Case:** Compare actual performance against industry standards for performance analysis.

## Workshop Usage

These CSV files are used in Lab 4B to demonstrate:

1. **CSV Import Process**: Upload to Minio (S3-compatible storage) and create external tables
2. **Data Conversion**: Transform CSV data to Iceberg format for optimal query performance
3. **Federated Queries**: Join CSV reference data with operational (HCD) and analytical (Iceberg) data
4. **Business Intelligence**: Create advanced analytics combining multiple data sources

## Import Instructions

### Step 1: Upload to Minio

```bash
# Configure Minio client
mc alias set myminio http://localhost:9000 <access_key> <secret_key>

# Create bucket
mc mb myminio/csv-imports

# Upload CSV files
mc cp workshop_data/*.csv myminio/csv-imports/
```

### Step 2: Create External Tables

```sql
-- Example for publisher metadata
CREATE TABLE iceberg_data.reference_data.publisher_metadata_csv (
    publisher_id varchar,
    publisher_name varchar,
    category varchar,
    country varchar,
    tier varchar,
    commission_rate varchar
) WITH (
    external_location = 's3a://csv-imports/',
    format = 'CSV',
    csv_separator = ',',
    skip_header_line_count = 1
);
```

### Step 3: Convert to Iceberg Format

```sql
-- Create Iceberg table
CREATE TABLE iceberg_data.reference_data.publisher_metadata (
    publisher_id varchar,
    publisher_name varchar,
    category varchar,
    country varchar,
    tier varchar,
    commission_rate double
) WITH (
    format = 'PARQUET'
);

-- Load data
INSERT INTO iceberg_data.reference_data.publisher_metadata
SELECT 
    publisher_id,
    publisher_name,
    category,
    country,
    tier,
    CAST(commission_rate AS DOUBLE)
FROM iceberg_data.reference_data.publisher_metadata_csv;
```

### Step 4: Query Federated Data

```sql
-- Join operational data with CSV metadata
SELECT 
    h.publishers_id,
    pm.publisher_name,
    pm.category,
    pm.commission_rate,
    COUNT(*) as impressions
FROM hcd.affiliate_junction.impression_tracking h
JOIN iceberg_data.reference_data.publisher_metadata pm
    ON h.publishers_id = pm.publisher_id
WHERE h.timestamp > CURRENT_TIMESTAMP - INTERVAL '5' MINUTE
GROUP BY h.publishers_id, pm.publisher_name, pm.category, pm.commission_rate
ORDER BY impressions DESC;
```

## Data Schema Alignment

The CSV data is designed to align with the existing demo data:

- **Publisher IDs**: Match format `pub_001` through `pub_010`
- **Advertiser IDs**: Match format `adv_001` through `adv_010`
- **Industries**: Align with common affiliate marketing verticals
- **Metrics**: Realistic conversion rates and benchmarks

## Customization

Workshop participants can:

1. Modify existing CSV files with custom data
2. Create new CSV files with additional reference data
3. Design custom federated queries joining their data
4. Present insights derived from their custom analysis

## Additional Resources

- [WORKSHOP_GUIDE.md](../WORKSHOP_GUIDE.md) - Complete workshop instructions
- [FEDERATED_QUERIES.md](../FEDERATED_QUERIES.md) - Query examples and patterns
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture details