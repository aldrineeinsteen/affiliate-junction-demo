
-- Create schema if it doesn't exist  
CREATE SCHEMA IF NOT EXISTS iceberg_data.affiliate_junction
WITH (location = 's3a://iceberg-bucket/affiliate_junction/');

-- Create impression tracking table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.impression_tracking (
    publishers_id varchar,
    cookie_id varchar,
    advertisers_id varchar,
    timestamp timestamp,
    impressions integer
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['publishers_id', 'cookie_id', 'advertisers_id']
);

-- Create conversions identification table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.conversions_identified (
    conversion_id varchar,
    advertisers_id varchar,
    publishers_id varchar,
    cookie_id varchar,
    conversion_timestamp timestamp,
    impression_timestamp timestamp,
    time_to_conversion_seconds bigint,
    created_at timestamp WITH TIME ZONE
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['conversion_timestamp']
);

-- Create analytics summary table for dashboards
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.analytics_summary (
    summary_date date,
    publishers_id varchar,
    advertisers_id varchar,
    total_impressions bigint,
    total_conversions bigint,
    conversion_rate double,
    unique_visitors bigint,
    created_at timestamp WITH TIME ZONE
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['summary_date']
);
