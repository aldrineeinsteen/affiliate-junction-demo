#!/usr/bin/env python

import os
import sys
import time
import json
import logging
import concurrent.futures
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
            'publisher_conversions_total': [],
            'execution_time_seconds': [],
            'publisher_processing_time': [],
            'advertiser_processing_time': [],
            'advertiser_conversion_processing_time': [],
            'publisher_conversion_processing_time': [],
            'presto_queries_executed': []
        }
        
    def connect_to_presto(self):
        """Establish connection to Presto"""
        try:
            presto_conn = PrestoConnection()
            self.presto_connection = presto_conn.connect()
            self.presto_client = presto_conn  # Keep reference for cleanup
            
            logger.info("Connected to Presto")
            
        except Exception as e:
            logger.error(f"Failed to connect to Presto: {e}")
            sys.exit(1)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster"""
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
            # Define the ID column name based on entity type (for Presto/Iceberg queries)
            id_column = f"{entity_type[:-1]}s_id"  # advertisers -> advertisers_id
            
            # Format datetime values directly into the query (Presto doesn't support parameterized queries)
            conversions_query = f"""
            SELECT 
                {id_column},
                COUNT(*) as total_conversions
            FROM iceberg_data.affiliate_junction.conversion_tracking
            WHERE timestamp = TIMESTAMP '{target_minute.strftime('%Y-%m-%d %H:%M:%S')}' 
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

    def upsert_publisher_conversions_identified(self, publisher_id, unix_timestamp, conversion_count):
        """
        Upsert conversion data for a publisher from conversions_identified table into the HCD publishers table.
        This updates the conversions column specifically.
        
        Args:
            publisher_id (str): The publisher ID
            unix_timestamp (int): Unix timestamp of the minute
            conversion_count (int): Number of conversions for this minute
        """
        try:
            # First, try to read existing record
            select_query = """
            SELECT impressions, conversions, last_updated
            FROM publishers
            WHERE publisher_id = ?
            """
            
            existing_row = self.cassandra_connection.execute_query(
                query=select_query,
                parameters=[publisher_id],
                query_description=f"Get existing publisher {publisher_id} record"
            )
            
            # Convert result to single row if needed
            existing_row = existing_row[0] if existing_row else None
            
            current_time = datetime.now(timezone.utc)
            
            # Create conversion entry as tuple [timestamp, count]
            new_conversion_tuple = [int(unix_timestamp), int(conversion_count)]

            if existing_row:
                # Update existing record
                existing_impressions_json = existing_row.impressions
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
                
                # Update the record - keep existing impressions, update conversions
                update_query = """
                UPDATE publishers
                SET conversions = ?, last_updated = ?
                WHERE publisher_id = ?
                """
                
                self.cassandra_connection.execute_query(
                    query=update_query,
                    parameters=[updated_conversions_json, current_time, publisher_id],
                    query_description=f"Update publisher {publisher_id} conversions from conversions_identified"
                )
                logger.debug(f"Updated publisher {publisher_id} with {conversion_count} conversions from conversions_identified for timestamp {unix_timestamp}")
                
            else:
                # Insert new record
                insert_query = """
                INSERT INTO publishers (publisher_id, impressions, conversions, last_updated)
                VALUES (?, ?, ?, ?)
                """
                
                # Create JSON for new conversions list
                new_conversions_json = json.dumps([new_conversion_tuple])
                empty_impressions_json = json.dumps([])
                
                self.cassandra_connection.execute_query(
                    query=insert_query,
                    parameters=[publisher_id, empty_impressions_json, new_conversions_json, current_time],
                    query_description=f"Insert new publisher {publisher_id} with conversions from conversions_identified"
                )
                logger.debug(f"Inserted new publisher {publisher_id} with {conversion_count} conversions from conversions_identified for timestamp {unix_timestamp}")
                
        except Exception as e:
            logger.error(f"Error upserting publisher conversions from conversions_identified for {publisher_id}: {e}")
            raise

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

    def process_publisher_conversions_identified(self, target_minute):
        """
        Process conversions from conversions_identified table by impression_timestamp for the previous 90 minutes,
        filtering for the target minute, and upsert to HCD publishers table.
        
        Args:
            target_minute (datetime): The minute timestamp to process conversions for
            
        Returns:
            tuple: (publishers_processed, total_conversions, processing_time)
        """
        logger.info(f"Starting publisher conversions processing from conversions_identified for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            # Query the previous 90 minutes from impression_timestamp
            start_time = target_minute - timedelta(minutes=90)
            # Filter for conversions that have impression_timestamp in the target minute
            target_start = target_minute
            target_end = target_minute + timedelta(minutes=1)
            
            # Query conversions_identified table for publisher conversions
            # Filter by impression_timestamp for the previous 90 minutes, then count conversions for target minute
            conversions_query = f"""
            SELECT 
                publishers_id,
                COUNT(*) as total_conversions
            FROM iceberg_data.affiliate_junction.conversions_identified
            WHERE impression_timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'
                AND impression_timestamp < TIMESTAMP '{target_end.strftime('%Y-%m-%d %H:%M:%S')}'
                AND publishers_id IS NOT NULL
            GROUP BY publishers_id
            """
            
            # Execute query using the connection wrapper to capture metrics
            publisher_conversions = self.presto_client.execute_query(
                query=conversions_query,
                query_description=f"Get publisher conversion totals from conversions_identified for minute {target_minute}"
            )
            
            publishers_processed = len(publisher_conversions)
            total_conversions = 0
            
            if not publisher_conversions:
                logger.info(f"No publisher conversions found in conversions_identified for minute: {target_minute}")
                processing_time = time.time() - processing_start_time
                return publishers_processed, total_conversions, processing_time
            
            logger.info(f"Found conversions for {len(publisher_conversions)} publishers in conversions_identified for minute: {target_minute}")
            
            # Process each publisher's conversions
            unix_timestamp = int(target_minute.timestamp())
            
            for row in publisher_conversions:
                publisher_id = row[0]
                conversion_count = int(row[1])
                total_conversions += conversion_count
                
                self.upsert_publisher_conversions_identified(publisher_id, unix_timestamp, conversion_count)
            
        except Exception as e:
            logger.error(f"Error during publisher conversions processing from conversions_identified: {e}")
            raise
        
        processing_time = time.time() - processing_start_time
        logger.info(f"Publisher conversions processing from conversions_identified completed for minute: {target_minute}")
        
        return publishers_processed, total_conversions, processing_time



    def process_conversion_rate_window(self, target_minute, window_minutes):
        """
        Calculate conversion rate for a specific time window (helper for parallel processing).
        
        Args:
            target_minute (datetime): The current minute timestamp
            window_minutes (int): Time window in minutes (30, 60, 90, 180)
            
        Returns:
            tuple: (window_minutes, conversion_rate)
        """
        try:
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
                logger.debug(f"{window_minutes}-minute conversion rate: {conversion_rate:.4f}%")
                return window_minutes, round(conversion_rate, 4)
            else:
                return window_minutes, 0.0
                
        except Exception as e:
            logger.error(f"Error calculating conversion rate for {window_minutes}-minute window: {e}")
            return window_minutes, 0.0

    def process_publisher_conversion_rates_parallel(self, target_minute):
        """
        Calculate average conversion rates across all publishers for different time windows
        using parallel execution and store results in the key_value_store table.
        
        Args:
            target_minute (datetime): The current minute timestamp for calculating time windows
        """
        logger.info("Processing publisher conversion rates for multiple time windows (parallel)")
        
        try:
            # time_windows = [30, 60, 90, 180]  # minutes
            time_windows = [90]  # minutes
            conversion_rates = {}
            
            # Execute all conversion rate queries in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(time_windows)) as executor:
                # Submit all conversion rate calculation tasks
                future_to_window = {
                    executor.submit(self.process_conversion_rate_window, target_minute, window): window
                    for window in time_windows
                }
                
                # Collect results
                for future in concurrent.futures.as_completed(future_to_window):
                    window_minutes, conversion_rate = future.result()
                    conversion_rates[f"{window_minutes}_min_pct"] = conversion_rate
            
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
            
            logger.info(f"Stored publisher conversion rates (parallel): {conversion_rates}")
            
        except Exception as e:
            logger.error(f"Error processing publisher conversion rates (parallel): {e}")
            raise

    def get_presto_table_sizes(self):
        """
        Enumerate all tables in the Presto affiliate_junction schema and get count(*) for each table.
        Store results in key_value_store table with key 'presto_table_counts'.
        """
        logger.info("Starting Presto table size enumeration")
        
        try:
            # First, get all tables in the affiliate_junction schema
            tables_query = """
            SHOW TABLES FROM iceberg_data.affiliate_junction
            """
            
            tables_result = self.presto_client.execute_query(
                query=tables_query,
                query_description="Get all tables in affiliate_junction schema"
            )
            
            if not tables_result:
                logger.warning("No tables found in affiliate_junction schema")
                return
            
            table_counts = {}
            
            # Get count for each table
            for table_row in tables_result:
                table_name = table_row[0]  # Table name is in the first column
                
                try:
                    count_query = f"""
                    SELECT COUNT(*) as row_count
                    FROM iceberg_data.affiliate_junction.{table_name}
                    """
                    
                    count_result = self.presto_client.execute_query(
                        query=count_query,
                        query_description=f"Get row count for table {table_name}"
                    )
                    
                    if count_result and len(count_result) > 0:
                        row_count = int(count_result[0][0])
                        table_counts[table_name] = row_count
                        logger.debug(f"Table {table_name}: {row_count} rows")
                    else:
                        table_counts[table_name] = 0
                        logger.warning(f"Could not get count for table {table_name}")
                        
                except Exception as e:
                    logger.error(f"Error counting rows in table {table_name}: {e}")
                    table_counts[table_name] = -1  # Indicate error
            
            # Store results in key_value_store table
            current_time = datetime.now(timezone.utc)
            value_json = json.dumps(table_counts)
            
            upsert_query = """
            INSERT INTO key_value_store (key, value, last_update)
            VALUES (?, ?, ?)
            """
            
            self.cassandra_connection.execute_query(
                query=upsert_query,
                parameters=["presto_table_counts", value_json, current_time],
                query_description="Store Presto table counts in key_value_store"
            )
            
            logger.info(f"Stored Presto table counts: {table_counts}")
            
        except Exception as e:
            logger.error(f"Error getting Presto table sizes: {e}")
            raise

    def process_minute_parallel(self, target_minute):
        """
        Process all data for a target minute using parallel execution.
        
        Args:
            target_minute (datetime): The minute timestamp to process
            
        Returns:
            dict: Results from all processing tasks
        """
        logger.info(f"Starting parallel processing for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            # Check if we should run table size enumeration (every 10 minutes)
            run_table_sizes = target_minute.minute % 10 == 0
            
            # Execute all processing tasks in parallel (main tasks + conversion rates + optional table sizes)
            max_workers = 6 if run_table_sizes else 5
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all main processing tasks
                publisher_impressions_future = executor.submit(self.process_publisher_impressions, target_minute)
                advertiser_impressions_future = executor.submit(self.process_advertiser_impressions, target_minute)
                advertiser_conversions_future = executor.submit(self.process_advertiser_conversions, target_minute)
                publisher_conversions_future = executor.submit(self.process_publisher_conversions_identified, target_minute)
                
                # Submit conversion rates processing in parallel (no dependency on main tasks)
                conversion_rates_future = executor.submit(self.process_publisher_conversion_rates_parallel, target_minute)
                
                # Submit table sizes processing every 10 minutes
                table_sizes_future = None
                if run_table_sizes:
                    table_sizes_future = executor.submit(self.get_presto_table_sizes)
                    logger.info("Started table size enumeration task (runs every 5 minutes)")
                
                # Wait for all main tasks to complete
                publishers_processed, publisher_impressions_total, publisher_processing_time = publisher_impressions_future.result()
                advertisers_processed, advertiser_impressions_total, advertiser_processing_time = advertiser_impressions_future.result()
                advertisers_conversions_processed, advertiser_conversions_total, advertiser_conversion_processing_time = advertiser_conversions_future.result()
                publishers_conversions_processed, publisher_conversions_total, publisher_conversion_processing_time = publisher_conversions_future.result()
                
                # Wait for conversion rates to complete
                conversion_rates_future.result()
                
                # Wait for table sizes to complete if it was started
                if table_sizes_future:
                    table_sizes_future.result()
                    logger.info("Table size enumeration completed")
            
            # Calculate total processing time
            total_processing_time = time.time() - processing_start_time
            
            # Calculate Presto queries executed based on what was run
            # Base queries: 4 main tasks + 1 conversion rate = 5 queries
            presto_queries_executed = 5
            
            # Add table size queries if they were executed (1 SHOW TABLES + N COUNT queries)
            if run_table_sizes:
                # We don't know the exact number of tables until runtime, but we'll estimate
                # The actual count will be tracked by the presto_client query metrics
                presto_queries_executed += 1  # For the SHOW TABLES query
                # Individual table counts will be tracked by the connection wrapper
            
            # Return results in same format as sequential processing
            return {
                'publishers_processed': publishers_processed,
                'publisher_impressions_total': publisher_impressions_total,
                'publisher_processing_time': publisher_processing_time,
                'advertisers_processed': advertisers_processed,
                'advertiser_impressions_total': advertiser_impressions_total,
                'advertiser_processing_time': advertiser_processing_time,
                'advertisers_conversions_processed': advertisers_conversions_processed,
                'advertiser_conversions_total': advertiser_conversions_total,
                'advertiser_conversion_processing_time': advertiser_conversion_processing_time,
                'publishers_conversions_processed': publishers_conversions_processed,
                'publisher_conversions_total': publisher_conversions_total,
                'publisher_conversion_processing_time': publisher_conversion_processing_time,
                'total_processing_time': total_processing_time,
                'presto_queries_executed': presto_queries_executed
            }
            
        except Exception as e:
            logger.error(f"Error during parallel processing for minute {target_minute}: {e}")
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
    
    def collect_iteration_stats(self, publishers_processed, advertisers_processed, publisher_impressions_total, advertiser_impressions_total, advertiser_conversions_total, publisher_conversions_total, execution_time, publisher_processing_time, advertiser_processing_time, advertiser_conversion_processing_time, publisher_conversion_processing_time, presto_queries_executed):
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
                'publisher_conversions_total': (current_timestamp, publisher_conversions_total),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'publisher_processing_time': (current_timestamp, round(publisher_processing_time, 2)),
                'advertiser_processing_time': (current_timestamp, round(advertiser_processing_time, 2)),
                'advertiser_conversion_processing_time': (current_timestamp, round(advertiser_conversion_processing_time, 2)),
                'publisher_conversion_processing_time': (current_timestamp, round(publisher_conversion_processing_time, 2)),
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
                    
                    # Main processing tasks - use parallel execution
                    results = self.process_minute_parallel(target_minute)
                    
                    # Extract results for stats collection
                    publishers_processed = results['publishers_processed']
                    publisher_impressions_total = results['publisher_impressions_total']
                    publisher_processing_time = results['publisher_processing_time']
                    advertisers_processed = results['advertisers_processed']
                    advertiser_impressions_total = results['advertiser_impressions_total']
                    advertiser_processing_time = results['advertiser_processing_time']
                    advertisers_conversions_processed = results['advertisers_conversions_processed']
                    advertiser_conversions_total = results['advertiser_conversions_total']
                    advertiser_conversion_processing_time = results['advertiser_conversion_processing_time']
                    publishers_conversions_processed = results['publishers_conversions_processed']
                    publisher_conversions_total = results['publisher_conversions_total']
                    publisher_conversion_processing_time = results['publisher_conversion_processing_time']
                    presto_queries_executed = results['presto_queries_executed']
                    
                    execution_time = time.time() - iteration_start
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        publishers_processed, advertisers_processed, 
                        publisher_impressions_total, advertiser_impressions_total, advertiser_conversions_total, publisher_conversions_total,
                        execution_time, publisher_processing_time, advertiser_processing_time, advertiser_conversion_processing_time, publisher_conversion_processing_time,
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
                        logger.info("Processing time exceeded 1 minute, no sleep required")
                        sleep_time = 0
                    
                    logger.info(f"Parallel processing completed in {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until 45 seconds past next minute ({next_minute_plus_45.strftime('%H:%M:%S')})...")
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