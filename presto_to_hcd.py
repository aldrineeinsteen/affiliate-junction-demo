#!/usr/bin/env python

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from cassandra import util

# Import shared modules
from affiliate_common import CassandraConnection, PrestoConnection, ServicesManager, SchemaExecutor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AffiliateJunctionInsights:
    def __init__(self):
        self.presto_connection = None
        self.presto_client = None
        self.cassandra_connection = None
        self.cassandra_session = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'publishers_processed': [],
            'advertisers_processed': [],
            'publisher_impressions_total': [],
            'advertiser_impressions_total': [],
            'advertiser_conversions_total': [],
            'execution_time_seconds': [],
            'publisher_processing_time': [],
            'advertiser_processing_time': [],
            'advertiser_conversion_processing_time': [],
            'presto_queries_executed': []
        }
        
    def connect_to_presto(self):
        """Establish connection to Presto - reusing configuration from hcd_to_presto.py"""
        try:
            presto_conn = PrestoConnection()
            self.presto_connection = presto_conn.connect()
            self.presto_client = presto_conn  # Keep reference for cleanup
            
            logger.info("Connected to Presto")
            
        except Exception as e:
            logger.error(f"Failed to connect to Presto: {e}")
            sys.exit(1)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster - reusing from hcd_to_presto.py"""
        try:
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Initialize services manager after connecting
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                'presto_to_hcd',
                'Insights service for aggregating impression data from Presto to Cassandra'
            )
            
            logger.info("Connected to Cassandra cluster")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            service_record = self.services_manager.poll_services_table()
                
        except Exception as e:
            logger.error(f"Failed to poll services table: {e}")
            # Continue with current settings if polling fails
    
    def insert_service_record(self):
        """Insert a new service record with empty settings"""
        try:
            self.services_manager.insert_service_record()
            
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
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Define the ID column name based on entity type (for Presto/Iceberg queries)
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
            
            # Execute query using the connection wrapper to capture metrics
            entity_impressions = self.presto_client.execute_query(
                query=impressions_query,
                query_description=f"Get {entity_type} impression totals for minute {target_minute}"
            )
            
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

    def process_entity_conversions(self, target_minute, entity_type='advertisers'):
        """
        Process conversion data from the previous minute and upsert to HCD entity table.
        Note: Conversions are typically only tracked for advertisers in affiliate marketing.
        
        Args:
            target_minute (datetime): The minute timestamp to process conversions for
            entity_type (str): Type of entity - 'advertisers' (conversions are advertiser-centric)
            
        Returns:
            tuple: (entities_processed, total_conversions, processing_time)
        """
        logger.info(f"Starting {entity_type[:-1]} conversions processing for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Define the ID column name based on entity type (for Presto/Iceberg queries)
            id_column = f"{entity_type[:-1]}s_id"  # advertisers -> advertisers_id
            
            # Format datetime values directly into the query (Presto doesn't support parameterized queries)
            conversions_query = f"""
            SELECT 
                {id_column},
                COUNT(*) as total_conversions
            FROM iceberg_data.affiliate_junction.conversion_tracking
            WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}' 
                AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                AND {id_column} IS NOT NULL
            GROUP BY {id_column}
            """
            
            # Execute query using the connection wrapper to capture metrics
            entity_conversions = self.presto_client.execute_query(
                query=conversions_query,
                query_description=f"Get {entity_type} conversion totals for minute {target_minute}"
            )
            
            entities_processed = len(entity_conversions)
            total_conversions = 0
            
            if not entity_conversions:
                logger.info(f"No conversions found for {entity_type} in minute: {target_minute}")
                processing_time = time.time() - processing_start_time
                return entities_processed, total_conversions, processing_time
            
            logger.info(f"Found conversions for {len(entity_conversions)} {entity_type} in minute: {target_minute}")
            
            # Process each entity's conversions
            unix_timestamp = int(target_minute.timestamp())
            
            for row in entity_conversions:
                entity_id = row[0]
                conversion_count = int(row[1])
                total_conversions += conversion_count
                
                self.upsert_entity_conversions(entity_id, unix_timestamp, conversion_count, entity_type)
            
        except Exception as e:
            logger.error(f"Error during {entity_type[:-1]} conversions processing: {e}")
            raise
        
        processing_time = time.time() - processing_start_time
        logger.info(f"{entity_type.capitalize()} conversions processing completed for minute: {target_minute}")
        
        return entities_processed, total_conversions, processing_time
    
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
            # Define table and column names based on entity type (for Cassandra queries)
            table_name = entity_type
            id_column = f"{entity_type[:-1]}_id"  # Remove 's' from end (publishers -> publisher_id, advertisers -> advertiser_id)
            
            # First, try to read existing record
            select_query = f"""
            SELECT impressions, last_updated
            FROM {table_name}
            WHERE {id_column} = '{entity_id}'
            """
            
            existing_row = self.cassandra_connection.execute_query(
                query=select_query,
                query_description=f"Get existing {entity_type[:-1]} {entity_id} record"
            )
            
            # Convert result to single row if needed
            existing_row = existing_row[0] if existing_row else None
            
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
                SET impressions = ?, last_updated = ?
                WHERE {id_column} = ?
                """
                
                self.cassandra_connection.execute_query(
                    query=update_query,
                    parameters=[updated_impressions_json, current_time, entity_id],
                    query_description=f"Update {entity_type[:-1]} {entity_id} impressions"
                )
                logger.debug(f"Updated {entity_type[:-1]} {entity_id} with {impression_count} impressions for timestamp {unix_timestamp}")
                
            else:
                # Insert new record
                insert_query = f"""
                INSERT INTO {table_name} ({id_column}, impressions, conversions, last_updated)
                VALUES (?, ?, ?, ?)
                """
                
                # Create JSON for new impressions list
                new_impressions_json = json.dumps([new_impression_tuple])
                empty_conversions_json = json.dumps([])
                
                self.cassandra_connection.execute_query(
                    query=insert_query,
                    parameters=[entity_id, new_impressions_json, empty_conversions_json, current_time],
                    query_description=f"Insert new {entity_type[:-1]} {entity_id}"
                )
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

    def upsert_entity_conversions(self, entity_id, unix_timestamp, conversion_count, entity_type='advertisers'):
        """
        Upsert conversion data for an entity (typically advertiser) in the HCD table.
        
        Args:
            entity_id (str): The entity ID (advertiser_id)
            unix_timestamp (int): Unix timestamp of the minute
            conversion_count (int): Number of conversions for this minute
            entity_type (str): Type of entity - 'advertisers' (conversions are advertiser-centric)
        """
        try:
            # Define table and column names based on entity type (for Cassandra queries)
            table_name = entity_type
            id_column = f"{entity_type[:-1]}_id"  # Remove 's' from end (advertisers -> advertiser_id)
            
            # First, try to read existing record
            select_query = f"""
            SELECT conversions, last_updated
            FROM {table_name}
            WHERE {id_column} = '{entity_id}'
            """
            
            existing_row = self.cassandra_connection.execute_query(
                query=select_query,
                query_description=f"Get existing {entity_type[:-1]} {entity_id} record"
            )
            
            # Convert result to single row if needed
            existing_row = existing_row[0] if existing_row else None
            
            current_time = datetime.now(timezone.utc)
            
            # Create conversion entry as tuple [timestamp, count]
            new_conversion_tuple = [int(unix_timestamp), int(conversion_count)]

            if existing_row:
                # Update existing record
                existing_conversions_json = existing_row.conversions
                
                # Parse existing JSON or start with empty list
                try:
                    existing_conversions = json.loads(existing_conversions_json) if existing_conversions_json else []
                except (json.JSONDecodeError, TypeError):
                    existing_conversions = []

                # Add new conversion entry to the list
                updated_conversions = existing_conversions + [new_conversion_tuple]

                # Remove duplicates by timestamp (keeping the latest entry for each timestamp)
                seen_timestamps = set()
                deduplicated_conversions = []
                for conversion in reversed(updated_conversions):  # Process from newest to oldest
                    if conversion[0] not in seen_timestamps:  # conversion[0] is timestamp
                        seen_timestamps.add(conversion[0])
                        deduplicated_conversions.append(conversion)
                
                # Convert back to sorted list (oldest first)
                conversions_list = sorted(deduplicated_conversions, key=lambda x: x[0])

                # Keep only the latest 90 entries
                if len(conversions_list) > 90:
                    conversions_list = conversions_list[-90:]
                
                # Convert to JSON string
                updated_conversions_json = json.dumps(conversions_list)
                
                # Update the record
                update_query = f"""
                UPDATE {table_name}
                SET conversions = ?, last_updated = ?
                WHERE {id_column} = ?
                """
                
                self.cassandra_connection.execute_query(
                    query=update_query,
                    parameters=[updated_conversions_json, current_time, entity_id],
                    query_description=f"Update {entity_type[:-1]} {entity_id} conversions"
                )
                logger.debug(f"Updated {entity_type[:-1]} {entity_id} with {conversion_count} conversions for timestamp {unix_timestamp}")
                
            else:
                # Insert new record
                insert_query = f"""
                INSERT INTO {table_name} ({id_column}, impressions, conversions, last_updated)
                VALUES (?, ?, ?, ?)
                """
                
                # Create JSON for new conversions list
                new_conversions_json = json.dumps([new_conversion_tuple])
                empty_impressions_json = json.dumps([])
                
                self.cassandra_connection.execute_query(
                    query=insert_query,
                    parameters=[entity_id, empty_impressions_json, new_conversions_json, current_time],
                    query_description=f"Insert new {entity_type[:-1]} {entity_id}"
                )
                logger.debug(f"Inserted new {entity_type[:-1]} {entity_id} with {conversion_count} conversions for timestamp {unix_timestamp}")
                
        except Exception as e:
            logger.error(f"Error upserting {entity_type[:-1]} conversions for {entity_id}: {e}")
            raise

    def process_advertiser_conversions(self, target_minute):
        """
        Process conversion data from the previous minute and upsert to HCD advertisers table.
        
        Args:
            target_minute (datetime): The minute timestamp to process conversions for
            
        Returns:
            tuple: (advertisers_processed, total_conversions, processing_time)
        """
        return self.process_entity_conversions(target_minute, 'advertisers')

    def process_publisher_conversion_rates(self, target_minute):
        """
        Calculate average conversion rates across all publishers for different time windows
        and store results in the key_value_store table.
        
        Args:
            target_minute (datetime): The current minute timestamp for calculating time windows
        """
        logger.info("Processing publisher conversion rates for multiple time windows")
        
        try:
            conversion_rates = {}
            time_windows = [30, 60, 90, 180]  # minutes
            
            for window_minutes in time_windows:
                start_time = target_minute - timedelta(minutes=window_minutes)
                end_time = target_minute
                
                # Query for total impressions and conversions across all publishers
                query = f"""
                WITH impressions_data AS (
                    SELECT SUM(impressions) as total_impressions
                    FROM iceberg_data.affiliate_junction.impression_tracking
                    WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'
                        AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                        AND publishers_id IS NOT NULL
                ),
                conversions_data AS (
                    SELECT COUNT(*) as total_conversions
                    FROM iceberg_data.affiliate_junction.conversion_tracking
                    WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'
                        AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                )
                SELECT 
                    i.total_impressions,
                    c.total_conversions,
                    CASE 
                        WHEN i.total_impressions > 0 THEN 
                            CAST(c.total_conversions AS DOUBLE) / CAST(i.total_impressions AS DOUBLE) * 100
                        ELSE 0.0
                    END as conversion_rate_percent
                FROM impressions_data i
                CROSS JOIN conversions_data c
                """
                
                result = self.presto_client.execute_query(
                    query=query,
                    query_description=f"Calculate publisher conversion rate for {window_minutes}-minute window"
                )
                
                if result and len(result) > 0:
                    row = result[0]
                    conversion_rate = float(row[2]) if row[2] is not None else 0.0
                    conversion_rates[f"{window_minutes}_min_pct"] = round(conversion_rate, 4)
                    logger.debug(f"{window_minutes}-minute conversion rate: {conversion_rate:.4f}%")
                else:
                    conversion_rates[f"{window_minutes}_min_pct"] = 0.0
            
            # Store results in key_value_store table
            current_time = datetime.now(timezone.utc)
            value_json = json.dumps(conversion_rates)
            
            upsert_query = """
            INSERT INTO key_value_store (key, value, last_update)
            VALUES (?, ?, ?)
            """
            
            self.cassandra_connection.execute_query(
                query=upsert_query,
                parameters=["publisher_all_conversion_rate", value_json, current_time],
                query_description="Store publisher conversion rates in key_value_store"
            )
            
            logger.info(f"Stored publisher conversion rates: {conversion_rates}")
            
        except Exception as e:
            logger.error(f"Error processing publisher conversion rates: {e}")
            raise

    def process_entity_metrics(self, target_minute, entity_type='publishers', metric_type='impressions'):
        """
        Generic method to process metrics (impressions or conversions) from Presto and upsert to HCD.
        This is a more generic version that could potentially replace the specific methods.
        
        Args:
            target_minute (datetime): The minute timestamp to process metrics for
            entity_type (str): Type of entity - 'publishers' or 'advertisers'
            metric_type (str): Type of metric - 'impressions' or 'conversions'
            
        Returns:
            tuple: (entities_processed, total_metrics, processing_time)
        """
        logger.info(f"Starting {entity_type[:-1]} {metric_type} processing for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Define the ID column name based on entity type (for Presto/Iceberg queries)
            id_column = f"{entity_type[:-1]}s_id"  # publishers -> publishers_id, advertisers -> advertisers_id
            
            # Define table and aggregation based on metric type
            if metric_type == 'impressions':
                table_name = 'impression_tracking'
                aggregation = 'SUM(impressions) as total_metrics'
                # Impressions can be tracked for both publishers and advertisers
            elif metric_type == 'conversions':
                table_name = 'conversion_tracking'
                aggregation = 'COUNT(*) as total_metrics'
                # Conversions are typically only for advertisers, but keeping it generic
            else:
                raise ValueError(f"Unsupported metric_type: {metric_type}")
            
            # Format datetime values directly into the query (Presto doesn't support parameterized queries)
            metrics_query = f"""
            SELECT 
                {id_column},
                {aggregation}
            FROM iceberg_data.affiliate_junction.{table_name}
            WHERE timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}' 
                AND timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                AND {id_column} IS NOT NULL
            GROUP BY {id_column}
            """
            
            # Execute query using the connection wrapper to capture metrics
            entity_metrics = self.presto_client.execute_query(
                query=metrics_query,
                query_description=f"Get {entity_type} {metric_type} totals for minute {target_minute}"
            )
            
            entities_processed = len(entity_metrics)
            total_metrics = 0
            
            if not entity_metrics:
                logger.info(f"No {metric_type} found for {entity_type} in minute: {target_minute}")
                processing_time = time.time() - processing_start_time
                return entities_processed, total_metrics, processing_time
            
            logger.info(f"Found {metric_type} for {len(entity_metrics)} {entity_type} in minute: {target_minute}")
            
            # Process each entity's metrics
            unix_timestamp = int(target_minute.timestamp())
            
            for row in entity_metrics:
                entity_id = row[0]
                metric_count = int(row[1])
                total_metrics += metric_count
                
                # Call the appropriate upsert method
                if metric_type == 'impressions':
                    self.upsert_entity_impressions(entity_id, unix_timestamp, metric_count, entity_type)
                elif metric_type == 'conversions':
                    self.upsert_entity_conversions(entity_id, unix_timestamp, metric_count, entity_type)
            
        except Exception as e:
            logger.error(f"Error during {entity_type[:-1]} {metric_type} processing: {e}")
            raise
        
        processing_time = time.time() - processing_start_time
        logger.info(f"{entity_type.capitalize()} {metric_type} processing completed for minute: {target_minute}")
        
        return entities_processed, total_metrics, processing_time
    
    def collect_iteration_stats(self, publishers_processed, advertisers_processed, publisher_impressions_total, advertiser_impressions_total, advertiser_conversions_total, execution_time, publisher_processing_time, advertiser_processing_time, advertiser_conversion_processing_time, presto_queries_executed):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'publishers_processed': (current_timestamp, publishers_processed),
                'advertisers_processed': (current_timestamp, advertisers_processed),
                'publisher_impressions_total': (current_timestamp, publisher_impressions_total),
                'advertiser_impressions_total': (current_timestamp, advertiser_impressions_total),
                'advertiser_conversions_total': (current_timestamp, advertiser_conversions_total),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'publisher_processing_time': (current_timestamp, round(publisher_processing_time, 2)),
                'advertiser_processing_time': (current_timestamp, round(advertiser_processing_time, 2)),
                'advertiser_conversion_processing_time': (current_timestamp, round(advertiser_conversion_processing_time, 2)),
                'presto_queries_executed': (current_timestamp, presto_queries_executed)
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
            # Get query metrics from database connections
            cassandra_metrics = self.cassandra_connection.get_query_metrics()
            presto_metrics = self.presto_client.get_query_metrics() if self.presto_client else None
            
            # Update services table with stats and query metrics
            self.services_manager.update_query_metrics(
                cassandra_metrics=cassandra_metrics,
                presto_metrics=presto_metrics
            )
            
            # Clear metrics after storing them
            self.cassandra_connection.clear_query_metrics()
            if self.presto_client:
                self.presto_client.clear_query_metrics()
            
        except Exception as e:
            logger.error(f"Failed to update service stats: {e}")
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.cassandra_connection:
                self.cassandra_connection.close()
                logger.info("Cassandra connection closed")
            
            if self.presto_client:
                self.presto_client.close()
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
                    advertisers_conversions_processed, advertiser_conversions_total, advertiser_conversion_processing_time = self.process_advertiser_conversions(target_minute)
                    self.process_publisher_conversion_rates(target_minute)
                    
                    execution_time = time.time() - iteration_start
                    
                    # We executed 7 Presto queries:
                    # - 1 for publishers impressions
                    # - 1 for advertisers impressions  
                    # - 1 for advertisers conversions
                    # - 4 for publisher conversion rates (30, 60, 90, 180 minute windows)
                    presto_queries_executed = 7
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        publishers_processed, advertisers_processed, 
                        publisher_impressions_total, advertiser_impressions_total, advertiser_conversions_total,
                        execution_time, publisher_processing_time, advertiser_processing_time, advertiser_conversion_processing_time,
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