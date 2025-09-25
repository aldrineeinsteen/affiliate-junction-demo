import logging
from typing import List, Dict, Optional
from . import hcd_operations
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
        
        result = hcd_operations.execute_query_with_retry(query, [limit * 3])  # Get more than needed to allow for filtering
        
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
        
        result = hcd_operations.execute_query_with_retry(query, [advertiser_id])
        
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
        
        result = hcd_operations.execute_query_with_retry(query, [advertiser_id])
        
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


def get_all_advertisers() -> List[Dict[str, str]]:
    """
    Get all advertisers from the database.
    Warning: This could return a large dataset depending on your data size.
    
    Returns:
        List of dictionaries containing all advertiser information
    """
    try:
        query = "SELECT advertiser_id FROM advertisers"
        
        result = hcd_operations.execute_query_with_retry(query)
        
        advertisers = []
        for row in result:
            advertisers.append({
                "advertiser_id": row.advertiser_id,
                "name": row.advertiser_id
            })
        
        logger.info(f"Retrieved all {len(advertisers)} advertisers")
        return advertisers
        
    except Exception as e:
        logger.error(f"Error fetching all advertisers: {e}")
        return []