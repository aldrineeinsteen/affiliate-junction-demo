#!/usr/bin/env python

import os
import sys
import time
import logging
import requests
import json
from datetime import datetime, timezone, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import count, lit

# Import shared modules
from affiliate_common import CassandraConnection, PrestoConnection, ServicesManager, SchemaExecutor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AffiliateJunctionETL:
    def __init__(self):
        self.cassandra_connection = None
        self.cassandra_session = None
        self.presto_connection = None
        self.presto_client = None
        self.spark = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'impressions_processed': [],
            'conversions_processed': [],
            'impressions_aggregated': [],
            'impressions_batches': [],
            'conversions_batches': [],
            'execution_time_seconds': [],
            'impressions_rollup_time': [],
            'conversions_identification_time': []
        }
        
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster - reusing from generate_traffic.py"""
        try:
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Initialize services manager after connecting
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                'hcd_to_presto',
                'ETL service for transferring and aggregating data from Cassandra to Presto/Iceberg'
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
    
    def connect_to_presto(self):
        """Establish connection to Presto"""
        try:
            self.presto_client = PrestoConnection()
            self.presto_connection = self.presto_client.connect()
            
            logger.info("Connected to Presto")
            
        except Exception as e:
            logger.error(f"Failed to connect to Presto: {e}")
            sys.exit(1)
    
    def initialize_spark(self):
        """Initialize Spark session"""
        try:
            self.spark = SparkSession.builder \
                .appName("AffiliateJunctionETL") \
                .config("spark.sql.adaptive.enabled", "true") \
                .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
                .config("spark.hadoop.native.lib", "false") \
                .config("spark.sql.execution.arrow.pyspark.enabled", "false") \
                .getOrCreate()
            
            # Set log level to reduce noise
            self.spark.sparkContext.setLogLevel("WARN")
            
            logger.info("Spark session initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Spark: {e}")
            sys.exit(1)
    
    def execute_presto_schema(self):
        """Execute the Presto schema file to create tables"""
        try:
            SchemaExecutor.execute_presto_schema(self.script_dir, self.presto_connection)
            
        except Exception as e:
            logger.error(f"Failed to execute Presto schema: {e}")
            raise
    
    def rollup_impressions(self):
        """Rollup impressions from Cassandra to Presto"""
        logger.info("Starting impressions rollup process...")
        rollup_start_time = time.time()
        
        # Get current minute timestamp for processing
        # Calculate the previous minute (rounded down to the last full minute)
        previous_minute = (datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1))
        
        try:
            all_impressions = []
            for bucket in range(int(os.getenv("AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"))):
                query = f"""
                SELECT bucket_date, publishers_id, advertisers_id, cookie_id
                FROM impressions_by_minute
                WHERE bucket_date = '{previous_minute}' AND bucket = {bucket}
                """
                
                rows = self.cassandra_connection.execute_query(
                    query=query,
                    query_description=f"Fetch impressions from bucket {bucket} for {previous_minute}"
                )
                for row in rows:
                    all_impressions.append({
                        'bucket_date': row.bucket_date,
                        'publishers_id': row.publishers_id,
                        'advertisers_id': row.advertisers_id,
                        'cookie_id': row.cookie_id,
                    })
            
            impressions_processed = len(all_impressions)
            
            if not all_impressions:
                logger.info(f"No impressions found for minute: {previous_minute}")
                rollup_time = time.time() - rollup_start_time
                return impressions_processed, 0, 0, rollup_time
            
            logger.info(f"Found {len(all_impressions)} raw impression records for minute: {previous_minute}")
            
            # Only proceed with Spark operations if we have data
            try:
                impressions_df = self.spark.createDataFrame(all_impressions)
                
                # Aggregate by publishers_id, advertisers_id, cookie_id to count impressions
                # Multiple records for the same combo within the time period should be counted
                # Include bucket_date in groupBy since all records should have the same bucket_date
                final_df = impressions_df.groupBy("publishers_id", "advertisers_id", "cookie_id", "bucket_date") \
                    .agg(count(lit(1)).alias("impressions")) \
                    .withColumnRenamed("bucket_date", "timestamp")
                
                impressions_aggregated = final_df.count()
                logger.info(f"Aggregated to {impressions_aggregated} unique publisher-advertiser-cookie combinations")
            except Exception as spark_error:
                logger.error(f"Error in Spark operations: {spark_error}")
                logger.error(f"Sample data: {all_impressions[0] if all_impressions else 'No data'}")
                # Return early on Spark errors
                rollup_time = time.time() - rollup_start_time
                return impressions_processed, 0, 0, rollup_time
            
            impressions_batches = 0
            # Write aggregated data to Presto impression_tracking table
            if final_df.count() > 0:
                # Convert Spark DataFrame to list of tuples for Presto insertion
                rows_to_insert = final_df.collect()
                
                insert_query = """
                INSERT INTO iceberg_data.affiliate_junction.impression_tracking 
                (publishers_id, cookie_id, advertisers_id, timestamp, impressions)
                VALUES (?, ?, ?, ?, ?)
                """
                
                # Process in batches of 10,000 records for better performance
                batch_size = 10000
                for i in range(0, len(rows_to_insert), batch_size):
                    batch = rows_to_insert[i:i + batch_size]
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(rows_to_insert) + batch_size - 1) // batch_size
                    impressions_batches = total_batches

                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} records)")
                    
                    # Create a single INSERT statement with multiple VALUES clauses
                    values_list = []
                    for row in batch:
                        values_list.append(f"('{row.publishers_id}', '{row.cookie_id}', '{row.advertisers_id}', TIMESTAMP '{row.timestamp}', {row.impressions})")
                    
                    values_clause = ", ".join(values_list)
                    batch_insert_query = f"""
                    INSERT INTO iceberg_data.affiliate_junction.impression_tracking 
                    (publishers_id, cookie_id, advertisers_id, timestamp, impressions)
                    VALUES {values_clause}
                    """
                    
                    # Execute the batch using the wrapper
                    self.presto_client.execute_query(
                        query=batch_insert_query,
                        query_description=f"Batch insert {len(batch)} aggregated impression records"
                    )
                
                logger.info(f"Successfully inserted {len(rows_to_insert)} aggregated impression records to Presto")
            
        except Exception as e:
            logger.error(f"Error during impressions rollup: {e}")
            raise
        
        rollup_time = time.time() - rollup_start_time
        logger.info(f"Impressions rollup completed for minute: {previous_minute}")
        
        return impressions_processed, impressions_aggregated, impressions_batches, rollup_time
    
    def identify_conversions(self):
        """Identify conversions by reading from Cassandra and writing to Presto"""
        logger.info("Starting conversions identification process...")
        conversions_start_time = time.time()
        
        # Get current minute timestamp for processing
        previous_minute = (datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1))
        
        try:
            all_conversions = []
            for bucket in range(int(os.getenv("AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"))):
                query = f"""
                SELECT bucket_date, ts, publishers_id, advertisers_id, cookie_id, conversion_id
                FROM conversions_by_minute
                WHERE bucket_date = '{previous_minute}' AND bucket = {bucket}
                """
                
                rows = self.cassandra_connection.execute_query(
                    query=query,
                    query_description=f"Fetch conversions from bucket {bucket} for {previous_minute}"
                )
                for row in rows:
                    all_conversions.append({
                        'bucket_date': row.bucket_date,
                        'ts': row.ts,
                        'publishers_id': row.publishers_id,
                        'advertisers_id': row.advertisers_id,
                        'cookie_id': row.cookie_id,
                        'conversion_id': row.conversion_id
                    })
            
            conversions_processed = len(all_conversions)
            
            if not all_conversions:
                logger.info(f"No conversions found for minute: {previous_minute}")
                conversions_time = time.time() - conversions_start_time
                return conversions_processed, 0, conversions_time
            
            logger.info(f"Found {len(all_conversions)} raw conversion records for minute: {previous_minute}")
            
            # Write conversion data directly to Presto conversion_tracking table
            # Each conversion is a distinct event, so no aggregation needed
            
            conversions_batches = 0
            # Process in batches of 10,000 records for better performance
            batch_size = 10000
            for i in range(0, len(all_conversions), batch_size):
                batch = all_conversions[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(all_conversions) + batch_size - 1) // batch_size
                conversions_batches = total_batches

                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} records)")
                
                # Create a single INSERT statement with multiple VALUES clauses
                values_list = []
                for row in batch:
                    # Use bucket_date as timestamp since it represents the minute bucket
                    values_list.append(f"('{row['advertisers_id']}', TIMESTAMP '{row['bucket_date']}', '{row['cookie_id']}')")
                
                values_clause = ", ".join(values_list)
                batch_insert_query = f"""
                INSERT INTO iceberg_data.affiliate_junction.conversion_tracking 
                (advertisers_id, timestamp, cookie_id)
                VALUES {values_clause}
                """
                
                # Execute the batch using the wrapper
                self.presto_client.execute_query(
                    query=batch_insert_query,
                    query_description=f"Batch insert {len(batch)} conversion records"
                )
            
            logger.info(f"Successfully inserted {len(all_conversions)} conversion records to Presto")
            
        except Exception as e:
            logger.error(f"Error during conversions identification: {e}")
            raise
        
        conversions_time = time.time() - conversions_start_time
        logger.info(f"Conversions identification completed for minute: {previous_minute}")
        
        return conversions_processed, conversions_batches, conversions_time
    
    def collect_iteration_stats(self, impressions_processed, conversions_processed, impressions_aggregated, impressions_batches, conversions_batches, execution_time, impressions_rollup_time, conversions_identification_time):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'impressions_processed': (current_timestamp, impressions_processed),
                'conversions_processed': (current_timestamp, conversions_processed),
                'impressions_aggregated': (current_timestamp, impressions_aggregated),
                'impressions_batches': (current_timestamp, impressions_batches),
                'conversions_batches': (current_timestamp, conversions_batches),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'impressions_rollup_time': (current_timestamp, round(impressions_rollup_time, 2)),
                'conversions_identification_time': (current_timestamp, round(conversions_identification_time, 2))
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
            # Get query metrics from both database connections
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
                
            if self.spark:
                self.spark.stop()
                logger.info("Spark session stopped")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Affiliate Junction ETL")
            
            # Initialize connections
            self.connect_to_cassandra()
            self.connect_to_presto()
            self.initialize_spark()
            
            # Execute Presto schema
            self.execute_presto_schema()
            
            logger.info("Entering main loop...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Poll services table for configuration updates
                    self.poll_services_table()
                    
                    # Task 1: Rollup impressions
                    impressions_processed, impressions_aggregated, impressions_batches, impressions_rollup_time = self.rollup_impressions()
                    
                    # Task 2: Identify conversions
                    conversions_processed, conversions_batches, conversions_identification_time = self.identify_conversions()
                    
                    execution_time = time.time() - iteration_start
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        impressions_processed, conversions_processed, impressions_aggregated,
                        impressions_batches, conversions_batches, execution_time,
                        impressions_rollup_time, conversions_identification_time
                    )
                    
                    # Update timeseries data with new stats
                    self.update_timeseries_stats(iteration_stats)
                    
                    # Write stats to services table
                    self.update_service_stats()
                    
                    # Calculate time until 5 seconds into the next minute
                    current_time = datetime.now(timezone.utc)
                    next_minute_plus_5 = (current_time.replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=5))
                    sleep_time = (next_minute_plus_5 - current_time).total_seconds()
                    
                    logger.info(f"Processing completed in {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until 5 seconds into next minute ({next_minute_plus_5.strftime('%H:%M:%S')})...")
                    time.sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    raise
                    # time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            time.sleep(5)
            #raise
            # sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    etl = AffiliateJunctionETL()
    etl.run()


if __name__ == "__main__":
    main()





