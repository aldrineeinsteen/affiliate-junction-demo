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
    impressions COUNTER,
    PRIMARY KEY ((publishers_id, cookie_id), timestamp, advertisers_id)
) WITH CLUSTERING ORDER BY (timestamp DESC);

-- Create conversion tracking table
CREATE TABLE IF NOT EXISTS conversion_tracking (
    advertisers_id TEXT,
    timestamp TIMESTAMP,
    cookie_id TEXT,
    PRIMARY KEY (advertisers_id, timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC);