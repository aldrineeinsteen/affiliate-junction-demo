import os
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from collections import defaultdict
from contextlib import contextmanager
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ExecutionProfile, Session
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@dataclass
class QueryMetrics:
    """Data class to store query execution metrics"""
    query_id: str
    query_text: str
    parameters: Optional[List[Any]]
    start_time: datetime
    end_time: Optional[datetime]
    execution_time_ms: Optional[float]
    rows_returned: Optional[int]
    success: bool
    error_message: Optional[str]
    prepared: bool
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization"""
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "parameters": self.parameters,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_time_ms": self.execution_time_ms,
            "rows_returned": self.rows_returned,
            "success": self.success,
            "error_message": self.error_message,
            "prepared": self.prepared,
            "retry_count": self.retry_count
        }


class CassandraQueryWrapper:
    """Wrapper for Cassandra queries that captures metrics and query information"""
    
    def __init__(self):
        self._session: Optional[Session] = None
        self._cluster = None
        self._query_counter = 0
        self._query_lock = threading.Lock()
        # Store all queries executed (for non-web applications)
        self._all_queries: List[QueryMetrics] = []
        
    @property
    def session(self) -> Session:
        """Get or create Cassandra session"""
        if self._session is None:
            self._session = self._connect_to_cassandra()
        return self._session
    
    def _connect_to_cassandra(self) -> Session:
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
            
            self._cluster = Cluster(
                [os.getenv('HCD_HOST', 'localhost')],
                port=int(os.getenv('HCD_PORT', '9042')),
                auth_provider=auth_provider,
                protocol_version=5,
                execution_profiles={'default': profile}
            )
            
            session = self._cluster.connect()
            
            # Set keyspace if specified
            if os.getenv('HCD_KEYSPACE'):
                session.set_keyspace(os.getenv('HCD_KEYSPACE'))
            
            logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            raise
    
    def _generate_query_id(self) -> str:
        """Generate unique query ID"""
        with self._query_lock:
            self._query_counter += 1
            return f"query_{self._query_counter}_{int(time.time() * 1000)}"
    
    def execute_query(self, query: str, parameters: Optional[List[Any]] = None, 
                     max_retries: int = 3) -> Any:
        """Execute a CQL query and capture metrics"""
        query_id = self._generate_query_id()
        metrics = QueryMetrics(
            query_id=query_id,
            query_text=query,
            parameters=parameters,
            start_time=datetime.now(timezone.utc),
            end_time=None,
            execution_time_ms=None,
            rows_returned=None,
            success=False,
            error_message=None,
            prepared=False
        )
        
        # Store metrics
        with self._query_lock:
            self._all_queries.append(metrics)
        
        start_time = time.time()
        result = None
        
        for attempt in range(max_retries):
            try:
                metrics.retry_count = attempt
                
                if parameters:
                    # Use prepared statement
                    metrics.prepared = True
                    prepared = self.session.prepare(query)
                    result = self.session.execute(prepared, parameters)
                else:
                    # Execute directly
                    metrics.prepared = False
                    result = self.session.execute(query)
                
                # Calculate execution time
                end_time = time.time()
                metrics.end_time = datetime.now(timezone.utc)
                metrics.execution_time_ms = (end_time - start_time) * 1000
                
                # Count rows returned
                try:
                    # Convert to list to count rows (this consumes the result)
                    result_list = list(result)
                    metrics.rows_returned = len(result_list)
                    metrics.success = True
                    
                    logger.debug(f"Query {query_id} completed successfully: {metrics.rows_returned} rows in {metrics.execution_time_ms:.2f}ms")
                    
                    # Return the list instead of the original result
                    return result_list
                    
                except Exception as count_error:
                    # If we can't count rows, still mark as successful
                    logger.warning(f"Could not count rows for query {query_id}: {count_error}")
                    metrics.rows_returned = None
                    metrics.success = True
                    return result
                
            except Exception as e:
                logger.warning(f"Query {query_id} attempt {attempt + 1} failed: {e}")
                metrics.error_message = str(e)
                
                if attempt < max_retries - 1:
                    # Reset connection and retry
                    self._session = None
                    continue
                else:
                    # Final attempt failed
                    metrics.end_time = datetime.now(timezone.utc)
                    metrics.execution_time_ms = (time.time() - start_time) * 1000
                    metrics.success = False
                    logger.error(f"Query {query_id} failed after {max_retries} attempts")
                    raise
        
        return result
    
    def execute_query_simple(self, query: str, parameters: Optional[List[Any]] = None) -> Any:
        """Execute a query without retry logic (for backward compatibility)"""
        return self.execute_query(query, parameters, max_retries=1)
    
    def prepare_statement(self, query: str):
        """Prepare a statement for reuse"""
        return self.session.prepare(query)
    
    def execute_prepared(self, prepared_statement, parameters: List[Any]) -> Any:
        """Execute a prepared statement and capture metrics"""
        query_id = self._generate_query_id()
        
        # Extract query text from prepared statement if possible
        query_text = getattr(prepared_statement, 'query_string', str(prepared_statement))
        
        metrics = QueryMetrics(
            query_id=query_id,
            query_text=query_text,
            parameters=parameters,
            start_time=datetime.now(timezone.utc),
            end_time=None,
            execution_time_ms=None,
            rows_returned=None,
            success=False,
            error_message=None,
            prepared=True
        )
        
        # Store metrics
        with self._query_lock:
            self._all_queries.append(metrics)
        
        start_time = time.time()
        
        try:
            result = self.session.execute(prepared_statement, parameters)
            
            # Calculate execution time
            end_time = time.time()
            metrics.end_time = datetime.now(timezone.utc)
            metrics.execution_time_ms = (end_time - start_time) * 1000
            
            # Count rows returned
            try:
                result_list = list(result)
                metrics.rows_returned = len(result_list)
                metrics.success = True
                
                logger.debug(f"Prepared query {query_id} completed successfully: {metrics.rows_returned} rows in {metrics.execution_time_ms:.2f}ms")
                return result_list
                
            except Exception as count_error:
                logger.warning(f"Could not count rows for prepared query {query_id}: {count_error}")
                metrics.rows_returned = None
                metrics.success = True
                return result
            
        except Exception as e:
            metrics.end_time = datetime.now(timezone.utc)
            metrics.execution_time_ms = (time.time() - start_time) * 1000
            metrics.success = False
            metrics.error_message = str(e)
            logger.error(f"Prepared query {query_id} failed: {e}")
            raise
    
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
        """Close the Cassandra connection"""
        try:
            if self._session:
                self._session.shutdown()
                self._session = None
                logger.info("Cassandra connection closed")
            
            if self._cluster:
                self._cluster.shutdown()
                self._cluster = None
                
        except Exception as e:
            logger.error(f"Error closing Cassandra connection: {e}")


# Global instance (for standalone usage)
global_cassandra_wrapper = CassandraQueryWrapper()