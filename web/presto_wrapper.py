import os
import time
import logging
import threading
import sqlparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from collections import defaultdict
from contextlib import contextmanager
from dotenv import load_dotenv
import prestodb
import prestodb.auth

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def truncate_query_text(query_text: str, max_length: int = 750) -> str:
    """
    Truncate query text if it exceeds the maximum length.
    Preserves readability by adding ellipsis and showing character count.
    
    Args:
        query_text: The query text to potentially truncate
        max_length: Maximum allowed length (default: 750)
        
    Returns:
        Truncated query text with ellipsis if needed
    """
    if not query_text or len(query_text) <= max_length:
        return query_text
    
    # Truncate and add ellipsis with character count info
    truncated = query_text[:max_length].rstrip()
    return f"{truncated}... [truncated from {len(query_text)} chars]"


def normalize_query_for_deduplication(query: str) -> str:
    """
    Normalize a query for deduplication by removing values from WHERE predicates.
    Creates a simplified pattern for quick identification of similar queries.
    """
    import re
    
    # Start with the original query
    normalized = query.strip()
    
    # Convert to uppercase for consistent comparison
    normalized = normalized.upper()
    
    # Focus on WHERE predicates - remove values but keep structure
    # Pattern: column = 'value' -> column = 
    normalized = re.sub(r"(\w+\s*=\s*)'[^']*'", r"\1", normalized)
    
    # Pattern: column = "value" -> column = 
    normalized = re.sub(r'(\w+\s*=\s*)"[^"]*"', r"\1", normalized)
    
    # Pattern: column = 123 -> column = 
    normalized = re.sub(r'(\w+\s*=\s*)\d+(\.\d+)?', r"\1", normalized)
    
    # Pattern: column IN ('val1', 'val2') -> column IN ()
    normalized = re.sub(r'(\bIN\s*\()\s*[^)]+(\))', r'\1\2', normalized)
    
    # Pattern: column BETWEEN val1 AND val2 -> column BETWEEN AND 
    normalized = re.sub(r'(\bBETWEEN\s+)[^A]+(\bAND\s+)[^\s]+', r'\1\2', normalized)
    
    # Replace parameter placeholders (already normalized for prepared statements)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


@dataclass
class QueryMetrics:
    """Data class to store query execution metrics"""
    query_id: str
    query_text: str
    query_description: Optional[str]
    query_type: str
    parameters: Optional[List[Any]]
    start_time: datetime
    end_time: Optional[datetime]
    execution_time_ms: Optional[float]
    rows_returned: Optional[int]
    success: bool
    error_message: Optional[str]
    prepared: bool
    retry_count: int = 0
    formatted_query_text: Optional[str] = None
    simplified_query_text: Optional[str] = None  # Normalized query for deduplication
    repeat_count: int = 1  # Number of times this query pattern has been executed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization"""
        # Sanitize parameters for JSON serialization
        sanitized_parameters = None
        if self.parameters is not None:
            # Limit to max 10 parameters
            limited_params = self.parameters[:10] if len(self.parameters) > 10 else self.parameters
            sanitized_parameters = []
            
            for param in limited_params:
                try:
                    # Convert parameter to string
                    if isinstance(param, datetime):
                        param_str = param.isoformat()
                    else:
                        param_str = str(param)
                    
                    # Truncate if too long
                    if len(param_str) > 15:
                        param_str = param_str[:12] + "..."
                    
                    sanitized_parameters.append(param_str)
                except Exception:
                    # If conversion fails, use a placeholder
                    sanitized_parameters.append("<unconvertible>")
        
        # Add repeat count header to formatted query text if repeated
        final_formatted_query = self.formatted_query_text
        if self.repeat_count > 1 and self.formatted_query_text:
            final_formatted_query = f"-- Query repeated {self.repeat_count} times\n{self.formatted_query_text}"
        
        return {
            "query_id": self.query_id,
            "query_text": truncate_query_text(self.query_text),
            "query_description": self.query_description,
            "query_type": self.query_type,
            "parameters": sanitized_parameters,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_time_ms": self.execution_time_ms,
            "rows_returned": self.rows_returned,
            "success": self.success,
            "error_message": self.error_message,
            "prepared": self.prepared,
            "retry_count": self.retry_count,
            "formatted_query_text": truncate_query_text(final_formatted_query) if final_formatted_query else None,
            "simplified_query_text": self.simplified_query_text,
            "repeat_count": self.repeat_count
        }


