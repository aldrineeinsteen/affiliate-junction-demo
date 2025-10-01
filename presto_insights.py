#!/usr/bin/env python

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta

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
        self.cassandra_connection = None
        self.cassandra_session = None
        self.presto_connection = None
        self.presto_client = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'conversions_processed': [],
            'conversions_identified': [],
            'execution_time_seconds': [],
            'conversions_identification_time': [],
            'presto_queries_executed': []
        }
        
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster for services table management"""
        try:
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Initialize services manager after connecting
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                'presto_insights',
                'Presto-based insights service for conversion identification and analytics'
            )
            
            logger.info("Connected to Cassandra cluster")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
        
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
    
    def process_conversions_identification(self, target_minute):
        """
        Process conversion identification for the previous minute.
        For each conversion, find the oldest matching impression within the last 90 minutes
        and populate the conversions_identified table.
        
        Args:
            target_minute (datetime): The minute timestamp to process conversions for
            
        Returns:
            tuple: (conversions_processed, conversions_identified, processing_time)
        """
        logger.info(f"Starting conversions identification processing for minute: {target_minute}")
        processing_start_time = time.time()
        
        try:
            start_time = target_minute
            end_time = target_minute + timedelta(minutes=1)
            
            # Define the time window for impression lookback (90 minutes before the conversion)
            impression_lookback_start = start_time - timedelta(minutes=90)
            
            # Query to find conversions and their matching oldest impressions
            # This query joins conversions with impressions on cookie_id and advertisers_id
            # and finds the oldest impression within the 90-minute lookback window
            conversions_identification_query = f"""
            WITH conversions_with_impressions AS (
                SELECT 
                    c.advertisers_id,
                    c.cookie_id,
                    c.timestamp as conversion_timestamp,
                    i.publishers_id,
                    i.timestamp as impression_timestamp,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.advertisers_id, c.cookie_id, c.timestamp 
                        ORDER BY i.timestamp ASC
                    ) as impression_rank
                FROM iceberg_data.affiliate_junction.conversion_tracking c
                INNER JOIN iceberg_data.affiliate_junction.impression_tracking i
                    ON c.cookie_id = i.cookie_id 
                    AND c.advertisers_id = i.advertisers_id
                WHERE c.timestamp >= TIMESTAMP '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'
                    AND c.timestamp < TIMESTAMP '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
                    AND i.timestamp >= TIMESTAMP '{impression_lookback_start.strftime('%Y-%m-%d %H:%M:%S')}'
                    AND i.timestamp < c.timestamp
            )
            SELECT 
                advertisers_id,
                publishers_id,
                cookie_id,
                conversion_timestamp,
                impression_timestamp,
                CAST(date_diff('second', impression_timestamp, conversion_timestamp) AS BIGINT) as time_to_conversion_seconds,
                CAST(CURRENT_TIMESTAMP AT TIME ZONE 'UTC' AS TIMESTAMP) as created_at
            FROM conversions_with_impressions
            WHERE impression_rank = 1
            """
            
            # Execute query using the connection wrapper to capture metrics
            conversion_identifications = self.presto_client.execute_query(
                query=conversions_identification_query,
                query_description=f"Identify conversions with oldest impressions for minute {target_minute}"
            )
            
            conversions_processed = len(conversion_identifications)
            conversions_identified = 0
            
            if not conversion_identifications:
                logger.info(f"No conversions with matching impressions found for minute: {target_minute}")
                processing_time = time.time() - processing_start_time
                return conversions_processed, conversions_identified, processing_time
            
            logger.info(f"Found {len(conversion_identifications)} conversions with matching impressions for minute: {target_minute}")
            
            # Insert identified conversions into the conversions_identified table
            if conversion_identifications:
                # Process in batches of 10,000 records for better performance
                batch_size = 10000
                for i in range(0, len(conversion_identifications), batch_size):
                    batch = conversion_identifications[i:i + batch_size]
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(conversion_identifications) + batch_size - 1) // batch_size

                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} records)")
                    
                    # Create a single INSERT statement with multiple VALUES clauses
                    values_list = []
                    for row in batch:
                        # row indices: advertisers_id, publishers_id, cookie_id, conversion_timestamp, impression_timestamp, time_to_conversion_seconds, created_at
                        # Convert timestamp values to proper format without timezone
                        conversion_ts = str(row[3]) if isinstance(row[3], str) else row[3].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        impression_ts = str(row[4]) if isinstance(row[4], str) else row[4].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        created_at_ts = str(row[6]) if isinstance(row[6], str) else row[6].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        
                        values_list.append(f"('{row[0]}', '{row[1]}', '{row[2]}', TIMESTAMP '{conversion_ts}', TIMESTAMP '{impression_ts}', {row[5]}, TIMESTAMP '{created_at_ts}')")
                    
                    values_clause = ", ".join(values_list)
                    batch_insert_query = f"""
                    INSERT INTO iceberg_data.affiliate_junction.conversions_identified 
                    (advertisers_id, publishers_id, cookie_id, conversion_timestamp, impression_timestamp, time_to_conversion_seconds, created_at)
                    VALUES {values_clause}
                    """
                    
                    # Execute the batch using the wrapper
                    self.presto_client.execute_query(
                        query=batch_insert_query,
                        query_description=f"Batch insert {len(batch)} identified conversion records"
                    )
                    
                    conversions_identified += len(batch)
                
                logger.info(f"Successfully inserted {conversions_identified} identified conversion records to Presto")
            
        except Exception as e:
            logger.error(f"Error during conversions identification: {e}")
            raise
        
        processing_time = time.time() - processing_start_time
        logger.info(f"Conversions identification completed for minute: {target_minute}")
        
        return conversions_processed, conversions_identified, processing_time
    
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
    
    def collect_iteration_stats(self, conversions_processed, conversions_identified, execution_time, conversions_identification_time, presto_queries_executed):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'conversions_processed': (current_timestamp, conversions_processed),
                'conversions_identified': (current_timestamp, conversions_identified),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'conversions_identification_time': (current_timestamp, round(conversions_identification_time, 2)),
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
            # Get query metrics from Presto connection
            presto_metrics = self.presto_client.get_query_metrics() if self.presto_client else None
            
            # Update services table with stats and query metrics
            self.services_manager.update_query_metrics(
                cassandra_metrics=None,
                presto_metrics=presto_metrics
            )
            
            # Clear metrics after storing them
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
            self.connect_to_cassandra()
            self.connect_to_presto()
            
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
                    # Process conversions identification for the previous minute
                    conversions_processed, conversions_identified, conversions_identification_time = self.process_conversions_identification(target_minute)
                        
                    execution_time = time.time() - iteration_start
                    
                    # We executed 1 Presto query for conversions identification
                    presto_queries_executed = 1
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        conversions_processed, conversions_identified,
                        execution_time, conversions_identification_time,
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