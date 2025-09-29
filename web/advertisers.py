import logging
from typing import List, Dict, Optional, Any
from . import hcd_operations
from . import presto_operations
import random
import json
import time

# Configure logging
logger = logging.getLogger(__name__)


def get_random_advertisers(limit: int = 10) -> List[Dict[str, str]]:
    """
    Get a random selection of advertisers from the HCD advertisers table.
    
    Args:
        limit: Maximum number of advertisers to return (default: 10)
        
    Returns:
        List of dictionaries containing advertiser information:
        [{"advertiser_id": "ADV123", "name": "ADV123"}, ...]
    """
    try:
        # Query to get advertisers - using LIMIT to control result size
        # Note: Cassandra doesn't have true random sampling, but we can limit results
        query = "SELECT advertiser_id FROM advertisers LIMIT ?"
        
        result = hcd_operations.execute_query_with_retry(query, [limit * 3], query_description="Fetch random advertisers for dropdown")  # Get more than needed to allow for filtering
        
        advertisers = []
        seen_ids = set()
        
        advertiser_ids = [row.advertiser_id for row in result]
        random.shuffle(advertiser_ids)
        selected_ids = advertiser_ids[:limit]

        advertisers = []
        for advertiser_id in selected_ids:
            advertisers.append({
            "advertiser_id": advertiser_id,
            "name": advertiser_id  # Using ID as display name for now
            })
        logger.info(f"Retrieved {len(advertisers)} advertisers")
        return advertisers
        
    except Exception as e:
        logger.error(f"Error fetching advertisers: {e}")
        return []


