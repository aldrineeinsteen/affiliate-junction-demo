#!/usr/bin/env python

import os
import sys
import time
import json
import logging
import prestodb
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra import util


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
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'publishers_processed': [],
            'advertisers_processed': [],
            'publisher_impressions_total': [],
            'advertiser_impressions_total': [],
            'execution_time_seconds': [],
            'publisher_processing_time': [],
            'advertiser_processing_time': [],
            'presto_queries_executed': []
        }
        
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
            
            self.cluster = Cluster(
                [os.getenv('HCD_HOST', 'localhost')],
                port=int(os.getenv('HCD_PORT', '9042')),
                auth_provider=auth_provider,
                protocol_version=5,
                execution_profiles={'default': profile}
            )
            
            self.cassandra_session = self.cluster.connect()
            # No need to register user types when using tuples
            
            # Set keyspace if specified
            if os.getenv('HCD_KEYSPACE'):
                self.cassandra_session.set_keyspace(os.getenv('HCD_KEYSPACE'))
            
            logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            # Query for the presto_to_hcd service record
            query = f"SELECT name, description, last_updated, settings FROM {os.getenv('HCD_KEYSPACE')}.services WHERE name = 'presto_to_hcd'"
            result = self.cassandra_session.execute(query)
            
            service_record = result.one()
            
            if service_record:
                # Service record exists
                logger.debug("Found existing presto_to_hcd service record")
            else:
                # No service record exists, insert a new one
                logger.info("No presto_to_hcd service record found, inserting new record")
                self.insert_service_record()
                
        except Exception as e:
            logger.error(f"Failed to poll services table: {e}")
            # Continue with current settings if polling fails
    
    def insert_service_record(self):
        """Insert a new service record with empty settings"""
        try:
            # Empty settings dict as specified
            settings_json = json.dumps({})
            
            insert_query = f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.services (name, description, last_updated, settings, stats)
                VALUES (%s, %s, %s, %s, %s)
            """
            
            self.cassandra_session.execute(insert_query, [
                'presto_to_hcd',
                'Insights service for transferring analytics from Presto to HCD entity tables',
                datetime.now(timezone.utc),
                settings_json,
                '{}'  # Empty stats JSON object
            ])
            
            logger.info("Successfully inserted new presto_to_hcd service record")
            
        except Exception as e:
            logger.error(f"Failed to insert service record: {e}")
    
    def process_entity_impressions(self, target_minute, entity_type='publishers'):
        """
        Process impression data from the previous minute and upsert to HCD entity table.
        
        Args:
            target_minute (datetime): The minute timestamp to process impressions for
            entity_type (str): Type of entity - 'publishers' or 'advertisers'
            
        Returns:
            tuple: (entities_processed, total_impressions, processing_time)
        """
        logger.info(f"Starting {entity_type[:-1]} impressions processing for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            cursor = self.presto_connection.cursor()
            
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Define the ID column name based on entity type
            id_column = f"{entity_type[:-1]}s_id"  # publishers -> publishers_id, advertisers -> advertisers_id
            
            # Format datetime values directly into the query (Presto doesn't support parameterized queries)
            impressions_query = f"""
            SELECT 
                {id_column},
                SUM(impressions) as total_impressions
            FROM iceberg_data.affiliate_junction.impression_tracking
            WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}' 
                AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                AND {id_column} IS NOT NULL
            GROUP BY {id_column}
            """
            
            cursor.execute(impressions_query)
            entity_impressions = cursor.fetchall()
            cursor.close()
            
            entities_processed = len(entity_impressions)
            total_impressions = 0
            
            if not entity_impressions:
                logger.info(f"No impressions found for {entity_type} in minute: {target_minute}")
                processing_time = time.time() - processing_start_time
                return entities_processed, total_impressions, processing_time
            
            logger.info(f"Found impressions for {len(entity_impressions)} {entity_type} in minute: {target_minute}")
            
            # Process each entity's impressions
            unix_timestamp = int(target_minute.timestamp())
            
            for row in entity_impressions:
                entity_id = row[0]
                impression_count = int(row[1])
                total_impressions += impression_count
                
                self.upsert_entity_impressions(entity_id, unix_timestamp, impression_count, entity_type)
            
        except Exception as e:
            logger.error(f"Error during {entity_type[:-1]} impressions processing: {e}")
            raise
        
        processing_time = time.time() - processing_start_time
        logger.info(f"{entity_type.capitalize()} impressions processing completed for minute: {target_minute}")
        
        return entities_processed, total_impressions, processing_time

    def process_publisher_impressions(self, target_minute):
        """
        Legacy wrapper for backward compatibility.
        Process impression data from the previous minute and upsert to HCD publishers table.
        
        Args:
            target_minute (datetime): The minute timestamp to process impressions for
            
        Returns:
            tuple: (publishers_processed, total_impressions, processing_time)
        """
        return self.process_entity_impressions(target_minute, 'publishers')

    def process_advertiser_impressions(self, target_minute):
        """
        Process impression data from the previous minute and upsert to HCD advertisers table.
        
        Args:
            target_minute (datetime): The minute timestamp to process impressions for
            
        Returns:
            tuple: (advertisers_processed, total_impressions, processing_time)
        """
        return self.process_entity_impressions(target_minute, 'advertisers')
    
    def upsert_entity_impressions(self, entity_id, unix_timestamp, impression_count, entity_type='publishers'):
        """
        Upsert impression data for an entity (publisher or advertiser) in the HCD table.
        
        Args:
            entity_id (str): The entity ID (publisher_id or advertiser_id)
            unix_timestamp (int): Unix timestamp of the minute
            impression_count (int): Number of impressions for this minute
            entity_type (str): Type of entity - 'publishers' or 'advertisers'
        """
        try:
            # Define table and column names based on entity type
            table_name = entity_type
            id_column = f"{entity_type[:-1]}_id"  # Remove 's' from end (publishers -> publisher_id)
            
            # First, try to read existing record
            select_query = f"""
            SELECT impressions, last_updated
            FROM {table_name}
            WHERE {id_column} = '{entity_id}'
            """
            
            existing_row = self.cassandra_session.execute(select_query).one()
            
            current_time = datetime.now(timezone.utc)
            
            # Create impression entry as tuple [timestamp, count]
            new_impression_tuple = [int(unix_timestamp), int(impression_count)]

            if existing_row:
                # Update existing record
                existing_impressions_json = existing_row.impressions
                
                # Parse existing JSON or start with empty list
                try:
                    existing_impressions = json.loads(existing_impressions_json) if existing_impressions_json else []
                except (json.JSONDecodeError, TypeError):
                    existing_impressions = []

                # Add new impression entry to the list
                updated_impressions = existing_impressions + [new_impression_tuple]

                # Remove duplicates by timestamp (keeping the latest entry for each timestamp)
                seen_timestamps = set()
                deduplicated_impressions = []
                for impression in reversed(updated_impressions):  # Process from newest to oldest
                    if impression[0] not in seen_timestamps:  # impression[0] is timestamp
                        seen_timestamps.add(impression[0])
                        deduplicated_impressions.append(impression)
                
                # Convert back to sorted list (oldest first)
                impressions_list = sorted(deduplicated_impressions, key=lambda x: x[0])

                # Keep only the latest 90 entries
                if len(impressions_list) > 90:
                    impressions_list = impressions_list[-90:]
                
                # Convert to JSON string
                updated_impressions_json = json.dumps(impressions_list)
                
                # Update the record
                update_query = f"""
                UPDATE {table_name}
                SET impressions = %s, last_updated = %s
                WHERE {id_column} = %s
                """
                
                self.cassandra_session.execute(update_query, [updated_impressions_json, current_time, entity_id])
                logger.debug(f"Updated {entity_type[:-1]} {entity_id} with {impression_count} impressions for timestamp {unix_timestamp}")
                
            else:
                # Insert new record
                insert_query = f"""
                INSERT INTO {table_name} ({id_column}, impressions, conversions, last_updated)
                VALUES (%s, %s, %s, %s)
                """
                
                # Create JSON for new impressions list
                new_impressions_json = json.dumps([new_impression_tuple])
                empty_conversions_json = json.dumps([])
                
                self.cassandra_session.execute(insert_query, [entity_id, new_impressions_json, empty_conversions_json, current_time])
                logger.debug(f"Inserted new {entity_type[:-1]} {entity_id} with {impression_count} impressions for timestamp {unix_timestamp}")
                
        except Exception as e:
            logger.error(f"Error upserting {entity_type[:-1]} impressions for {entity_id}: {e}")
            raise

    def upsert_publisher_impressions(self, publisher_id, unix_timestamp, impression_count):
        """
        Legacy wrapper for backward compatibility.
        Upsert impression data for a publisher in the HCD publishers table.
        
        Args:
            publisher_id (str): The publisher ID
            unix_timestamp (int): Unix timestamp of the minute
            impression_count (int): Number of impressions for this minute
        """
        return self.upsert_entity_impressions(publisher_id, unix_timestamp, impression_count, 'publishers')
    
    def collect_iteration_stats(self, publishers_processed, advertisers_processed, publisher_impressions_total, advertiser_impressions_total, execution_time, publisher_processing_time, advertiser_processing_time, presto_queries_executed):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'publishers_processed': (current_timestamp, publishers_processed),
                'advertisers_processed': (current_timestamp, advertisers_processed),
                'publisher_impressions_total': (current_timestamp, publisher_impressions_total),
                'advertiser_impressions_total': (current_timestamp, advertiser_impressions_total),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'publisher_processing_time': (current_timestamp, round(publisher_processing_time, 2)),
                'advertiser_processing_time': (current_timestamp, round(advertiser_processing_time, 2)),
                'presto_queries_executed': (current_timestamp, presto_queries_executed)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to collect iteration stats: {e}")
            return {}
    
    def update_timeseries_stats(self, iteration_stats):
        """Update timeseries data with new stats, maintaining 90 datapoints"""
        try:
            for metric_name, (timestamp, value) in iteration_stats.items():
                if metric_name in self.stats_timeseries:
                    # Add new datapoint
                    self.stats_timeseries[metric_name].append([timestamp, value])
                    
                    # Maintain only the most recent 90 datapoints
                    if len(self.stats_timeseries[metric_name]) > 90:
                        self.stats_timeseries[metric_name] = self.stats_timeseries[metric_name][-90:]
            
            logger.debug(f"Updated timeseries stats with {len(iteration_stats)} metrics")
            
        except Exception as e:
            logger.error(f"Failed to update timeseries stats: {e}")
    
    def update_service_stats(self):
        """Update the services table with current stats"""
        try:
            # Serialize stats as JSON
            stats_json = json.dumps(self.stats_timeseries)
            
            # Update the service record with new stats
            update_query = f"""
                UPDATE {os.getenv('HCD_KEYSPACE')}.services 
                SET stats = %s, last_updated = %s
                WHERE name = %s
            """
            
            self.cassandra_session.execute(update_query, [
                stats_json,
                datetime.now(timezone.utc),
                'presto_to_hcd'
            ])
            
            logger.debug("Successfully updated service stats")
            
        except Exception as e:
            logger.error(f"Failed to update service stats: {e}")
    
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
                    target_minute = current_time.replace(second=0, microsecond=0) - timedelta(minutes=1)
                    
                    # Poll services table for configuration updates
                    self.poll_services_table()
                    
                    # Main processing tasks
                    publishers_processed, publisher_impressions_total, publisher_processing_time = self.process_publisher_impressions(target_minute)
                    advertisers_processed, advertiser_impressions_total, advertiser_processing_time = self.process_advertiser_impressions(target_minute)
                    
                    execution_time = time.time() - iteration_start
                    
                    # We executed 2 Presto queries (one for publishers, one for advertisers)
                    presto_queries_executed = 2
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        publishers_processed, advertisers_processed, 
                        publisher_impressions_total, advertiser_impressions_total,
                        execution_time, publisher_processing_time, advertiser_processing_time,
                        presto_queries_executed
                    )
                    
                    # Update timeseries data with new stats
                    self.update_timeseries_stats(iteration_stats)
                    
                    # Write stats to services table
                    self.update_service_stats()
                    
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
                    raise
                    # Sleep for a short time before retrying to prevent rapid failure loops
                    time.sleep(10)
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    insights = AffiliateJunctionInsights()
    insights.run()


if __name__ == "__main__":
    main()