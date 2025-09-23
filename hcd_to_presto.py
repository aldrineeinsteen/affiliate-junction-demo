#!/usr/bin/env python

import os
import sys
import time
import logging
import requests
import prestodb
from datetime import datetime, timezone
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
        """Rollup impressions from Cassandra to Presto - STUB FUNCTION"""
        logger.info("Starting impressions rollup process...")
        
        # Get current minute timestamp for processing
        current_minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        
        # TODO: Implement impressions rollup logic
        # This should:
        # 1. Query impressions_by_minute table from Cassandra for the current minute
        # 2. Aggregate by publishers_id, advertisers_id
        # 3. Calculate total impressions and unique cookies
        # 4. Write aggregated data to Presto impressions_rollup table
        
        logger.info(f"Impressions rollup completed for minute: {current_minute}")
    
    def identify_conversions(self):
        """Identify conversions by matching with impression data - STUB FUNCTION"""
        logger.info("Starting conversions identification process...")
        
        # Get current minute timestamp for processing
        current_minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        
        # TODO: Implement conversion identification logic
        # This should:
        # 1. Query conversion_tracking table from Cassandra for the current minute
        # 2. For each conversion, look back in impression_tracking to find matching impressions
        # 3. Calculate time_to_conversion and identify the publisher that should get credit
        # 4. Write conversion attribution data to Presto conversions_identified table
        
        logger.info(f"Conversions identification completed for minute: {current_minute}")
    
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
            sys.exit()
            
            logger.info("Entering main loop...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Task 1: Rollup impressions
                    self.rollup_impressions()
                    
                    # Task 2: Identify conversions
                    self.identify_conversions()
                    
                    # Calculate how long the processing took
                    execution_time = time.time() - iteration_start
                    
                    # Calculate sleep time to align with the next minute
                    now = time.time()
                    seconds_into_minute = now % 60
                    sleep_time = max(0, 60 - seconds_into_minute)
                    
                    logger.info(f"Processing completed in {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until next minute...")
                    time.sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    """Entry point"""
    etl = AffiliateJunctionETL()
    etl.run()


if __name__ == "__main__":
    main()





