#!/usr/bin/env python

import os
import sys
import time
import logging
import requests
import prestodb
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy
from pyspark.sql import SparkSession
from pyspark.sql.functions import *


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AffiliateJunctionETL:
    def __init__(self):
        self.cassandra_session = None
        self.presto_connection = None
        self.spark = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.load_environment()
        
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
        
    def load_environment(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            logger.info("Environment variables loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            sys.exit(1)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster - reusing from generate_traffic.py"""
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
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            # Query for the hcd_to_presto service record
            query = f"SELECT name, description, last_updated, settings FROM {os.getenv('HCD_KEYSPACE')}.services WHERE name = 'hcd_to_presto'"
            result = self.cassandra_session.execute(query)
            
            service_record = result.one()
            
            if service_record:
                # Service record exists
                logger.debug("Found existing hcd_to_presto service record")
            else:
                # No service record exists, insert a new one
                logger.info("No hcd_to_presto service record found, inserting new record")
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
                'hcd_to_presto',
                'ETL service for transferring and aggregating data from Cassandra to Presto/Iceberg',
                datetime.now(timezone.utc),
                settings_json,
                '{}'  # Empty stats JSON object
            ])
            
            logger.info("Successfully inserted new hcd_to_presto service record")
            
        except Exception as e:
            logger.error(f"Failed to insert service record: {e}")
    
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
            schema_file_path = os.path.join(self.script_dir, 'presto_schema.sql')
            
            if not os.path.exists(schema_file_path):
                logger.error(f"Presto schema file not found at: {schema_file_path}")
                raise FileNotFoundError(f"Presto schema file not found: {schema_file_path}")
            
            logger.info(f"Executing Presto schema file: {schema_file_path}")
            
            # Read and execute the schema file
            with open(schema_file_path, 'r') as f:
                schema_content = f.read()
            
            logger.info(f"Schema file content length: {len(schema_content)} characters")
            
            # Split statements by semicolon and execute each one
            cursor = self.presto_connection.cursor()
            
            # Remove comments and split by semicolons
            lines = schema_content.split('\n')
            cleaned_lines = []
            for line in lines:
                # Remove comments but keep the rest of the line
                if '--' in line:
                    line = line[:line.index('--')]
                cleaned_lines.append(line)
            
            cleaned_content = '\n'.join(cleaned_lines)
            statements = [stmt.strip() for stmt in cleaned_content.split(';') if stmt.strip()]
            
            logger.info(f"Found {len(statements)} SQL statements to execute")
            
            for i, statement in enumerate(statements, 1):
                if statement:
                    logger.info(f"Executing statement {i}/{len(statements)}: {statement[:100]}...")
                    try:
                        cursor.execute(statement)
                        result = cursor.fetchall()
                        logger.info(f"Statement {i} executed successfully. Result: {result}")
                    except Exception as stmt_error:
                        logger.error(f"Error executing statement {i}: {stmt_error}")
                        logger.error(f"Statement was: {statement}")
                        raise
            
            cursor.close()
            logger.info("Presto schema executed successfully")
            
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
                
                rows = self.cassandra_session.execute(query)
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
            
            impressions_df = self.spark.createDataFrame(all_impressions)
            
            # Aggregate by publishers_id, advertisers_id, cookie_id to count impressions
            # Multiple records for the same combo within the time period should be counted
            # Include bucket_date in groupBy since all records should have the same bucket_date
            final_df = impressions_df.groupBy("publishers_id", "advertisers_id", "cookie_id", "bucket_date") \
                .agg(count("*").alias("impressions")) \
                .withColumnRenamed("bucket_date", "timestamp")
            
            impressions_aggregated = final_df.count()
            logger.info(f"Aggregated to {impressions_aggregated} unique publisher-advertiser-cookie combinations")
            
            impressions_batches = 0
            # Write aggregated data to Presto impression_tracking table
            if final_df.count() > 0:
                # Convert Spark DataFrame to list of tuples for Presto insertion
                rows_to_insert = final_df.collect()
                
                cursor = self.presto_connection.cursor()
                
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
                    
                    # Execute the batch as a single statement
                    cursor.execute(batch_insert_query)
                
                cursor.close()
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
                
                rows = self.cassandra_session.execute(query)
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
            cursor = self.presto_connection.cursor()
            
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
                
                # Execute the batch as a single statement
                cursor.execute(batch_insert_query)
            
            cursor.close()
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
                'hcd_to_presto'
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





