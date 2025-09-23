#!/usr/bin/env python

import os
import sys
import time
import logging
import requests
import prestodb
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
            
            if not all_impressions:
                logger.info(f"No impressions found for minute: {previous_minute}")
                return
            
            logger.info(f"Found {len(all_impressions)} raw impression records for minute: {previous_minute}")
            
            impressions_df = self.spark.createDataFrame(all_impressions)
            
            # Aggregate by publishers_id, advertisers_id, cookie_id to count impressions
            # Multiple records for the same combo within the time period should be counted
            # Include bucket_date in groupBy since all records should have the same bucket_date
            final_df = impressions_df.groupBy("publishers_id", "advertisers_id", "cookie_id", "bucket_date") \
                .agg(count("*").alias("impressions")) \
                .withColumnRenamed("bucket_date", "timestamp")
            
            logger.info(f"Aggregated to {final_df.count()} unique publisher-advertiser-cookie combinations")
            
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
        
        logger.info(f"Impressions rollup completed for minute: {previous_minute}")
    
    def identify_conversions(self):
        """Identify conversions by matching with impression data - STUB FUNCTION"""
        logger.info("Starting conversions identification process...")
        
        # Get current minute timestamp for processing
        previous_minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        
        # TODO: Implement conversion identification logic
        # This should:
        # 1. Query conversion_tracking table from Cassandra for the current minute
        # 2. For each conversion, look back in impression_tracking to find matching impressions
        # 3. Calculate time_to_conversion and identify the publisher that should get credit
        # 4. Write conversion attribution data to Presto conversions_identified table
        
        logger.info(f"Conversions identification completed for minute: {previous_minute}")
    
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
                    
                    # Task 1: Rollup impressions
                    self.rollup_impressions()
                    
                    # Task 2: Identify conversions
                    # self.identify_conversions()
                    
                    execution_time = time.time() - iteration_start
                    sleep_time = 60 - execution_time
                    logger.info(f"Processing completed in {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until next minute...")
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
            raise
            # sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    etl = AffiliateJunctionETL()
    etl.run()


if __name__ == "__main__":
    main()





