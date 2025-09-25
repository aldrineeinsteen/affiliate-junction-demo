import logging
from .cassandra_wrapper import cassandra_wrapper

# Configure logging
logger = logging.getLogger(__name__)


def get_cassandra_session():
    """Get or create Cassandra session"""
    return cassandra_wrapper.session


def close_cassandra_connection():
    """Close the Cassandra connection"""
    cassandra_wrapper.close_connection()


def execute_query(query, parameters=None, query_description=None):
    """Execute a CQL query and return results"""
    try:
        return cassandra_wrapper.execute_query_simple(query, parameters, query_description)
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        raise


def execute_query_with_retry(query, parameters=None, max_retries=3, query_description=None):
    """Execute a query with connection retry logic"""
    return cassandra_wrapper.execute_query(query, parameters, max_retries, query_description)