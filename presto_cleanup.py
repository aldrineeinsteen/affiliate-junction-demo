#!/usr/bin/env python

import os
import sys
import time
import logging
import prestodb
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AffiliateJunctionDataCleanup:
    def __init__(self):
        self.presto_connection = None
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
        """Establish connection to Presto"""
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
    
    def cleanup_old_data(self):
        """Delete data older than 24 hours from both tables"""
        logger.info("Starting data cleanup process...")
        
        # Calculate cutoff time (24 hours ago)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_timestamp = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"Deleting data older than: {cutoff_timestamp} UTC")
        
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
            logger.info(f"Data cleanup completed successfully for data older than {cutoff_timestamp}")
            
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
            
            return impression_count, conversion_count
            
        except Exception as e:
            logger.error(f"Error getting table counts: {e}")
            return None, None
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.presto_connection:
                self.presto_connection.close()
                logger.info("Presto connection closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Affiliate Junction Data Cleanup Service")
            
            # Initialize connection
            self.connect_to_presto()
            
            logger.info("Entering main cleanup loop (runs every 300 seconds)...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Get current table counts before cleanup
                    pre_impression_count, pre_conversion_count = self.get_table_counts()
                    
                    # Perform cleanup
                    self.cleanup_old_data()
                    
                    # Get table counts after cleanup
                    post_impression_count, post_conversion_count = self.get_table_counts()
                    
                    # Log the difference if counts are available
                    if pre_impression_count is not None and post_impression_count is not None:
                        deleted_impressions = pre_impression_count - post_impression_count
                        deleted_conversions = pre_conversion_count - post_conversion_count
                        logger.info(f"Records deleted - Impressions: {deleted_impressions}, Conversions: {deleted_conversions}")
                    
                    execution_time = time.time() - iteration_start
                    
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