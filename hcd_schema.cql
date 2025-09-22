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
) WITH CLUSTERING ORDER BY (timestamp DESC);

-- Create conversion tracking table
CREATE TABLE IF NOT EXISTS conversion_tracking (
    advertisers_id TEXT,
    timestamp TIMESTAMP,
    cookie_id TEXT,
    PRIMARY KEY (advertisers_id, timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
AND default_time_to_live = 360;

-- Create impressions by minute table for time-based impression tracking
CREATE TABLE IF NOT EXISTS impressions_by_minute (
    bucket_date TIMESTAMP,   -- floor(timestamp to UTC minute)
    bucket SMALLINT,         -- 0..(N-1), hash bucket to fan out writes
    ts TIMEUUID,             -- event time (timeuuid for ordering)
    publishers_id TEXT,
    advertisers_id TEXT,
    cookie_id TEXT,
    impression_id UUID,      -- optional unique id for idempotency
    PRIMARY KEY ((bucket_date, bucket), ts, publishers_id, advertisers_id, cookie_id, impression_id)
) WITH CLUSTERING ORDER BY (ts ASC)
AND default_time_to_live = 21600;