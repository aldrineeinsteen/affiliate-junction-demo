-- Create keyspace for affiliate junction
CREATE KEYSPACE IF NOT EXISTS affiliate_junction
WITH REPLICATION = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

-- Use the keyspace
USE affiliate_junction;

-- Create impression tracking table
CREATE TABLE IF NOT EXISTS impression_tracking (
    publishers_id TEXT,
    cookie_id TEXT,
    advertisers_id TEXT,
    timestamp TIMESTAMP,
    impressions INT,
    PRIMARY KEY ((publishers_id, cookie_id, advertisers_id), timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
AND default_time_to_live = 3600;

-- Create conversion tracking table
CREATE TABLE IF NOT EXISTS conversion_tracking (
    advertisers_id TEXT,
    timestamp TIMESTAMP,
    cookie_id TEXT,
    PRIMARY KEY (advertisers_id, timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
AND default_time_to_live = 3600;

-- Create impressions by minute table for time-based impression tracking
CREATE TABLE IF NOT EXISTS impressions_by_minute (
    bucket_date TIMESTAMP,   
    bucket SMALLINT,        
    ts TIMEUUID,            
    publishers_id TEXT,
    advertisers_id TEXT,
    cookie_id TEXT,
    impression_id UUID,     
    PRIMARY KEY ((bucket_date, bucket), ts, publishers_id, advertisers_id, cookie_id, impression_id)
) WITH CLUSTERING ORDER BY (ts ASC)
AND default_time_to_live = 6000;

-- Create conversions by minute table for time-based conversion tracking
CREATE TABLE IF NOT EXISTS conversions_by_minute (
    bucket_date TIMESTAMP,  
    bucket SMALLINT,        
    ts TIMEUUID,             
    publishers_id TEXT,
    advertisers_id TEXT,
    cookie_id TEXT,
    conversion_id UUID,     
    PRIMARY KEY ((bucket_date, bucket), ts, publishers_id, advertisers_id, cookie_id, conversion_id)
) WITH CLUSTERING ORDER BY (ts ASC)
AND default_time_to_live = 6000;

-- Create publishers table with trailing 90-minute data using JSON text fields
-- Each JSON array contains objects with timestamp and count: [{"ts": 1234567890, "count": 10}, ...]
CREATE TABLE IF NOT EXISTS publishers (
    publisher_id text PRIMARY KEY,
    impressions text, 
    conversions text, 
    last_updated timestamp
) WITH default_time_to_live = 21600;

-- Create advertisers table with trailing 90-minute data using JSON text fields
-- Each JSON array contains objects with timestamp and count: [{"ts": 1234567890, "count": 10}, ...]
CREATE TABLE IF NOT EXISTS advertisers (
    advertiser_id TEXT,
    impressions text,
    conversions text,
    last_updated TIMESTAMP,
    PRIMARY KEY (advertiser_id)
) WITH default_time_to_live = 21600;

-- Create services table for managing system services
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    description TEXT,
    last_updated TIMESTAMP,
    stats TEXT,
    settings TEXT,
    query_metrics TEXT
);