def get_advertiser_details(advertiser_id: str) -> Optional[Dict]:
    """
    Get detailed information for a specific advertiser.
    
    Args:
        advertiser_id: The advertiser ID to look up
        
    Returns:
        Dictionary with advertiser details or None if not found
    """
    try:
        query = "SELECT advertiser_id, impressions, conversions, last_updated FROM advertisers WHERE advertiser_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [advertiser_id], query_description="Get advertiser details by ID")
        
        for row in result:
            return {
                "advertiser_id": row.advertiser_id,
                "impressions": row.impressions,
                "conversions": row.conversions,
                "last_updated": row.last_updated
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching advertiser details for {advertiser_id}: {e}")
        return None


def get_advertiser_dashboard_data(advertiser_id: str) -> Optional[Dict]:
    """
    Get aggregated dashboard data for a specific advertiser including total counts.
    
    Args:
        advertiser_id: The advertiser ID to look up
        
    Returns:
        Dictionary with advertiser dashboard data or None if not found
    """
    try:
        query = "SELECT advertiser_id, impressions, conversions, last_updated FROM advertisers WHERE advertiser_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [advertiser_id], query_description="Get advertiser dashboard data")
        
        for row in result:
            # Parse JSON data and calculate totals
            total_impressions = _sum_json_counts(row.impressions)
            total_conversions = _sum_json_counts(row.conversions)
            
            return {
                "advertiser_id": row.advertiser_id,
                "name": row.advertiser_id,  # Using ID as name for now
                "total_impressions": total_impressions,
                "total_conversions": total_conversions,
                "last_updated": row.last_updated
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching advertiser dashboard data for {advertiser_id}: {e}")
        return None


def get_advertiser_chart_data(advertiser_id: str) -> Optional[Dict]:
    """
    Get time-series chart data for a specific advertiser formatted for Chart.js.
    
    Args:
        advertiser_id: The advertiser ID to look up
        
    Returns:
        Dictionary with chart data or None if not found
        Format: {
            "labels": ["2023-09-25 10:00", "2023-09-25 10:01", ...],
            "impressions": [100, 120, 95, ...],
            "conversions": [5, 8, 3, ...]
        }
    """
    try:
        query = "SELECT advertiser_id, impressions, conversions FROM advertisers WHERE advertiser_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [advertiser_id], query_description="Get advertiser chart data")
        
        for row in result:
            impressions_data = _parse_time_series_data(row.impressions)
            conversions_data = _parse_time_series_data(row.conversions)
            
            # Merge and sort by timestamp
            all_timestamps = set()
            impressions_dict = {item['timestamp']: item['count'] for item in impressions_data}
            conversions_dict = {item['timestamp']: item['count'] for item in conversions_data}
            
            all_timestamps.update(impressions_dict.keys())
            all_timestamps.update(conversions_dict.keys())
            
            # Sort timestamps and create chart data
            sorted_timestamps = sorted(all_timestamps)
            
            labels = []
            impressions_values = []
            conversions_values = []
            
            for timestamp in sorted_timestamps:
                # Convert unix timestamp to readable format
                labels.append(_format_timestamp(timestamp))
                impressions_values.append(impressions_dict.get(timestamp, 0))
                conversions_values.append(conversions_dict.get(timestamp, 0))
            
            return {
                "advertiser_id": row.advertiser_id,
                "labels": labels,
                "impressions": impressions_values,
                "conversions": conversions_values
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching advertiser chart data for {advertiser_id}: {e}")
        return None


def _sum_json_counts(json_data: str) -> int:
    """
    Sum up all count values from a JSON string containing an array of time-count tuples.
    
    Args:
        json_data: JSON string like '[{"ts": 1234567890, "count": 10}, ...]'
        
    Returns:
        Total sum of all count values
    """
    try:
        if not json_data or json_data.strip() == '':
            return 0
            
        data = json.loads(json_data)
        if not isinstance(data, list):
            return 0
            
        total = 0
        for item in data:
            if isinstance(item, dict) and 'count' in item:
                total += item.get('count', 0)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # Handle tuple format [timestamp, count]
                total += item[1]
                
        return total
        
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Error parsing JSON data: {e}")
        return 0


def _parse_time_series_data(json_data: str) -> List[Dict]:
    """
    Parse time-series JSON data into a list of timestamp-count dictionaries.
    
    Args:
        json_data: JSON string containing time-count data
        
    Returns:
        List of dictionaries with 'timestamp' and 'count' keys
    """
    try:
        if not json_data or json_data.strip() == '':
            return []
            
        data = json.loads(json_data)
        if not isinstance(data, list):
            return []
            
        result = []
        for item in data:
            if isinstance(item, dict) and 'ts' in item and 'count' in item:
                result.append({
                    'timestamp': item['ts'],
                    'count': item['count']
                })
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # Handle tuple format [timestamp, count]
                result.append({
                    'timestamp': item[0],
                    'count': item[1]
                })
                
        return result
        
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Error parsing time-series JSON data: {e}")
        return []


def _format_timestamp(unix_timestamp: int) -> str:
    """
    Format a unix timestamp for chart display.
    
    Args:
        unix_timestamp: Unix timestamp
        
    Returns:
        Formatted time string
    """
    try:
        dt = time.strftime('%H:%M', time.localtime(unix_timestamp))
        return dt
    except (ValueError, OSError) as e:
        logger.warning(f"Error formatting timestamp {unix_timestamp}: {e}")
        return str(unix_timestamp)


def get_advertiser_conversions(advertiser_id: str) -> List[Dict]:
    """
    Get all conversions for a specific advertiser from the Presto conversions_identified table.
    Ordered by conversion_timestamp DESC (newest first).
    
    Args:
        advertiser_id: The advertiser ID to look up conversions for
        
    Returns:
        List of dictionaries containing conversion data:
        [{"cookie_id": "abc123", "conversion_timestamp": datetime, "advertiser_id": "ADV123", 
          "publisher_id": "PUB456", "impression_timestamp": datetime, "time_to_conversion_seconds": 3600}, ...]
    """
    try:
        query = """
        SELECT advertisers_id, publishers_id, cookie_id, conversion_timestamp, 
               impression_timestamp, time_to_conversion_seconds, created_at
        FROM iceberg_data.affiliate_junction.conversions_identified 
        WHERE advertisers_id = ? 
        ORDER BY conversion_timestamp DESC
        LIMIT 100
        """
        
        result = presto_operations.execute_query_with_retry(
            query, 
            [advertiser_id], 
            query_description=f"Get conversions for advertiser {advertiser_id} from Presto"
        )
        
        conversions = []
        for row in result:
            conversions.append({
                "advertiser_id": row.advertisers_id,
                "publisher_id": row.publishers_id,
                "cookie_id": row.cookie_id,
                "conversion_timestamp": row.conversion_timestamp,
                "impression_timestamp": row.impression_timestamp,
                "time_to_conversion_seconds": row.time_to_conversion_seconds,
                "created_at": row.created_at
            })
        
        logger.info(f"Retrieved {len(conversions)} conversions for advertiser {advertiser_id} from Presto")
        return conversions
        
    except Exception as e:
        logger.error(f"Error fetching conversions for advertiser {advertiser_id} from Presto: {e}")
        return []


def get_all_advertisers() -> List[Dict[str, str]]:
    """
    Get all advertisers from the database.
    Warning: This could return a large dataset depending on your data size.
    
    Returns:
        List of dictionaries containing all advertiser information
    """
    try:
        query = "SELECT advertiser_id FROM advertisers"
        
        result = hcd_operations.execute_query_with_retry(query, query_description="Get all advertisers")
        
        advertisers = []
        for row in result:
            advertisers.append({
                "advertiser_id": row.advertiser_id,
                "name": row.advertiser_id
            })
        
        return advertisers
        
    except Exception as e:
        logger.error(f"Error fetching all advertisers: {e}")
        return []


def get_presto_query_metrics() -> Dict[str, Any]:
    """
    Get comprehensive query metrics for all Presto operations executed through this module.
    
    Returns:
        Dictionary containing:
        - summary: Aggregate statistics (total queries, success rate, average execution time, etc.)
        - queries: Detailed list of all executed queries with individual metrics
        
    Example:
        metrics = get_presto_query_metrics()
        print(f"Total Presto queries: {metrics['summary']['total_queries']}")
        print(f"Average execution time: {metrics['summary']['average_execution_time_ms']}ms")
        
        for query in metrics['queries']:
            print(f"Query: {query['query_description']} - {query['execution_time_ms']}ms")
    """
    try:
        summary = presto_operations.get_query_summary()
        all_queries = presto_operations.get_query_metrics()
        
        return {
            "summary": summary,
            "queries": all_queries,
            "metrics_timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Error fetching Presto query metrics: {e}")
        return {
            "summary": {},
            "queries": [],
            "error": str(e),
            "metrics_timestamp": time.time()
        }


def clear_presto_query_metrics():
    """
    Clear all stored Presto query metrics. Useful for resetting metrics during testing
    or to start fresh metrics collection.
    """
    try:
        presto_operations.clear_query_metrics()
        logger.info("Presto query metrics cleared successfully")
        return {"success": True, "message": "Presto query metrics cleared"}
        
    except Exception as e:
        logger.error(f"Error clearing Presto query metrics: {e}")
        return {"success": False, "error": str(e)}


def test_presto_metrics() -> Dict[str, Any]:
    """
    Test function to check if Presto metrics are being captured correctly.
    Runs a simple test query and returns the metrics.
    """
    try:
        # Clear metrics first
        presto_operations.clear_query_metrics()
        
        # Run a simple test query
        test_query = "SELECT 1 as test_value"
        result = presto_operations.execute_query_simple(
            test_query, 
            query_description="Test query for metrics validation"
        )
        
        # Get metrics
        summary = presto_operations.get_query_summary()
        queries = presto_operations.get_query_metrics()
        
        return {
            "test_result": result,
            "metrics_summary": summary,
            "metrics_queries": queries,
            "metrics_count": len(queries) if queries else 0,
            "test_timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Error testing Presto metrics: {e}")
        return {
            "error": str(e),
            "test_timestamp": time.time()
        }