class PrestoQueryWrapper:
    """Wrapper for Presto queries that captures metrics and query information"""
    
    def __init__(self):
        self._connection = None
        self._query_counter = 0
        self._query_lock = threading.Lock()
        # Store all queries executed (for non-web applications)
        self._all_queries: List[QueryMetrics] = []
        # Thread-local storage for current request's query metrics
        self._request_queries = threading.local()
        
    @property
    def connection(self):
        """Get or create Presto connection"""
        if self._connection is None:
            self._connection = self._connect_to_presto()
        return self._connection
    
    def _connect_to_presto(self):
        """Establish connection to Presto"""
        try:           
            connection = prestodb.dbapi.connect(
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
            connection._http_session.verify = "/certs/presto.crt"
            
            logger.info(f"Connected to Presto at {os.getenv('PRESTO_HOST')}:{os.getenv('PRESTO_PORT')}")
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to Presto: {e}")
            raise
    
    def _generate_query_id(self) -> str:
        """Generate unique query ID"""
        with self._query_lock:
            self._query_counter += 1
            return f"presto_{self._query_counter}_{int(time.time() * 1000)}"
    
    def _find_existing_query_metric(self, simplified_query: str) -> Optional[QueryMetrics]:
        """Find existing query metric with the same simplified query pattern"""
        for metric in self._all_queries:
            if metric.simplified_query_text == simplified_query:
                return metric
        return None
    
    @contextmanager
    def request_context(self):
        """Context manager to track queries for a specific request"""
        # Initialize request-local query storage
        if not hasattr(self._request_queries, 'queries'):
            self._request_queries.queries = []
        
        try:
            yield
        finally:
            # Don't clear queries here - they'll be retrieved by get_request_queries()
            pass
    
    def get_request_queries(self) -> List[Dict[str, Any]]:
        """Get all queries executed in the current request context"""
        if hasattr(self._request_queries, 'queries'):
            queries = [q.to_dict() for q in self._request_queries.queries]
            # Clear the queries after retrieving them
            self._request_queries.queries = []
            return queries
        return []
    
    def _format_presto_query(self, query: str, parameters: List) -> str:
        """
        Format a Presto query with parameters
        
        Since Presto doesn't use ? placeholders like Cassandra, we need to format the query
        This is a simple implementation - in production, you'd want more robust parameter handling
        
        Args:
            query: Query string with placeholders
            parameters: List of parameter values
            
        Returns:
            Formatted query string
        """
        formatted_query = query
        
        # Replace ? placeholders with actual values
        for param in parameters:
            if isinstance(param, str):
                # Escape single quotes in strings and wrap in quotes
                escaped_param = "'" + param.replace("'", "''") + "'"
            elif param is None:
                escaped_param = "NULL"
            else:
                escaped_param = str(param)
            
            # Replace the first occurrence of ?
            formatted_query = formatted_query.replace('?', escaped_param, 1)
        
        return formatted_query
    
    def execute_query(self, query: str, parameters: Optional[List[Any]] = None, 
                     max_retries: int = 3, query_description: Optional[str] = None) -> Any:
        """Execute a Presto query and capture metrics"""
        
        # Create simplified query for deduplication
        simplified_query = normalize_query_for_deduplication(query)
        
        # Check if we already have metrics for this query pattern
        existing_metrics = self._find_existing_query_metric(simplified_query)
        
        if existing_metrics:
            # Increment repeat count and update timing
            existing_metrics.repeat_count += 1
            existing_metrics.start_time = datetime.now(timezone.utc)  # Update to latest execution time
            
            # Also add to current request context
            if not hasattr(self._request_queries, 'queries'):
                self._request_queries.queries = []
            self._request_queries.queries.append(existing_metrics)
            
            logger.debug(f"Found existing Presto query pattern, incremented count to {existing_metrics.repeat_count}")
            current_metrics = existing_metrics
        else:
            # Create new metrics for this query pattern
            query_id = self._generate_query_id()
            
            # Format the query using sqlparse
            formatted_query = None
            try:
                formatted_query = sqlparse.format(query, reindent=True, keyword_case='upper')
            except Exception as e:
                logger.debug(f"Could not format Presto query with sqlparse: {e}")
                formatted_query = query  # Fallback to original query
            
            current_metrics = QueryMetrics(
                query_id=query_id,
                query_text=query,
                query_description=query_description,
                query_type="Presto",
                parameters=parameters,
                start_time=datetime.now(timezone.utc),
                end_time=None,
                execution_time_ms=None,
                rows_returned=None,
                success=False,
                error_message=None,
                prepared=False,
                formatted_query_text=formatted_query,
                simplified_query_text=simplified_query,
                repeat_count=1
            )
            
            # Store new metrics
            with self._query_lock:
                self._all_queries.append(current_metrics)
            
            # Also store in thread-local storage for request context
            if not hasattr(self._request_queries, 'queries'):
                self._request_queries.queries = []
            self._request_queries.queries.append(current_metrics)
            
            logger.debug(f"Created new Presto query metric {query_id} for pattern. Total metrics: {len(self._all_queries)}")
        
        start_time = time.time()
        result = None
        
        for attempt in range(max_retries):
            try:
                current_metrics.retry_count = attempt
                
                cursor = self.connection.cursor()
                
                # Determine the actual query to execute
                if parameters:
                    # Format the query with parameters
                    current_metrics.prepared = False  # Presto doesn't use true prepared statements
                    formatted_query_to_execute = self._format_presto_query(query, parameters)
                    cursor.execute(formatted_query_to_execute)
                else:
                    # Execute directly
                    current_metrics.prepared = False
                    cursor.execute(query)
                
                # Determine if this is a SELECT query or a modification query (INSERT/UPDATE/DELETE)
                query_upper = query.strip().upper()
                is_select_query = query_upper.startswith('SELECT') or query_upper.startswith('WITH') or query_upper.startswith('SHOW') or query_upper.startswith('DESCRIBE')
                
                if is_select_query:
                    # For SELECT queries, fetch the results
                    result_rows = cursor.fetchall()
                    
                    # Get column names and create named tuple-like objects for easier access
                    column_names = [desc[0] for desc in cursor.description] if cursor.description else []
                    
                    # Convert to list of objects with attribute access
                    formatted_results = []
                    for row in result_rows:
                        if column_names:
                            # Create a simple object with attribute access
                            row_dict = dict(zip(column_names, row))
                            formatted_results.append(type('Row', (), row_dict)())
                        else:
                            formatted_results.append(row)
                    
                    result = formatted_results
                    current_metrics.rows_returned = len(result) if result else 0
                else:
                    # For INSERT/UPDATE/DELETE queries, don't fetch results
                    # Instead, get the row count if available
                    result = None
                    try:
                        current_metrics.rows_returned = cursor.rowcount if hasattr(cursor, 'rowcount') else 0
                    except:
                        current_metrics.rows_returned = 0
                
                # Calculate execution time
                end_time = time.time()
                current_metrics.end_time = datetime.now(timezone.utc)
                current_metrics.execution_time_ms = (end_time - start_time) * 1000
                current_metrics.success = True
                
                logger.debug(f"Query {current_metrics.query_id} completed successfully: {current_metrics.rows_returned} rows in {current_metrics.execution_time_ms:.2f}ms")
                
                # Close cursor
                cursor.close()
                
                return result
                
            except Exception as e:
                logger.warning(f"Query {current_metrics.query_id} attempt {attempt + 1} failed: {e}")
                current_metrics.error_message = str(e)
                
                if 'cursor' in locals():
                    try:
                        cursor.close()
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    # Reset connection and retry
                    self._connection = None
                    # Wait before retry
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying Presto query in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed
                    current_metrics.end_time = datetime.now(timezone.utc)
                    current_metrics.execution_time_ms = (time.time() - start_time) * 1000
                    current_metrics.success = False
                    logger.error(f"Query {current_metrics.query_id} failed after {max_retries} attempts")
                    raise
        
        return result
    
    def execute_query_simple(self, query: str, parameters: Optional[List[Any]] = None, 
                           query_description: Optional[str] = None) -> Any:
        """Execute a query without retry logic (for backward compatibility)"""
        return self.execute_query(query, parameters, max_retries=1, query_description=query_description)
    
    def execute_query_with_retry(self, query: str, parameters: Optional[List[Any]] = None, 
                               max_retries: int = 3, query_description: Optional[str] = None) -> Any:
        """Execute a query with retry logic (alias for execute_query)"""
        return self.execute_query(query, parameters, max_retries, query_description)
    
    def test_connection(self) -> bool:
        """
        Test if Presto connection is working
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            result = self.execute_query_simple("SELECT 1 as test", query_description="Connection test")
            return len(result) > 0 and hasattr(result[0], 'test') and result[0].test == 1
        except Exception as e:
            logger.error(f"Presto connection test failed: {e}")
            return False
    
    def get_table_info(self, schema: str, table: str) -> Optional[Dict]:
        """
        Get information about a table
        
        Args:
            schema: Schema name
            table: Table name
            
        Returns:
            Dictionary with table information or None if not found
        """
        try:
            query = f"DESCRIBE {schema}.{table}"
            result = self.execute_query_simple(query, query_description=f"Describe table {schema}.{table}")
            
            columns = []
            for row in result:
                columns.append({
                    "name": row.Column,
                    "type": row.Type,
                    "extra": getattr(row, 'Extra', ''),
                    "comment": getattr(row, 'Comment', '')
                })
            
            return {
                "schema": schema,
                "table": table,
                "columns": columns
            }
            
        except Exception as e:
            logger.error(f"Error getting table info for {schema}.{table}: {e}")
            return None
    
    def get_all_queries(self) -> List[Dict[str, Any]]:
        """Get all queries executed by this wrapper"""
        with self._query_lock:
            return [q.to_dict() for q in self._all_queries]
    
    def clear_query_history(self):
        """Clear the query history"""
        with self._query_lock:
            self._all_queries.clear()
            logger.info("Query history cleared")
    
    def get_query_summary(self) -> Dict[str, Any]:
        """Get summary statistics of all queries"""
        with self._query_lock:
            if not self._all_queries:
                return {
                    "total_queries": 0,
                    "successful_queries": 0,
                    "failed_queries": 0,
                    "average_execution_time_ms": 0,
                    "total_rows_returned": 0
                }
            
            successful = [q for q in self._all_queries if q.success]
            failed = [q for q in self._all_queries if not q.success]
            
            avg_exec_time = 0
            total_rows = 0
            
            if successful:
                exec_times = [q.execution_time_ms for q in successful if q.execution_time_ms is not None]
                if exec_times:
                    avg_exec_time = sum(exec_times) / len(exec_times)
                
                total_rows = sum(q.rows_returned for q in successful if q.rows_returned is not None)
            
            return {
                "total_queries": len(self._all_queries),
                "successful_queries": len(successful),
                "failed_queries": len(failed),
                "average_execution_time_ms": round(avg_exec_time, 2),
                "total_rows_returned": total_rows
            }
    
    def close_connection(self):
        """Close the Presto connection"""
        try:
            if self._connection:
                self._connection.close()
                self._connection = None
                logger.info("Presto connection closed")
                
        except Exception as e:
            logger.error(f"Error closing Presto connection: {e}")


# Global instance (to match cassandra_wrapper pattern)
presto_wrapper = PrestoQueryWrapper()

# Global instance (for standalone usage - backward compatibility)
global_presto_wrapper = PrestoQueryWrapper()