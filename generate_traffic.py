#!/usr/bin/env python

import os
import sys
import time
import logging
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SyntheticTrafficGenerator:
    def __init__(self):
        self.cassandra_session = None
        self.load_environment()
        
        # Generate indexes of string IDs for advertisers and publishers
        self.advertisers = [f"AID_{i+1:06d}" for i in range(int(os.getenv('AFFILIATE_JUNCTION_ADVERTISERS_COUNT')))]
        self.publishers = [f"PID_{i+1:06d}" for i in range(int(os.getenv('AFFILIATE_JUNCTION_PUBLISHERS_COUNT')))]
        
        # Generate pool of cookie IDs based on environment variable
        self.cookie_ids = [f"CID_{i+1:06d}" for i in range(int(os.getenv('AFFILIATE_JUNCTION_COOKIES_COUNT')))]
        
        logger.info(f"Generated {len(self.advertisers)} advertisers, {len(self.publishers)} publishers, and {len(self.cookie_ids)} cookie IDs")
        
    def load_environment(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            logger.info("Environment variables loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            sys.exit(1)
    
    def get_random_cookie_id(self):
        """Get a random cookie ID from the predefined pool"""
        return random.choice(self.cookie_ids)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster"""
        try:
            auth_provider = None
            if os.getenv('HCD_USER') and os.getenv('HCD_PASSWD'):
                auth_provider = PlainTextAuthProvider(
                    username=os.getenv('HCD_USER'),
                    password=os.getenv('HCD_PASSWD')
                )
                      
            # Create execution profile with timeout settings
            profile = ExecutionProfile(
                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc=os.getenv('HCD_DATACENTER')),
                request_timeout=10
            )
            
            cluster = Cluster(
                [os.getenv('HCD_HOST', 'localhost')],
                port=int(os.getenv('HCD_PORT', '9042')),
                auth_provider=auth_provider,
                protocol_version=5,
                execution_profiles={'default': profile}
            )
            
            self.cassandra_session = cluster.connect()
            
            # Set keyspace if specified
            if os.getenv('HCD_KEYSPACE'):
                self.cassandra_session.set_keyspace(os.getenv('HCD_KEYSPACE'))
            
            # Prepare statements for data insertion
            self.prepare_statements()
            
            logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
            
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
                USING TTL {int(os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')) * 60}
            """)
            
            # Prepare statement for conversion tracking with configurable TTL
            self.conversion_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversion_tracking (advertisers_id, timestamp, cookie_id) 
                VALUES (?, ?, ?)
                USING TTL {int(os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')) * 60}
            """)
            
            logger.info(f"Prepared statements for data insertion with {os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')}-minute TTL")
            
        except Exception as e:
            logger.error(f"Failed to prepare statements: {e}")
            raise
    
    def generate_synthetic_data(self):
        """Generate synthetic traffic data"""
        logger.info("Generating synthetic traffic data...")
        
        # Get current time clipped to the minute
        now = datetime.now(timezone.utc)
        clipped_timestamp = now.replace(second=0, microsecond=0)
        
        # Aggregate impression data by key (publishers_id, cookie_id, timestamp)
        impression_aggregates = {}
        for _ in range(int(os.getenv('AFFILIATE_JUNCTION_TRAFFIC_MIN'))):
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
        
        # Convert aggregated data to list
        impression_data = list(impression_aggregates.values())
        
        # Generate conversion tracking data
        conversion_data = []
        for _ in range(int(os.getenv('AFFILIATE_JUNCTION_SALES_MIN'))):
            advertiser_id = random.choice(self.advertisers)
            cookie_id = self.get_random_cookie_id()
            
            conversion_data.append({
                'advertisers_id': advertiser_id,
                'timestamp': clipped_timestamp,
                'cookie_id': cookie_id
            })
        
        logger.info(f"Generated {len(impression_data)} aggregated impression records ({sum(record['impressions'] for record in impression_data)} total impressions) and {len(conversion_data)} conversion records")
        
        # Insert data to Cassandra
        self.insert_data_to_cassandra(impression_data, conversion_data)
    
    def insert_data_to_cassandra(self, impression_data, conversion_data):
        """Insert data into Cassandra using batch operations"""
        try:
            logger.info("Inserting data to Cassandra using batch operations...")
            
            # Use batch operations for better performance
            from cassandra.query import BatchStatement, BatchType
            
            # Create batch statement for impression tracking data
            if impression_data:
                impression_batch = BatchStatement(batch_type=BatchType.UNLOGGED)
                for record in impression_data:
                    impression_batch.add(
                        self.impression_insert_stmt,
                        [
                            record['publishers_id'],
                            record['cookie_id'],
                            record['timestamp'],
                            record['advertisers_id'],
                            record['impressions']
                        ]
                    )
                self.cassandra_session.execute(impression_batch)
                logger.info(f"Batch inserted {len(impression_data)} impression records")
            
            # Create batch statement for conversion tracking data
            if conversion_data:
                conversion_batch = BatchStatement(batch_type=BatchType.UNLOGGED)
                for record in conversion_data:
                    conversion_batch.add(
                        self.conversion_insert_stmt,
                        [
                            record['advertisers_id'],
                            record['timestamp'],
                            record['cookie_id']
                        ]
                    )
                self.cassandra_session.execute(conversion_batch)
                logger.info(f"Batch inserted {len(conversion_data)} conversion records")
            
            logger.info(f"Successfully batch inserted {len(impression_data)} impression records and {len(conversion_data)} conversion records")
            
        except Exception as e:
            logger.error(f"Failed to insert data to Cassandra: {e}")
            raise
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.cassandra_session:
                self.cassandra_session.shutdown()
                logger.info("Cassandra connection closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Synthetic Traffic Generator")
            
            # Connect to databases
            self.connect_to_cassandra()
            
            # Main loop - no-op for now
            logger.info("Entering main loop...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Generate and process synthetic data
                    self.generate_synthetic_data()
                    
                    # Calculate how long the data generation took
                    execution_time = time.time() - iteration_start
                    
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