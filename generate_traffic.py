#!/usr/bin/env python

import os
import sys
import time
import logging
import random
import uuid
import json
from datetime import datetime, timezone, date
from cassandra.util import uuid_from_time

# Import shared modules
from affiliate_common import CassandraConnection, ServicesManager, SchemaExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SyntheticTrafficGenerator:
    def __init__(self):
        self.cassandra_connection = None
        self.cassandra_session = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
        
        # Store current settings for comparison
        self.current_settings = {
            'AFFILIATE_JUNCTION_ADVERTISERS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_ADVERTISERS_COUNT')),
            'AFFILIATE_JUNCTION_PUBLISHERS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_PUBLISHERS_COUNT')),
            'AFFILIATE_JUNCTION_COOKIES_COUNT': int(os.getenv('AFFILIATE_JUNCTION_COOKIES_COUNT')),
            'AFFILIATE_JUNCTION_HISTORY_MINS': int(os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')),
            'AFFILIATE_JUNCTION_TRAFFIC_MIN': int(os.getenv('AFFILIATE_JUNCTION_TRAFFIC_MIN')),
            'AFFILIATE_JUNCTION_SALES_MIN': int(os.getenv('AFFILIATE_JUNCTION_SALES_MIN')),
            'AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT'))
        }
        
        # Generate indexes of string IDs for advertisers and publishers
        self.advertisers = [f"AID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_ADVERTISERS_COUNT'])]
        self.publishers = [f"PID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_PUBLISHERS_COUNT'])]
        
        # Generate pool of cookie IDs based on environment variable
        self.cookie_ids = [f"CID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_COOKIES_COUNT'])]
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'impression_aggregates_count': [],
            'total_impressions': [],
            'impressions_by_minute_count': [],
            'conversion_count': [],
            'conversions_by_minute_count': [],
            'execution_time_seconds': [],
            'current_advertisers_count': [],
            'current_publishers_count': [],
            'current_cookies_count': [],
            'traffic_per_minute': [],
            'sales_per_minute': []
        }
        
        logger.info(f"Generated {len(self.advertisers)} advertisers, {len(self.publishers)} publishers, and {len(self.cookie_ids)} cookie IDs")
        
    def execute_schema(self):
        """Execute the Cassandra schema file to create keyspace and tables"""
        try:
            SchemaExecutor.execute_cassandra_schema(self.script_dir, self.cassandra_session)
                
        except Exception as e:
            logger.error(f"Failed to execute schema: {e}")
            raise
    
    def get_random_cookie_id(self):
        """Get a random cookie ID from the predefined pool"""
        return random.choice(self.cookie_ids)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster"""
        try:
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Prepare statements for data insertion
            self.prepare_statements()
            
            # Initialize services manager after connecting
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                'generate_traffic',
                'Synthetic traffic generation service'
            )
            
            logger.info("Connected to Cassandra cluster")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
    
    def prepare_statements(self):
        """Prepare Cassandra statements for data insertion"""
        try:
            # Prepare statement for impression tracking insert/update (will overwrite if exists)
            self.impression_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions) 
                VALUES (?, ?, ?, ?, ?)
            """)
            
            # Prepare statement for impressions_by_minute table
            self.impressions_by_minute_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.impressions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, impression_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            # Prepare statement for conversion tracking with configurable TTL
            self.conversion_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversion_tracking (advertisers_id, timestamp, cookie_id) 
                VALUES (?, ?, ?)
            """)
            
            # Prepare statement for conversions_by_minute table
            self.conversions_by_minute_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, conversion_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            logger.info(f"Prepared statements for data insertion with {os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')}-minute TTL")
            
        except Exception as e:
            logger.error(f"Failed to prepare statements: {e}")
            raise
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            service_record = self.services_manager.poll_services_table()
            if service_record:
                self.update_settings_from_service(service_record)
                
        except Exception as e:
            logger.error(f"Failed to poll services table: {e}")
            # Continue with current settings if polling fails
    
    def insert_service_record(self):
        """Insert a new service record with default settings from .env"""
        try:
            self.services_manager.insert_service_record(self.current_settings)
            
        except Exception as e:
            logger.error(f"Failed to insert service record: {e}")
    
    def update_settings_from_service(self, service_record):
        """Update runtime settings if they have changed in the services table"""
        try:
            if service_record.settings:
                new_settings = json.loads(service_record.settings)
                
                # Check if settings have changed
                settings_changed = False
                for key, value in new_settings.items():
                    if key in self.current_settings and self.current_settings[key] != value:
                        logger.info(f"Setting {key} changed from {self.current_settings[key]} to {value}")
                        self.current_settings[key] = value
                        settings_changed = True
                
                # If settings changed, regenerate the data pools
                if settings_changed:
                    self.regenerate_data_pools()
                    logger.info("Settings updated from services table")
                    
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse settings from services table: {e}")
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
    
    def regenerate_data_pools(self):
        """Regenerate advertisers, publishers, and cookie pools based on updated settings"""
        try:
            # Regenerate advertisers
            self.advertisers = [f"AID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_ADVERTISERS_COUNT'])]
            
            # Regenerate publishers
            self.publishers = [f"PID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_PUBLISHERS_COUNT'])]
            
            # Regenerate cookie IDs
            self.cookie_ids = [f"CID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_COOKIES_COUNT'])]
            
            logger.info(f"Regenerated pools: {len(self.advertisers)} advertisers, {len(self.publishers)} publishers, {len(self.cookie_ids)} cookie IDs")
            
        except Exception as e:
            logger.error(f"Failed to regenerate data pools: {e}")
    
    def collect_iteration_stats(self, impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data, execution_time):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Calculate total impressions
            total_impressions = sum(record['impressions'] for record in impression_data) if impression_data else 0
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'impression_aggregates_count': (current_timestamp, len(impression_data)),
                'total_impressions': (current_timestamp, total_impressions),
                'impressions_by_minute_count': (current_timestamp, len(impressions_by_minute_data)),
                'conversion_count': (current_timestamp, len(conversion_data)),
                'conversions_by_minute_count': (current_timestamp, len(conversions_by_minute_data)),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'current_advertisers_count': (current_timestamp, len(self.advertisers)),
                'current_publishers_count': (current_timestamp, len(self.publishers)),
                'current_cookies_count': (current_timestamp, len(self.cookie_ids)),
                'traffic_per_minute': (current_timestamp, self.current_settings['AFFILIATE_JUNCTION_TRAFFIC_MIN']),
                'sales_per_minute': (current_timestamp, self.current_settings['AFFILIATE_JUNCTION_SALES_MIN'])
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to collect iteration stats: {e}")
            return {}
    
    def update_timeseries_stats(self, iteration_stats):
        """Update timeseries data with new stats, maintaining 90 datapoints"""
        try:
            self.services_manager.update_timeseries_stats(iteration_stats)
            
        except Exception as e:
            logger.error(f"Failed to update timeseries stats: {e}")
    
    def update_service_stats(self):
        """Update the services table with current stats and query metrics"""
        try:
            # Get query metrics from database connection
            cassandra_metrics = self.cassandra_connection.get_query_metrics()
            
            # Update services table with stats and query metrics
            self.services_manager.update_query_metrics(cassandra_metrics=cassandra_metrics)
            
            # Clear metrics after storing them
            self.cassandra_connection.clear_query_metrics()
            
        except Exception as e:
            logger.error(f"Failed to update service stats: {e}")
    
    def generate_synthetic_data(self):
        """Generate synthetic traffic data"""
        logger.info("Generating synthetic traffic data...")
        
        # Get current time clipped to the minute
        now = datetime.now(timezone.utc)
        clipped_timestamp = now.replace(second=0, microsecond=0)
        
        # Get bucket date (floor timestamp to UTC minute)
        bucket_date = clipped_timestamp
        
        # Aggregate impression data by key (publishers_id, cookie_id, timestamp)
        impression_aggregates = {}
        impressions_by_minute_data = []
        
        for _ in range(self.current_settings['AFFILIATE_JUNCTION_TRAFFIC_MIN']):
            publisher_id = random.choice(self.publishers)
            advertiser_id = random.choice(self.advertisers)
            cookie_id = self.get_random_cookie_id()
            
            # Create a composite key for aggregation
            key = (publisher_id, cookie_id, clipped_timestamp)
            
            if key in impression_aggregates:
                # Increment the count for this key
                impression_aggregates[key]['impressions'] += 1
            else:
                # Create new entry for this key
                impression_aggregates[key] = {
                    'publishers_id': publisher_id,
                    'cookie_id': cookie_id,
                    'timestamp': clipped_timestamp,
                    'advertisers_id': advertiser_id,
                    'impressions': 1
                }
            
            # Generate individual impression for impressions_by_minute table
            # Create a hash bucket based on publisher_id for write distribution
            bucket = hash(publisher_id) % self.current_settings["AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"]
            
            # Generate timeuuid for precise ordering
            ts_uuid = uuid_from_time(now)
            
            # Generate unique impression ID
            impression_id = uuid.uuid4()
            
            impressions_by_minute_data.append({
                'bucket_date': bucket_date,
                'bucket': bucket,
                'ts': ts_uuid,
                'publishers_id': publisher_id,
                'advertisers_id': advertiser_id,
                'cookie_id': cookie_id,
                'impression_id': impression_id
            })
        
        # Convert aggregated data to list
        impression_data = list(impression_aggregates.values())
        
        # Generate conversion tracking data
        conversion_data = []
        conversions_by_minute_data = []
        
        for _ in range(self.current_settings['AFFILIATE_JUNCTION_SALES_MIN']):
            advertiser_id = random.choice(self.advertisers)
            publisher_id = random.choice(self.publishers)  # Add publisher for conversions_by_minute
            cookie_id = self.get_random_cookie_id()
            
            conversion_data.append({
                'advertisers_id': advertiser_id,
                'timestamp': clipped_timestamp,
                'cookie_id': cookie_id
            })
            
            # Generate individual conversion for conversions_by_minute table
            # Create a hash bucket based on advertiser_id for write distribution
            bucket = hash(advertiser_id) % self.current_settings["AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"]
            
            # Generate timeuuid for precise ordering
            ts_uuid = uuid_from_time(now)
            
            # Generate unique conversion ID
            conversion_id = uuid.uuid4()
            
            conversions_by_minute_data.append({
                'bucket_date': bucket_date,
                'bucket': bucket,
                'ts': ts_uuid,
                'publishers_id': publisher_id,
                'advertisers_id': advertiser_id,
                'cookie_id': cookie_id,
                'conversion_id': conversion_id
            })
        
        logger.info(f"Generated {len(impression_data)} aggregated impression records ({sum(record['impressions'] for record in impression_data)} total impressions), {len(impressions_by_minute_data)} minute-based impression records, {len(conversion_data)} conversion records, and {len(conversions_by_minute_data)} minute-based conversion records")
        
        # Insert data to Cassandra
        self.insert_data_to_cassandra(impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data)
        
        # Return data for stats collection
        return impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data
    
    def execute_batch_in_chunks(self, data, prepared_statement, param_extractor, batch_size=10000, operation_name="records", representative_query=None):
        """Execute batch operations in chunks to avoid Cassandra batch size limits"""
        from cassandra.query import BatchStatement, BatchType
        
        if not data:
            return
            
        total_records = len(data)
        logger.info(f"Processing {total_records} {operation_name} in chunks of {batch_size}...")
        
        # Process data in chunks
        for i in range(0, total_records, batch_size):
            chunk = data[i:i + batch_size]
            
            # Create batch statement for this chunk
            batch = BatchStatement(batch_type=BatchType.UNLOGGED)
            for record in chunk:
                batch.add(prepared_statement, param_extractor(record))
            
            # Execute the batch using connection wrapper to capture metrics
            batch_description = f"Batch insert {len(chunk)} {operation_name}"
            
            # Pass the batch object directly to the wrapper with representative query
            result = self.cassandra_connection.execute_query(
                query=batch,  # Pass the batch object itself
                parameters=None,
                query_description=batch_description,
                representative_query=representative_query
            )
                
            logger.info(f"Batch inserted {len(chunk)} {operation_name} (chunk {i//batch_size + 1}/{(total_records + batch_size - 1)//batch_size})")

    def insert_data_to_cassandra(self, impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data):
        """Insert data into Cassandra using batch operations with dual write pattern"""
        try:
            logger.info("Inserting data to Cassandra using batch operations...")
            
            # Use batch operations for better performance
            from cassandra.query import BatchStatement, BatchType
            
            # Insert impression tracking data using chunked batches
            if impression_data:
                self.execute_batch_in_chunks(
                    impression_data,
                    self.impression_insert_stmt,
                    lambda record: [
                        record['publishers_id'],
                        record['cookie_id'],
                        record['timestamp'],
                        record['advertisers_id'],
                        record['impressions']
                    ],
                    operation_name="impression tracking records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions) VALUES (?, ?, ?, ?, ?)"""
                )
            
            # Insert impressions_by_minute data using chunked batches (dual write pattern)
            if impressions_by_minute_data:
                self.execute_batch_in_chunks(
                    impressions_by_minute_data,
                    self.impressions_by_minute_insert_stmt,
                    lambda record: [
                        record['bucket_date'],
                        record['bucket'],
                        record['ts'],
                        record['publishers_id'],
                        record['advertisers_id'],
                        record['cookie_id'],
                        record['impression_id']
                    ],
                    operation_name="impressions_by_minute records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.impressions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, impression_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                )
            
            # Insert conversion tracking data using chunked batches
            if conversion_data:
                self.execute_batch_in_chunks(
                    conversion_data,
                    self.conversion_insert_stmt,
                    lambda record: [
                        record['advertisers_id'],
                        record['timestamp'],
                        record['cookie_id']
                    ],
                    operation_name="conversion tracking records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversion_tracking (advertisers_id, timestamp, cookie_id) VALUES (?, ?, ?)"""
                )
            
            # Insert conversions_by_minute data using chunked batches (dual write pattern)
            if conversions_by_minute_data:
                self.execute_batch_in_chunks(
                    conversions_by_minute_data,
                    self.conversions_by_minute_insert_stmt,
                    lambda record: [
                        record['bucket_date'],
                        record['bucket'],
                        record['ts'],
                        record['publishers_id'],
                        record['advertisers_id'],
                        record['cookie_id'],
                        record['conversion_id']
                    ],
                    operation_name="conversions_by_minute records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, conversion_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                )
            
            logger.info(f"Successfully inserted all data: {len(impression_data)} impression records, {len(impressions_by_minute_data)} impressions_by_minute records, {len(conversion_data)} conversion records, and {len(conversions_by_minute_data)} conversions_by_minute records")
            
        except Exception as e:
            logger.error(f"Failed to insert data to Cassandra: {e}")
            raise
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.cassandra_connection:
                self.cassandra_connection.close()
                logger.info("Cassandra connection closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Synthetic Traffic Generator")
            
            # Execute schema before connecting to Cassandra
            self.execute_schema()
            
            # Connect to databases
            self.connect_to_cassandra()
            
            # Main loop - no-op for now
            logger.info("Entering main loop...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Poll services table for configuration updates
                    self.poll_services_table()
                    
                    # Generate and process synthetic data
                    impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data = self.generate_synthetic_data()
                    
                    # Calculate how long the data generation took
                    execution_time = time.time() - iteration_start
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        impression_data, impressions_by_minute_data, 
                        conversion_data, conversions_by_minute_data, 
                        execution_time
                    )
                    
                    # Update timeseries data with new stats
                    self.update_timeseries_stats(iteration_stats)
                    
                    # Write stats to services table
                    self.update_service_stats()
                    
                    # Sleep for the remaining time to maintain 60-second intervals
                    sleep_time = max(0, 60 - execution_time)
                    logger.info(f"Data generation took {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until next traffic generation...")
                    time.sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    generator = SyntheticTrafficGenerator()
    generator.run()


if __name__ == "__main__":
    main()