#!/usr/bin/env python
"""
Simple script to truncate all Iceberg and HCD Cassandra tables.
This script will clear all data from both the analytics (Presto) and operational (Cassandra) databases.
"""

import os
import sys
import logging
from dotenv import load_dotenv
from affiliate_common.database_connections import CassandraConnection, PrestoConnection

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_environment():
    """Load environment variables from .env file"""
    load_dotenv()
    
    # Verify required environment variables
    required_vars = [
        'HCD_HOST', 'HCD_PORT', 'HCD_USER', 'HCD_PASSWD', 'HCD_KEYSPACE',
        'PRESTO_HOST', 'PRESTO_PORT', 'PRESTO_USER', 'PRESTO_PASSWD', 'PRESTO_CATALOG', 'PRESTO_SCHEMA'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)

def truncate_presto_tables():
    """Truncate all Iceberg tables in Presto"""
    logger.info("Starting Presto/Iceberg table truncation...")
    
    # Tables from presto_schema.sql
    iceberg_tables = [
        'impression_tracking',
        'conversion_tracking', 
        'conversions_identified'
    ]
    
    presto_conn = PrestoConnection()
    
    try:
        presto_conn.connect()
        
        for table in iceberg_tables:
            try:
                full_table_name = f"{os.getenv('PRESTO_CATALOG')}.{os.getenv('PRESTO_SCHEMA')}.{table}"
                truncate_query = f"DELETE FROM {full_table_name}"
                
                logger.info(f"Truncating Presto table: {full_table_name}")
                presto_conn.execute_query(
                    truncate_query, 
                    query_description=f"Truncate table {table}"
                )
                logger.info(f"Successfully truncated {full_table_name}")
                
            except Exception as e:
                logger.error(f"Failed to truncate Presto table {table}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to connect to Presto: {e}")
    finally:
        presto_conn.close()

def truncate_cassandra_tables():
    """Truncate all HCD Cassandra tables"""
    logger.info("Starting HCD/Cassandra table truncation...")
    
    # Tables from hcd_schema.cql
    cassandra_tables = [
        'impression_tracking',
        'conversion_tracking',
        'impressions_by_minute',
        'conversions_by_minute', 
        'publishers',
        'advertisers',
        'services',
        'key_value_store'
    ]
    
    cassandra_conn = CassandraConnection()
    
    try:
        cassandra_conn.connect()
        
        for table in cassandra_tables:
            try:
                # Use TRUNCATE statement for Cassandra
                truncate_query = f"TRUNCATE {os.getenv('HCD_KEYSPACE')}.{table}"
                
                logger.info(f"Truncating Cassandra table: {os.getenv('HCD_KEYSPACE')}.{table}")
                cassandra_conn.execute_query(
                    truncate_query,
                    query_description=f"Truncate table {table}"
                )
                logger.info(f"Successfully truncated {os.getenv('HCD_KEYSPACE')}.{table}")
                
            except Exception as e:
                logger.error(f"Failed to truncate Cassandra table {table}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to connect to Cassandra: {e}")
    finally:
        cassandra_conn.close()

def main():
    """Main function to truncate all tables"""
    logger.info("=== Starting truncation of all affiliate junction tables ===")
    
    # Load environment variables
    load_environment()
    
    # Truncate Presto tables first (analytics layer)
    truncate_presto_tables()
    
    print()
    
    # Truncate Cassandra tables (operational layer)
    truncate_cassandra_tables()
    
    logger.info("=== Table truncation completed ===")

if __name__ == "__main__":
    main()