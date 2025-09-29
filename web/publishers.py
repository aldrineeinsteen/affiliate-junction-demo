import logging
from typing import List, Dict, Optional
from . import hcd_operations
import random
import json
import time

# Configure logging
logger = logging.getLogger(__name__)


def get_random_publishers(limit: int = 10) -> List[Dict]:
    """
    Get a random selection of publishers from the HCD publishers table with impression
    and conversion data, sorted by conversions DESC first, then impressions DESC second.
    
    Args:
        limit: Maximum number of publishers to return (default: 10)
        
    Returns:
        List of dictionaries containing publisher information with metrics:
        [
            {
                "publisher_id": "PUB123", 
                "name": "PUB123",
                "total_impressions": 1500,
                "total_conversions": 25,
                "last_updated": "2023-09-29 10:30:00"
            }, 
            ...
        ]
        Sorted by conversions DESC, then impressions DESC
    """
    try:
        # Query to get publishers with impression and conversion data
        query = "SELECT publisher_id, impressions, conversions, last_updated FROM publishers LIMIT ?"
        
        result = hcd_operations.execute_query_with_retry(query, [limit * 5], query_description="Fetch publishers with metrics for random selection")  # Get more than needed to allow for filtering
        
        publishers = []
        for row in result:
            # Parse JSON data and calculate totals
            total_impressions = _sum_json_counts(row.impressions)
            total_conversions = _sum_json_counts(row.conversions)
            
            publishers.append({
                "publisher_id": row.publisher_id,
                "name": row.publisher_id,  # Using ID as display name for now
                "total_impressions": total_impressions,
                "total_conversions": total_conversions,
                "last_updated": row.last_updated
            })
        
        # Sort by conversions DESC first, then impressions DESC second
        publishers.sort(key=lambda x: (x['total_conversions'], x['total_impressions']), reverse=True)
        
        # Randomly shuffle the sorted list and take the limit
        random.shuffle(publishers)
        selected_publishers = publishers[:limit]
        
        logger.info(f"Retrieved {len(selected_publishers)} random publishers with metrics")
        return selected_publishers
        
    except Exception as e:
        logger.error(f"Error fetching random publishers: {e}")
        return []


def get_publisher_details(publisher_id: str) -> Optional[Dict]:
    """
    Get detailed information for a specific publisher.
    
    Args:
        publisher_id: The publisher ID to look up
        
    Returns:
        Dictionary with publisher details or None if not found
    """
    try:
        query = "SELECT publisher_id, impressions, conversions, last_updated FROM publishers WHERE publisher_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [publisher_id], query_description="Get publisher details by ID")
        
        for row in result:
            return {
                "publisher_id": row.publisher_id,
                "impressions": row.impressions,
                "conversions": row.conversions,
                "last_updated": row.last_updated
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching publisher details for {publisher_id}: {e}")
        return None


def get_publisher_dashboard_data(publisher_id: str) -> Optional[Dict]:
    """
    Get aggregated dashboard data for a specific publisher including total counts.
    
    Args:
        publisher_id: The publisher ID to look up
        
    Returns:
        Dictionary with publisher dashboard data or None if not found
    """
    try:
        query = "SELECT publisher_id, impressions, conversions, last_updated FROM publishers WHERE publisher_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [publisher_id], query_description="Get publisher dashboard data")
        
        for row in result:
            # Parse JSON data and calculate totals
            total_impressions = _sum_json_counts(row.impressions)
            total_conversions = _sum_json_counts(row.conversions)
            
            return {
                "publisher_id": row.publisher_id,
                "name": row.publisher_id,  # Using ID as name for now
                "total_impressions": total_impressions,
                "total_conversions": total_conversions,
                "last_updated": row.last_updated
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching publisher dashboard data for {publisher_id}: {e}")
        return None


def get_publisher_chart_data(publisher_id: str) -> Optional[Dict]:
    """
    Get time-series chart data for a specific publisher formatted for Chart.js.
    
    Args:
        publisher_id: The publisher ID to look up
        
    Returns:
        Dictionary with chart data or None if not found
        Format: {
            "labels": ["2023-09-25 10:00", "2023-09-25 10:01", ...],
            "impressions": [100, 120, 95, ...],
            "conversions": [5, 8, 3, ...]
        }
    """
    try:
        query = "SELECT publisher_id, impressions, conversions FROM publishers WHERE publisher_id = ?"
        
        result = hcd_operations.execute_query_with_retry(query, [publisher_id], query_description="Get publisher chart data")
        
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
                "publisher_id": row.publisher_id,
                "labels": labels,
                "impressions": impressions_values,
                "conversions": conversions_values
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching publisher chart data for {publisher_id}: {e}")
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


def get_all_publishers() -> List[Dict[str, str]]:
    """
    Get all publishers from the database.
    Warning: This could return a large dataset depending on your data size.
    
    Returns:
        List of dictionaries containing all publisher information
    """
    try:
        query = "SELECT publisher_id FROM publishers"
        
        result = hcd_operations.execute_query_with_retry(query, query_description="Get all publishers")
        
        publishers = []
        for row in result:
            publishers.append({
                "publisher_id": row.publisher_id,
                "name": row.publisher_id
            })
        
        return publishers
        
    except Exception as e:
        logger.error(f"Error fetching all publishers: {e}")
        return []