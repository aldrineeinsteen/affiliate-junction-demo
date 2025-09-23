
-- Create schema if it doesn't exist  
CREATE SCHEMA IF NOT EXISTS iceberg_data.affiliate_junction
WITH (location = 's3a://iceberg-bucket/affiliate_junction/');

-- Create impression tracking table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.impression_tracking (
    publishers_id varchar,
    advertisers_id varchar,
    cookie_id varchar,
    timestamp timestamp,
    impressions integer
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['day(timestamp)', 'bucket(publishers_id, 10)']
);

-- Create conversion tracking table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.conversion_tracking (
    advertisers_id varchar,
    timestamp timestamp,
    cookie_id varchar
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['day(timestamp)', 'bucket(advertisers_id, 10)']
);

-- Create conversions identification table
CREATE TABLE IF NOT EXISTS iceberg_data.affiliate_junction.conversions_identified (
    advertisers_id varchar,
    publishers_id varchar,
    cookie_id varchar,
    conversion_timestamp timestamp,
    impression_timestamp timestamp,
    time_to_conversion_seconds bigint,
    created_at timestamp WITH TIME ZONE
) WITH (
    format = 'PARQUET',
    partitioning = ARRAY['day(conversion_timestamp)', 'bucket(publishers_id, 10)']
);


