#!/usr/bin/env python

import os
import sys
import time
import logging
import uuid
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
        
        # Generate indexes of UUIDs for advertisers and publishers
        self.advertisers = [uuid.uuid4() for _ in range(int(os.getenv('AFFILIATE_JUNCTION_ADVERTISERS_COUNT')))]
        self.publishers = [uuid.uuid4() for _ in range(int(os.getenv('AFFILIATE_JUNCTION_PUBLISHERS_COUNT')))]
        
        logger.info(f"Generated {len(self.advertisers)} advertisers and {len(self.publishers)} publishers")
        
    def load_environment(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            logger.info("Environment variables loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            sys.exit(1)
    
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
            # Prepare statement for impression tracking
            self.impression_insert_stmt = self.cassandra_session.prepare("""
                UPDATE impression_tracking 
                SET impressions = impressions + ? 
                WHERE publishers_id = ? AND cookie_id = ? AND timestamp = ? AND advertisers_id = ?
            """)
            
            # Prepare statement for conversion tracking
            self.conversion_insert_stmt = self.cassandra_session.prepare("""
                INSERT INTO conversion_tracking (advertisers_id, timestamp, cookie_id) 
                VALUES (?, ?, ?)
            """)
            
            logger.info("Prepared statements for data insertion")
            
        except Exception as e:
            logger.error(f"Failed to prepare statements: {e}")
            raise
    
    def generate_synthetic_data(self):
        """Generate synthetic traffic data"""
        logger.info("Generating synthetic traffic data...")
        
        # Get current time clipped to the minute
        now = datetime.now(timezone.utc)
        clipped_timestamp = now.replace(second=0, microsecond=0)
        
        # Generate impression tracking data
        impression_data = []
        for _ in range(int(os.getenv('AFFILIATE_JUNCTION_TRAFFIC_MIN'))):
            publisher_id = random.choice(self.publishers)
            advertiser_id = random.choice(self.advertisers)
            cookie_id = uuid.uuid4()
            
            impression_data.append({
                'publishers_id': publisher_id,
                'cookie_id': cookie_id,
                'advertisers_id': advertiser_id,
                'timestamp': clipped_timestamp,
                'impressions': 1
            })
        
        # Generate conversion tracking data
        conversion_data = []
        for _ in range(int(os.getenv('AFFILIATE_JUNCTION_SALES_MIN'))):
            advertiser_id = random.choice(self.advertisers)
            cookie_id = uuid.uuid4()
            
            conversion_data.append({
                'advertisers_id': advertiser_id,
                'timestamp': clipped_timestamp,
                'cookie_id': cookie_id
            })
        
        logger.info(f"Generated {len(impression_data)} impression records and {len(conversion_data)} conversion records")
        
        # Insert data to Cassandra
        self.insert_data_to_cassandra(impression_data, conversion_data)
    
    def insert_data_to_cassandra(self, impression_data, conversion_data):
        """Insert data into Cassandra"""
        try:
            logger.info("Inserting data to Cassandra...")
            
            # Insert impression tracking data
            for record in impression_data:
                self.cassandra_session.execute(
                    self.impression_insert_stmt,
                    [
                        record['impressions'],
                        record['publishers_id'],
                        record['cookie_id'],
                        record['timestamp'],
                        record['advertisers_id']
                    ]
                )
            
            # Insert conversion tracking data
            for record in conversion_data:
                self.cassandra_session.execute(
                    self.conversion_insert_stmt,
                    [
                        record['advertisers_id'],
                        record['timestamp'],
                        record['cookie_id']
                    ]
                )
            
            logger.info(f"Successfully inserted {len(impression_data)} impression records and {len(conversion_data)} conversion records")
            
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
                    # Generate and process synthetic data
                    self.generate_synthetic_data()
                    
                    # Sleep for 60 seconds (1 minute)
                    logger.info("Sleeping for 60 seconds until next traffic generation...")
                    time.sleep(60)
                    
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