#!/usr/bin/env python
"""
Database connection classes for affiliate junction demo.
Provides shared connection logic for Cassandra (HCD) and Presto.
Includes query metrics capture for service monitoring.
"""

import os
import time
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from contextlib import contextmanager
import prestodb
import sqlparse
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

logger = logging.getLogger(__name__)


def truncate_query_text(query_text: str, max_length: int = 1500) -> str:
    """
    Truncate query text if it exceeds the maximum length.
    Preserves readability by adding ellipsis and showing character count.
    
    Args:
        query_text: The query text to potentially truncate
        max_length: Maximum allowed length (default: 500)
        
    Returns:
        Truncated query text with ellipsis if needed
    """
    if not query_text or len(query_text) <= max_length:
        return query_text
    
    # Truncate and add ellipsis with character count info
    truncated = query_text[:max_length].rstrip()
    return f"{truncated}... [truncated from {len(query_text)} chars]"


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
    rows_data: Optional[List[Any]] = None
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
            final_formatted_query = f"-- Query repeated {self.repeat_count} times{self.formatted_query_text}"
        
        return {
            "query_id": self.query_id,
            "query_text": truncate_query_text(self.query_text),
            "query_description": self.query_description,
            "query_type": self.query_type,
            "parameters": sanitized_parameters,
            "start_time": self.start_time.isoformat() if self.start_time is not None else None,
            "end_time": self.end_time.isoformat() if self.end_time is not None else None,
            "execution_time_ms": self.execution_time_ms,
            "rows_returned": self.rows_returned,
            "success": self.success,
            "error_message": self.error_message,
            "prepared": self.prepared,
            "retry_count": self.retry_count,
            "formatted_query_text": truncate_query_text(final_formatted_query) if final_formatted_query else None,
            "simplified_query_text": self.simplified_query_text,
            "repeat_count": self.repeat_count,
            # Don't include rows_data for batch services to save space
            "rows_data": None
        }


def normalize_query_for_deduplication(query: str, query_type: str) -> str:
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
    
    # Replace ? parameter placeholders (already normalized for prepared statements)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


