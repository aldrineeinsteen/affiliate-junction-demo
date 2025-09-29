import logging
import os
import time
from typing import List, Dict, Any, Optional, Tuple
import prestodb
import prestodb.auth

# Configure logging FIRST
logger = logging.getLogger(__name__)

try:
    from .presto_wrapper import presto_wrapper
    _wrapper_available = True
    logger.info("Presto wrapper imported successfully")
except ImportError as e:
    logger.error(f"Failed to import presto_wrapper: {e}")
    presto_wrapper = None
    _wrapper_available = False
except Exception as e:
    logger.error(f"Failed to initialize presto_wrapper: {e}")
    presto_wrapper = None
    _wrapper_available = False

# Global connection variable (for backward compatibility)
_presto_connection = None


def get_presto_connection():
    """Get or create Presto connection - delegated to wrapper"""
    return presto_wrapper.connection


def connect_to_presto():
    """Establish connection to Presto - delegated to wrapper"""
    return presto_wrapper.connection


def close_presto_connection():
    """Close the Presto connection"""
    global _presto_connection
    presto_wrapper.close_connection()
    _presto_connection = None


def execute_query_simple(query: str, parameters: Optional[List] = None, query_description: Optional[str] = None) -> List[Any]:
    """
    Execute a Presto SQL query and return results - now with query metrics
    
    Args:
        query: SQL query string
        parameters: List of parameters for prepared statements
        query_description: Description of the query for logging and metrics
        
    Returns:
        List of result rows
    """
    return presto_wrapper.execute_query_simple(query, parameters, query_description)


def execute_query_with_retry(query: str, parameters: Optional[List] = None, max_retries: int = 3, query_description: Optional[str] = None) -> List[Any]:
    """
    Execute a Presto query with connection retry logic - now with query metrics
    
    Args:
        query: SQL query string
        parameters: List of parameters
        max_retries: Maximum number of retry attempts
        query_description: Description of the query for logging and metrics
        
    Returns:
        List of result rows
    """
    return presto_wrapper.execute_query_with_retry(query, parameters, max_retries, query_description)


def execute_query(query: str, parameters: Optional[List] = None, max_retries: int = 3, query_description: Optional[str] = None) -> List[Any]:
    """
    Alias for execute_query_with_retry for compatibility with hcd_operations pattern
    """
    return execute_query_with_retry(query, parameters, max_retries, query_description)


def test_connection() -> bool:
    """
    Test if Presto connection is working
    
    Returns:
        True if connection is working, False otherwise
    """
    return presto_wrapper.test_connection()


def get_table_info(schema: str, table: str) -> Optional[Dict]:
    """
    Get information about a table
    
    Args:
        schema: Schema name
        table: Table name
        
    Returns:
        Dictionary with table information or None if not found
    """
    return presto_wrapper.get_table_info(schema, table)


# ========== QUERY METRICS FUNCTIONS (matching cassandra_wrapper pattern) ==========

def get_request_queries() -> List[Dict[str, Any]]:
    """
    Get all queries executed in the current request context (matches cassandra_wrapper pattern)
    
    Returns:
        List of dictionaries containing query execution metrics for current request
    """
    return presto_wrapper.get_request_queries()


# ========== ADDITIONAL QUERY METRICS FUNCTIONS ==========

def get_query_metrics() -> List[Dict[str, Any]]:
    """
    Get all query metrics captured by the Presto wrapper (backward compatibility).
    
    Returns:
        List of dictionaries containing query execution metrics including:
        - query_id: Unique identifier for the query
        - query_text: The SQL query text (truncated if too long)
        - query_description: Human-readable description of the query
        - parameters: Query parameters (sanitized for serialization)
        - start_time: When the query started executing
        - end_time: When the query finished executing
        - execution_time_ms: How long the query took to execute
        - rows_returned: Number of rows returned by the query
        - success: Whether the query executed successfully
        - error_message: Error message if the query failed
        - prepared: Whether the query used prepared statements
        - retry_count: Number of retries attempted
        - formatted_query_text: Pretty-formatted SQL query
        - repeat_count: How many times this query pattern was executed
        
    Example:
        metrics = get_query_metrics()
        for metric in metrics:
            print(f"Query {metric['query_id']}: {metric['execution_time_ms']}ms")
    """
    return presto_wrapper.get_all_queries()


def get_query_summary() -> Dict[str, Any]:
    """
    Get summary statistics of all queries executed by the Presto wrapper.
    
    Returns:
        Dictionary containing aggregate metrics:
        - total_queries: Total number of query executions
        - successful_queries: Number of queries that completed successfully
        - failed_queries: Number of queries that failed
        - average_execution_time_ms: Average execution time in milliseconds
        - total_rows_returned: Total number of rows returned across all queries
        
    Example:
        summary = get_query_summary()
        print(f"Executed {summary['total_queries']} queries")
        print(f"Average execution time: {summary['average_execution_time_ms']}ms")
    """
    return presto_wrapper.get_query_summary()


def clear_query_metrics():
    """
    Clear all stored query metrics. Useful for resetting metrics during testing
    or to free up memory in long-running applications.
    """
    presto_wrapper.clear_query_history()
    logger.info("Presto query metrics cleared")


def format_presto_query(query: str, parameters: List) -> str:
    """
    Format a Presto query with parameters (kept for backward compatibility)
    
    Args:
        query: Query string with placeholders
        parameters: List of parameter values
        
    Returns:
        Formatted query string
    """
    return presto_wrapper._format_presto_query(query, parameters)