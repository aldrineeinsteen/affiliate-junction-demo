#!/usr/bin/env python

import os
import sys
import time
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


class AffiliateJunctionDataCleanup:
    def __init__(self):
        self.presto_connection = None
        self.presto_conn = None
        self.cassandra_connection = None
        self.cassandra_session = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
    
    def connect_to_databases(self):
        """Establish connections to both Cassandra and Presto"""
        try:
            # Connect to Cassandra for services table management
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Initialize services manager
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                "presto_cleanup", 
                "Data cleanup service for Presto tables"
            )
            
            # Connect to Presto
            self.presto_conn = PrestoConnection()
            self.presto_connection = self.presto_conn.connect()
            
            # Ensure Presto schema exists
            SchemaExecutor.execute_presto_schema(self.script_dir, self.presto_connection)
            
            logger.info("Connected to all databases successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to databases: {e}")
            sys.exit(1)
    
    def cleanup_old_data(self):
        """Delete data older than 24 hours from both tables"""
        logger.info("Starting data cleanup process...")
        
        # Calculate cutoff time (24 hours ago)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_timestamp = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"Deleting data older than: {cutoff_timestamp} UTC")
        
        # Track statistics for this iteration
        iteration_stats = {}
        cleanup_start_time = time.time()
        
        try:
            cursor = self.presto_connection.cursor()
            
            # Clean up impression_tracking table
            impression_delete_query = f"""
            DELETE FROM iceberg_data.affiliate_junction.impression_tracking
            WHERE timestamp < TIMESTAMP '{cutoff_timestamp}'
            """
            
            logger.info("Executing cleanup for impression_tracking table...")
            cursor.execute(impression_delete_query)
            
            # Get the number of affected rows (if supported)
            try:
                impression_result = cursor.fetchall()
                logger.info(f"Impression tracking cleanup completed. Result: {impression_result}")
            except Exception as e:
                logger.info("Impression tracking cleanup completed (result not available)")
            
            # Clean up conversion_tracking table
            conversion_delete_query = f"""
            DELETE FROM iceberg_data.affiliate_junction.conversion_tracking
            WHERE timestamp < TIMESTAMP '{cutoff_timestamp}'
            """
            
            logger.info("Executing cleanup for conversion_tracking table...")
            cursor.execute(conversion_delete_query)
            
            # Get the number of affected rows (if supported)
            try:
                conversion_result = cursor.fetchall()
                logger.info(f"Conversion tracking cleanup completed. Result: {conversion_result}")
            except Exception as e:
                logger.info("Conversion tracking cleanup completed (result not available)")
            
            cursor.close()
            
            # Record execution time for stats
            execution_time = time.time() - cleanup_start_time
            current_timestamp = datetime.now(timezone.utc).isoformat()
            
            iteration_stats['cleanup_execution_time_seconds'] = [current_timestamp, execution_time]
            iteration_stats['cleanup_cutoff_hours'] = [current_timestamp, 24]
            
            logger.info(f"Data cleanup completed successfully for data older than {cutoff_timestamp}")
            
            return iteration_stats
            
        except Exception as e:
            logger.error(f"Error during data cleanup: {e}")
            raise
    
    def get_table_counts(self):
        """Get current record counts for monitoring purposes"""
        try:
            cursor = self.presto_connection.cursor()
            
            # Count records in impression_tracking table
            cursor.execute("SELECT COUNT(*) FROM iceberg_data.affiliate_junction.impression_tracking")
            impression_count = cursor.fetchone()[0]
            
            # Count records in conversion_tracking table
            cursor.execute("SELECT COUNT(*) FROM iceberg_data.affiliate_junction.conversion_tracking")
            conversion_count = cursor.fetchone()[0]
            
            cursor.close()
            
            logger.info(f"Current table counts - Impressions: {impression_count}, Conversions: {conversion_count}")
            
            # Create stats for services table
            current_timestamp = datetime.now(timezone.utc).isoformat()
            count_stats = {
                'impression_records_count': [current_timestamp, impression_count],
                'conversion_records_count': [current_timestamp, conversion_count]
            }
            
            return impression_count, conversion_count, count_stats
            
        except Exception as e:
            logger.error(f"Error getting table counts: {e}")
            return None, None, {}
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.presto_conn:
                self.presto_conn.close()
            if self.cassandra_connection:
                self.cassandra_connection.close()
            logger.info("All connections closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Affiliate Junction Data Cleanup Service")
            
            # Initialize connections
            self.connect_to_databases()
            
            # Check for service record and configuration
            service_record = self.services_manager.poll_services_table()
            
            logger.info("Entering main cleanup loop (runs every 300 seconds)...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Get current table counts before cleanup
                    pre_impression_count, pre_conversion_count, pre_count_stats = self.get_table_counts()
                    
                    # Perform cleanup and collect stats
                    cleanup_stats = self.cleanup_old_data()
                    
                    # Get table counts after cleanup
                    post_impression_count, post_conversion_count, post_count_stats = self.get_table_counts()
                    
                    # Calculate and log the difference if counts are available
                    iteration_stats = {}
                    if pre_impression_count is not None and post_impression_count is not None:
                        deleted_impressions = pre_impression_count - post_impression_count
                        deleted_conversions = pre_conversion_count - post_conversion_count
                        logger.info(f"Records deleted - Impressions: {deleted_impressions}, Conversions: {deleted_conversions}")
                        
                        # Add deletion stats
                        current_timestamp = datetime.now(timezone.utc).isoformat()
                        iteration_stats.update({
                            'impressions_deleted_count': [current_timestamp, deleted_impressions],
                            'conversions_deleted_count': [current_timestamp, deleted_conversions]
                        })
                    
                    # Combine all stats
                    iteration_stats.update(cleanup_stats)
                    iteration_stats.update(post_count_stats)
                    
                    execution_time = time.time() - iteration_start
                    current_timestamp = datetime.now(timezone.utc).isoformat()
                    iteration_stats['total_execution_time_seconds'] = [current_timestamp, execution_time]
                    
                    # Update services table with stats
                    if iteration_stats:
                        self.services_manager.update_timeseries_stats(iteration_stats)
                        self.services_manager.update_service_stats()
                    
                    logger.info(f"Cleanup cycle completed in {execution_time:.2f} seconds. Sleeping for 300 seconds...")
                    time.sleep(300)  # Sleep for 300 seconds (5 minutes)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    logger.info("Waiting 60 seconds before retrying...")
                    time.sleep(60)  # Wait before retrying on error
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    cleanup_service = AffiliateJunctionDataCleanup()
    cleanup_service.run()


if __name__ == "__main__":
    main()