
-- Create schema if it doesn't exist  
CREATE SCHEMA IF NOT EXISTS iceberg_data.affiliate_junction
WITH (location = 's3a://iceberg-bucket/affiliate_junction/');

-- Create impressions rollup table for minute-level aggregations
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.impressions_rollup (
    bucket_date timestamp(6),
    publishers_id varchar,
    advertisers_id varchar,
    total_impressions bigint,
    unique_cookies bigint,
    created_at timestamp(6) WITH TIME ZONE DEFAULT current_timestamp
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['bucket_date']
);

-- Create conversions identification table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.conversions_identified (
    conversion_id varchar,
    advertisers_id varchar,
    publishers_id varchar,
    cookie_id varchar,
    conversion_timestamp timestamp(6),
    impression_timestamp timestamp(6),
    time_to_conversion interval,
    created_at timestamp(6) WITH TIME ZONE DEFAULT current_timestamp
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['date(conversion_timestamp)']
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
    created_at timestamp(6) WITH TIME ZONE DEFAULT current_timestamp
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['summary_date']
);
