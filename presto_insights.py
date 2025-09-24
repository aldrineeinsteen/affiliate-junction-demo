#!/usr/bin/env python

import os
import sys
import time
import logging
import prestodb
from datetime import datetime, timezone, timedelta
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


class AffiliateJunctionInsights:
    def __init__(self):
        self.presto_connection = None
        self.cassandra_session = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.load_environment()
        
    def load_environment(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            logger.info("Environment variables loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            sys.exit(1)
    
    def connect_to_presto(self):
        """Establish connection to Presto - reusing configuration from hcd_to_presto.py"""
        try:           
            self.presto_connection = prestodb.dbapi.connect(
                host=os.getenv('PRESTO_HOST'),
                port=int(os.getenv('PRESTO_PORT')),
                user=os.getenv('PRESTO_USER'),
                catalog=os.getenv('PRESTO_CATALOG'),
                schema=os.getenv('PRESTO_SCHEMA'),
                http_scheme='https',
                auth=prestodb.auth.BasicAuthentication(
                    os.getenv('PRESTO_USER'), 
                    os.getenv('PRESTO_PASSWD')
                )
            )
            self.presto_connection._http_session.verify = "/certs/presto.crt"
            
            logger.info(f"Connected to Presto at {os.getenv('PRESTO_HOST')}:{os.getenv('PRESTO_PORT')}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Presto: {e}")
            sys.exit(1)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster - reusing from hcd_to_presto.py"""
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
            
            logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
    
    def process_publisher_impressions(self, target_minute):
        """
        Process impression data from the previous minute and upsert to HCD publishers table.
        
        Args:
            target_minute (datetime): The minute timestamp to process impressions for
        """
        logger.info(f"Starting publisher impressions processing for minute: {target_minute}")
        
        try:
            cursor = self.presto_connection.cursor()
            
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Format datetime values directly into the query (Presto doesn't support parameterized queries)
            impressions_query = f'''
            SELECT 
                publishers_id,
                SUM(impressions) as total_impressions
            FROM iceberg_data.affiliate_junction.impression_tracking
            WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}' 
                AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
            GROUP BY publishers_id
            '''
            
            cursor.execute(impressions_query)
            publisher_impressions = cursor.fetchall()
            cursor.close()
            
            if not publisher_impressions:
                logger.info(f"No impressions found for minute: {target_minute}")
                return
            
            logger.info(f"Found impressions for {len(publisher_impressions)} publishers in minute: {target_minute}")
            
            # Process each publisher's impressions
            unix_timestamp = int(target_minute.timestamp())
            
            for row in publisher_impressions:
                publisher_id = row[0]
                impression_count = int(row[1])
                
                self.upsert_publisher_impressions(publisher_id, unix_timestamp, impression_count)
            
        except Exception as e:
            logger.error(f"Error during publisher impressions processing: {e}")
            raise
        
        logger.info(f"Publisher impressions processing completed for minute: {target_minute}")
    
    def upsert_publisher_impressions(self, publisher_id, unix_timestamp, impression_count):
        """
        Upsert impression data for a publisher in the HCD publishers table.
        
        Args:
            publisher_id (str): The publisher ID
            unix_timestamp (int): Unix timestamp of the minute
            impression_count (int): Number of impressions for this minute
        """
        try:
            # First, try to read existing record
            select_query = """
            SELECT impressions, last_updated
            FROM publishers
            WHERE publisher_id = ?
            """
            
            existing_row = self.cassandra_session.execute(select_query, [publisher_id]).one()
            
            current_time = datetime.now(timezone.utc)
            new_impression_tuple = (unix_timestamp, impression_count)
            
            if existing_row:
                # Update existing record
                existing_impressions = existing_row.impressions or []
                
                # Add new impression tuple
                updated_impressions = existing_impressions + [new_impression_tuple]
                
                # Sort by timestamp (oldest first)
                updated_impressions.sort(key=lambda x: x[0])
                
                # Keep only the latest 90 entries
                if len(updated_impressions) > 90:
                    updated_impressions = updated_impressions[-90:]
                
                # Update the record
                update_query = """
                UPDATE publishers
                SET impressions = ?, last_updated = ?
                WHERE publisher_id = ?
                """
                
                self.cassandra_session.execute(update_query, [updated_impressions, current_time, publisher_id])
                logger.debug(f"Updated publisher {publisher_id} with {impression_count} impressions for timestamp {unix_timestamp}")
                
            else:
                # Insert new record
                new_impressions = [new_impression_tuple]
                
                insert_query = """
                INSERT INTO publishers (publisher_id, impressions, conversions, last_updated)
                VALUES (?, ?, ?, ?)
                """
                
                self.cassandra_session.execute(insert_query, [publisher_id, new_impressions, [], current_time])
                logger.debug(f"Inserted new publisher {publisher_id} with {impression_count} impressions for timestamp {unix_timestamp}")
                
        except Exception as e:
            logger.error(f"Error upserting publisher impressions for {publisher_id}: {e}")
            raise
    
    def identify_conversions(self, target_minute):
        """
        Stub function to identify conversions and populate the conversions_identified table.
        
        This function will analyze impression_tracking and conversion_tracking data
        to identify which impressions led to conversions within a reasonable time window.
        
        Args:
            target_minute (datetime): The minute timestamp to process conversions for
        """
        logger.info(f"Starting conversion identification for minute: {target_minute}")
        
        try:
            # TODO: Implement the actual conversion identification logic
            # This will involve:
            # 1. Reading impressions from impression_tracking table
            # 2. Reading conversions from conversion_tracking table  
            # 3. Matching conversions to impressions based on cookie_id and timing
            # 4. Calculating time_to_conversion_seconds
            # 5. Inserting matched records into conversions_identified table
            
            cursor = self.presto_connection.cursor()
            
            # For now, this is a stub - just log that we would process this minute
            logger.info(f"STUB: Would identify conversions for minute {target_minute}")
            logger.info("STUB: Would query impression_tracking and conversion_tracking tables")
            logger.info("STUB: Would match conversions to impressions by cookie_id")
            logger.info("STUB: Would calculate time_to_conversion_seconds")
            logger.info("STUB: Would insert results into conversions_identified table")
            
            # Example of the structure that will be implemented later:
            """
            # Query to find conversions that occurred after impressions
            conversion_query = '''
            SELECT 
                c.advertisers_id,
                i.publishers_id,
                c.cookie_id,
                c.timestamp as conversion_timestamp,
                i.timestamp as impression_timestamp,
                date_diff('second', i.timestamp, c.timestamp) as time_to_conversion_seconds,
                current_timestamp as created_at
            FROM iceberg_data.affiliate_junction.conversion_tracking c
            INNER JOIN iceberg_data.affiliate_junction.impression_tracking i
                ON c.cookie_id = i.cookie_id 
                AND c.advertisers_id = i.advertisers_id
                AND c.timestamp >= i.timestamp
                AND c.timestamp <= i.timestamp + interval '30' day
            WHERE c.timestamp >= ? AND c.timestamp < ?
            '''
            
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            cursor.execute(conversion_query, (start_time, end_time))
            conversions = cursor.fetchall()
            
            if conversions:
                # Insert identified conversions into conversions_identified table
                insert_query = '''
                INSERT INTO iceberg_data.affiliate_junction.conversions_identified
                (advertisers_id, publishers_id, cookie_id, conversion_timestamp, 
                 impression_timestamp, time_to_conversion_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
                
                for conversion in conversions:
                    cursor.execute(insert_query, conversion)
                
                logger.info(f"Inserted {len(conversions)} conversion identifications")
            """
            
            cursor.close()
            
        except Exception as e:
            logger.error(f"Error during conversion identification: {e}")
            raise
        
        logger.info(f"Conversion identification completed for minute: {target_minute}")
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.cassandra_session:
                self.cassandra_session.shutdown()
                logger.info("Cassandra connection closed")
            
            if self.presto_connection:
                self.presto_connection.close()
                logger.info("Presto connection closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop - runs every minute at 45 seconds past the minute"""
        try:
            logger.info("Starting Affiliate Junction Insights")
            
            # Initialize connections
            self.connect_to_presto()
            self.connect_to_cassandra()
            
            logger.info("Entering main loop...")
            
            # First iteration - process the previous minute immediately
            first_run = True
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    current_time = datetime.now(timezone.utc)
                    
                    if first_run:
                        # For the first run, process the previous minute immediately
                        target_minute = current_time.replace(second=0, microsecond=0) - timedelta(minutes=1)
                        logger.info("First iteration - processing previous minute immediately")
                        first_run = False
                    else:
                        # For subsequent runs, process the current minute (which just completed)
                        target_minute = current_time.replace(second=0, microsecond=0)
                    
                    # Main processing tasks
                    self.process_publisher_impressions(target_minute)
                    self.identify_conversions(target_minute)
                    
                    execution_time = time.time() - iteration_start
                    
                    # Calculate time until 45 seconds past the next minute
                    next_minute_plus_45 = (current_time.replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=45))
                    sleep_time = (next_minute_plus_45 - datetime.now(timezone.utc)).total_seconds()
                    
                    # Ensure we don't have negative sleep time
                    if sleep_time < 0:
                        next_minute_plus_45 = next_minute_plus_45 + timedelta(minutes=1)
                        sleep_time = (next_minute_plus_45 - datetime.now(timezone.utc)).total_seconds()
                    
                    logger.info(f"Processing completed in {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until 45 seconds past next minute ({next_minute_plus_45.strftime('%H:%M:%S')})...")
                    time.sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    # Sleep for a short time before retrying to prevent rapid failure loops
                    time.sleep(10)
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    insights = AffiliateJunctionInsights()
    insights.run()


if __name__ == "__main__":
    main()