class CassandraConnection:
    """Shared Cassandra connection logic with query metrics capture"""
    
    def __init__(self):
        self.session = None
        self.cluster = None
        self._query_counter = 0
        self._query_lock = threading.Lock()
        self._query_metrics = []  # Store query metrics for this connection
    
    def connect(self):
        """Establish connection to Cassandra cluster"""
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
            
            self.cluster = Cluster(
                [os.getenv('HCD_HOST', 'localhost')],
                port=int(os.getenv('HCD_PORT', '9042')),
                auth_provider=auth_provider,
                protocol_version=5,
                execution_profiles={'default': profile}
            )
            
            self.session = self.cluster.connect()
            
            # Set keyspace if specified
            if os.getenv('HCD_KEYSPACE'):
                self.session.set_keyspace(os.getenv('HCD_KEYSPACE'))
            
            logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
            return self.session
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            raise
    
    def _generate_query_id(self) -> str:
        """Generate unique query ID"""
        with self._query_lock:
            self._query_counter += 1
            return f"cql_{self._query_counter}_{int(time.time() * 1000)}"
    
    def _find_existing_query_metric(self, simplified_query: str) -> Optional[QueryMetrics]:
        """Find existing query metric with the same simplified query pattern"""
        for metric in self._query_metrics:
            if metric.simplified_query_text == simplified_query:
                return metric
        return None
    
    def execute_query(self, query: str, parameters: Optional[List[Any]] = None, 
                     max_retries: int = 3, query_description: Optional[str] = None, 
                     representative_query: Optional[str] = None) -> Any:
        """Execute a CQL query and capture metrics"""
        
        # Handle batch statements - check if query is actually a BatchStatement object
        from cassandra.query import BatchStatement
        is_batch = isinstance(query, BatchStatement)
        
        if is_batch:
            # For batch statements, record the batch as a single formatted operation
            return self._execute_batch_with_single_metric(query, query_description, max_retries, representative_query)
        else:
            # Handle regular queries
            return self._execute_single_query(query, parameters, query_description, max_retries)
    
    def _execute_single_query(self, query: str, parameters: Optional[List[Any]] = None,
                             query_description: Optional[str] = None, max_retries: int = 3) -> Any:
        """Execute a single CQL query and capture metrics"""
        
        # Create simplified query for deduplication
        simplified_query = normalize_query_for_deduplication(query, "HCD")
        
        # Check if we already have metrics for this query pattern
        existing_metrics = self._find_existing_query_metric(simplified_query)
        
        if existing_metrics:
            # Increment repeat count and update timing
            existing_metrics.repeat_count += 1
            existing_metrics.start_time = datetime.now(timezone.utc)  # Update to latest execution time
            
            logger.debug(f"Found existing query pattern, incremented count to {existing_metrics.repeat_count}")
            current_metrics = existing_metrics
        else:
            # Create new metrics for this query pattern
            query_id = self._generate_query_id()
            
            # Format the query using sqlparse
            formatted_query = None
            try:
                formatted_query = sqlparse.format(query, reindent=True, keyword_case='upper')
            except Exception as e:
                logger.debug(f"Could not format CQL query with sqlparse: {e}")
                formatted_query = query  # Fallback to original query
            
            current_metrics = QueryMetrics(
                query_id=query_id,
                query_text=query,
                formatted_query_text=formatted_query,
                simplified_query_text=simplified_query,
                query_description=query_description,
                query_type="HCD",
                parameters=parameters,
                start_time=datetime.now(timezone.utc),
                end_time=None,
                execution_time_ms=None,
                rows_returned=None,
                success=False,
                error_message=None,
                prepared=False,
                repeat_count=1
            )
            
            # Store new metrics
            self._query_metrics.append(current_metrics)
            logger.debug(f"Created new query metric {query_id} for pattern. Total metrics: {len(self._query_metrics)}")
        
        start_time = time.time()
        result = None
        
        for attempt in range(max_retries):
            try:
                current_metrics.retry_count = attempt
                
                if parameters:
                    # Use prepared statement
                    current_metrics.prepared = True
                    prepared = self.session.prepare(query)
                    result = self.session.execute(prepared, parameters)
                else:
                    # Execute directly
                    current_metrics.prepared = False
                    result = self.session.execute(query)
                
                # Calculate execution time
                end_time = time.time()
                current_metrics.end_time = datetime.now(timezone.utc)
                current_metrics.execution_time_ms = (end_time - start_time) * 1000
                
                # Count rows returned
                try:
                    result_list = list(result)
                    current_metrics.rows_returned = len(result_list)
                    current_metrics.success = True
                    
                    logger.debug(f"Query {current_metrics.query_id} completed successfully: {current_metrics.rows_returned} rows in {current_metrics.execution_time_ms:.2f}ms")
                    return result_list
                    
                except Exception as count_error:
                    logger.warning(f"Could not count rows for query {current_metrics.query_id}: {count_error}")
                    current_metrics.rows_returned = None
                    current_metrics.success = True
                    return result
                
            except Exception as e:
                logger.warning(f"Query {current_metrics.query_id} attempt {attempt + 1} failed: {e}")
                current_metrics.error_message = str(e)
                
                if attempt < max_retries - 1:
                    # Reset connection and retry
                    self.session = None
                    self.connect()
                    continue
                else:
                    # Final attempt failed
                    current_metrics.end_time = datetime.now(timezone.utc)
                    current_metrics.execution_time_ms = (time.time() - start_time) * 1000
                    current_metrics.success = False
                    logger.error(f"Query {current_metrics.query_id} failed after {max_retries} attempts")
                    raise
        
        return result
    
    def _execute_batch_with_single_metric(self, batch_statement, query_description: Optional[str] = None, max_retries: int = 3, representative_query: Optional[str] = None) -> Any:
        """Execute a batch statement and record metrics for the batch as a single operation"""
        from cassandra.query import BatchStatement
        import sqlparse
        
        batch_start_time = time.time()
        batch_query_id = self._generate_query_id()
        
        # Extract batch size and basic info
        batch_size = 0
        
        try:
            # Access the batch's queries to get size
            if hasattr(batch_statement, '_statements_and_parameters'):
                batch_size = len(batch_statement._statements_and_parameters)
            elif hasattr(batch_statement, '_queries_and_parameters'):
                batch_size = len(batch_statement._queries_and_parameters)
            else:
                # Try to get batch size from other attributes
                batch_size = getattr(batch_statement, 'size', 0) or len(getattr(batch_statement, '_statements_and_parameters', []))
                
        except Exception as e:
            logger.warning(f"Could not determine batch size: {e}")
            batch_size = 0
        
        # Create batch info string
        batch_type = getattr(batch_statement, 'batch_type', 'UNKNOWN')
        consistency = getattr(batch_statement, 'consistency_level', 'Not Set')
        batch_info = f"<BatchStatement type={batch_type}, statements={batch_size}, consistency={consistency}>"
        
        # Use the representative query provided by the caller
        sample_query_text = representative_query
        
        # Format the query using sqlparse if provided
        if sample_query_text:
            try:
                formatted_query = sqlparse.format(sample_query_text, reindent=True, keyword_case='upper')
                sample_query_text = formatted_query
            except Exception as e:
                logger.debug(f"Could not format representative query with sqlparse: {e}")
        
        # Combine batch info with formatted query
        if sample_query_text:
            combined_query_text = f"-- {batch_info}\n{sample_query_text}"
        else:
            combined_query_text = batch_info
        
        # Create a single metric for the entire batch
        metrics = QueryMetrics(
            query_id=batch_query_id,
            query_text=combined_query_text,
            formatted_query_text=combined_query_text,
            simplified_query_text=combined_query_text,  # Batches are unique by nature
            query_description=query_description or 'Batch operation',
            query_type="HCD",
            parameters=None,  # Don't store parameters for batch operations
            start_time=datetime.now(timezone.utc),
            end_time=None,
            execution_time_ms=None,
            rows_returned=0,  # Batch operations don't return rows
            success=False,
            error_message=None,
            prepared=True,  # Batch queries are typically prepared
            repeat_count=1
        )
        
        self._query_metrics.append(metrics)
        logger.debug(f"Recorded single metric for batch with {batch_size} statements. Total metrics: {len(self._query_metrics)}")
        
        # Execute the actual batch
        result = None
        batch_success = False
        batch_error = None
        final_attempt = 0
        
        for attempt in range(max_retries):
            final_attempt = attempt
            try:
                result = self.session.execute(batch_statement)
                batch_success = True
                break
                
            except Exception as e:
                batch_error = str(e)
                logger.warning(f"Batch {batch_query_id} attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Reset connection and retry
                    self.session = None
                    self.connect()
                    continue
                else:
                    logger.error(f"Batch {batch_query_id} failed after {max_retries} attempts")
                    break
        
        # Update the single batch metric with execution results
        batch_end_time = time.time()
        batch_execution_time = (batch_end_time - batch_start_time) * 1000
        
        # Find and update the batch metric
        for metric in self._query_metrics:
            if metric.query_id == batch_query_id:
                metric.end_time = datetime.now(timezone.utc)
                metric.execution_time_ms = batch_execution_time
                metric.success = batch_success
                metric.error_message = batch_error if not batch_success else None
                metric.retry_count = final_attempt
                break
        
        if not batch_success and batch_error:
            raise Exception(batch_error)
        
        logger.debug(f"Batch {batch_query_id} with {batch_size} statements completed in {batch_execution_time:.2f}ms")
        return result
    
    def get_query_metrics(self) -> List[Dict[str, Any]]:
        """Get all query metrics captured by this connection"""
        return [metric.to_dict() for metric in self._query_metrics]
    
    def clear_query_metrics(self):
        """Clear stored query metrics"""
        self._query_metrics = []
    
    def close(self):
        """Clean up Cassandra connection"""
        try:
            if self.session:
                self.session.shutdown()
            if self.cluster:
                self.cluster.shutdown()
            logger.info("Cassandra connection closed")
        except Exception as e:
            logger.error(f"Error closing Cassandra connection: {e}")


class PrestoConnection:
    """Shared Presto connection logic with query metrics capture"""
    
    def __init__(self):
        self.connection = None
        self._query_counter = 0
        self._query_lock = threading.Lock()
        self._query_metrics = []  # Store query metrics for this connection
    
    def connect(self):
        """Establish connection to Presto"""
        try:           
            self.connection = prestodb.dbapi.connect(
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
            self.connection._http_session.verify = "/certs/presto.crt"
            
            logger.info(f"Connected to Presto at {os.getenv('PRESTO_HOST')}:{os.getenv('PRESTO_PORT')}")
            return self.connection
            
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
        for metric in self._query_metrics:
            if metric.simplified_query_text == simplified_query:
                return metric
        return None
    
    def execute_query(self, query: str, parameters: Optional[List[Any]] = None,
                     max_retries: int = 3, query_description: Optional[str] = None) -> Any:
        """Execute a Presto query and capture metrics"""
        
        # Create simplified query for deduplication
        simplified_query = normalize_query_for_deduplication(query, "Presto")
        
        # Check if we already have metrics for this query pattern
        existing_metrics = self._find_existing_query_metric(simplified_query)
        if existing_metrics:
            # Increment repeat count and update timing
            existing_metrics.repeat_count += 1
            existing_metrics.start_time = datetime.now(timezone.utc)  # Update to latest execution time
            
            logger.debug(f"Found existing Presto query pattern, incremented count to {existing_metrics.repeat_count}")
            current_metrics = existing_metrics
        else:
            # Create new metrics for this query pattern
            query_id = self._generate_query_id()
            
            # Format the query using sqlparse
            formatted_query = None
            try:
                formatted_query = sqlparse.format(query[:750], reindent=True, keyword_case='upper')
            except Exception as e:
                logger.debug(f"Could not format Presto query with sqlparse: {e}")
                formatted_query = query  # Fallback to original query
            
            current_metrics = QueryMetrics(
                query_id=query_id,
                query_text=query,
                formatted_query_text=formatted_query,
                simplified_query_text=simplified_query,
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
                repeat_count=1
            )
            
            # Store new metrics
            self._query_metrics.append(current_metrics)
            logger.debug(f"Created new Presto query metric {query_id} for pattern. Total metrics: {len(self._query_metrics)}")
        
        start_time = time.time()
        result = None
        
        for attempt in range(max_retries):
            try:
                current_metrics.retry_count = attempt
                
                cursor = self.connection.cursor()
                cursor.execute(query, parameters)
                
                # Determine if this is a SELECT query or a modification query (INSERT/UPDATE/DELETE)
                query_upper = query.strip().upper()
                is_select_query = query_upper.startswith('SELECT') or query_upper.startswith('WITH') or query_upper.startswith('SHOW') or query_upper.startswith('DESCRIBE')
                
                if is_select_query:
                    # For SELECT queries, fetch the results
                    result = cursor.fetchall()
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
                return result
                
            except Exception as e:
                logger.warning(f"Query {current_metrics.query_id} attempt {attempt + 1} failed: {e}")
                current_metrics.error_message = str(e)
                
                if attempt < max_retries - 1:
                    # Reset connection and retry
                    self.connection = None
                    self.connect()
                    continue
                else:
                    # Final attempt failed
                    current_metrics.end_time = datetime.now(timezone.utc)
                    current_metrics.execution_time_ms = (time.time() - start_time) * 1000
                    current_metrics.success = False
                    logger.error(f"Query {current_metrics.query_id} failed after {max_retries} attempts")
                    raise
        
        return result
    
    def get_query_metrics(self) -> List[Dict[str, Any]]:
        """Get all query metrics captured by this connection"""
        return [metric.to_dict() for metric in self._query_metrics]
    
    def clear_query_metrics(self):
        """Clear stored query metrics"""
        self._query_metrics = []
    
    def close(self):
        """Clean up Presto connection"""
        try:
            if self.connection:
                self.connection.close()
            logger.info("Presto connection closed")
        except Exception as e:
            logger.error(f"Error closing Presto connection: {e}")
