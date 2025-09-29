#!/usr/bin/env python

import os
import sys
import time
import logging
import random
import uuid
import json
from datetime import datetime, timezone, date, timedelta
from collections import defaultdict, deque
from cassandra.util import uuid_from_time

# Import shared modules
from affiliate_common import CassandraConnection, ServicesManager, SchemaExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CookieImpressionTracker:
    """In-memory tracker for cookie impressions with sliding 90-minute window"""
    
    def __init__(self, window_minutes=90):
        self.window_minutes = window_minutes
        # cookie_id -> deque of impression timestamps
        self.cookie_impressions = defaultdict(deque)
        self.total_impressions_tracked = 0
        self.cleanup_counter = 0
        
    def record_impression(self, cookie_id, timestamp):
        """Record an impression for a cookie"""
        self.cookie_impressions[cookie_id].append(timestamp)
        self.total_impressions_tracked += 1
        self.cleanup_counter += 1
        
        # Periodic cleanup every 1000 impressions to prevent memory bloat
        if self.cleanup_counter >= 1000:
            self._cleanup_all_cookies(timestamp)
            self.cleanup_counter = 0
    
    def get_eligible_cookies(self, current_time):
        """Get set of cookies that have impressions in the last window_minutes"""
        eligible_cookies = set()
        cutoff_time = current_time - timedelta(minutes=self.window_minutes)
        
        for cookie_id in list(self.cookie_impressions.keys()):
            self._cleanup_old_impressions(cookie_id, current_time)
            if self.cookie_impressions[cookie_id]:  # Has recent impressions
                eligible_cookies.add(cookie_id)
        
        return eligible_cookies
    
    def has_recent_impression(self, cookie_id, current_time):
        """Check if cookie has impression in the last window_minutes"""
        if cookie_id not in self.cookie_impressions:
            return False
        
        self._cleanup_old_impressions(cookie_id, current_time)
        return len(self.cookie_impressions[cookie_id]) > 0
    
    def get_stats(self, current_time):
        """Get tracking statistics"""
        # Clean up before calculating stats
        self._cleanup_all_cookies(current_time)
        
        eligible_cookies = len([cookie_id for cookie_id in self.cookie_impressions.keys() 
                               if self.cookie_impressions[cookie_id]])
        total_recent_impressions = sum(len(impressions) for impressions in self.cookie_impressions.values())
        
        return {
            'eligible_cookies_count': eligible_cookies,
            'total_recent_impressions': total_recent_impressions,
            'total_impressions_tracked': self.total_impressions_tracked,
            'tracked_cookies_count': len(self.cookie_impressions)
        }
    
    def _cleanup_old_impressions(self, cookie_id, current_time):
        """Remove impressions older than the window for a specific cookie"""
        cutoff_time = current_time - timedelta(minutes=self.window_minutes)
        impressions = self.cookie_impressions[cookie_id]
        
        while impressions and impressions[0] < cutoff_time:
            impressions.popleft()
        
        # Remove empty entries to save memory
        if not impressions:
            del self.cookie_impressions[cookie_id]
    
    def _cleanup_all_cookies(self, current_time):
        """Clean up old impressions for all cookies"""
        # Make a copy of keys to avoid dictionary size change during iteration
        cookie_ids = list(self.cookie_impressions.keys())
        for cookie_id in cookie_ids:
            self._cleanup_old_impressions(cookie_id, current_time)


class SyntheticTrafficGenerator:
    def __init__(self):
        self.cassandra_connection = None
        self.cassandra_session = None
        self.services_manager = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        ServicesManager.load_environment()
        
        # Store current settings for comparison
        self.current_settings = {
            'AFFILIATE_JUNCTION_ADVERTISERS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_ADVERTISERS_COUNT')),
            'AFFILIATE_JUNCTION_PUBLISHERS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_PUBLISHERS_COUNT')),
            'AFFILIATE_JUNCTION_COOKIES_COUNT': int(os.getenv('AFFILIATE_JUNCTION_COOKIES_COUNT')),
            'AFFILIATE_JUNCTION_HISTORY_MINS': int(os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')),
            'AFFILIATE_JUNCTION_TRAFFIC_MIN': int(os.getenv('AFFILIATE_JUNCTION_TRAFFIC_MIN')),
            'AFFILIATE_JUNCTION_SALES_MIN': int(os.getenv('AFFILIATE_JUNCTION_SALES_MIN')),
            'AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT': int(os.getenv('AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT')),
            'AFFILIATE_JUNCTION_FRAUD_COOKIES_COUNT': int(os.getenv('AFFILIATE_JUNCTION_FRAUD_COOKIES_COUNT', '5')),
            'AFFILIATE_JUNCTION_COHORTS': os.getenv('AFFILIATE_JUNCTION_COHORTS', 'TECH,FASHION,HEALTH,FINANCE,TRAVEL').split(','),
            'AFFILIATE_JUNCTION_COHORT_SAME_PROBABILITY': float(os.getenv('AFFILIATE_JUNCTION_COHORT_SAME_PROBABILITY', '0.60')),
            'AFFILIATE_JUNCTION_COHORT_DIFFERENT_PROBABILITY': float(os.getenv('AFFILIATE_JUNCTION_COHORT_DIFFERENT_PROBABILITY', '0.20')),
            'AFFILIATE_JUNCTION_FRAUD_CROSS_CONTAMINATION_PROBABILITY': float(os.getenv('AFFILIATE_JUNCTION_FRAUD_CROSS_CONTAMINATION_PROBABILITY', '0.05')),
            'AFFILIATE_JUNCTION_RANDOM_COOKIE_PROBABILITY': float(os.getenv('AFFILIATE_JUNCTION_RANDOM_COOKIE_PROBABILITY', '0.15'))
        }
        
        # Generate structured publisher and cookie data
        self.generate_structured_data()
        
        # Initialize cookie impression tracker for attribution
        self.cookie_tracker = CookieImpressionTracker(
            window_minutes=self.current_settings['AFFILIATE_JUNCTION_HISTORY_MINS']
        )
        
        # Initialize stats tracking with timeseries data structure
        self.stats_timeseries = {
            'impression_aggregates_count': [],
            'total_impressions': [],
            'impressions_by_minute_count': [],
            'conversion_count': [],
            'conversions_by_minute_count': [],
            'execution_time_seconds': [],
            'current_advertisers_count': [],
            'current_publishers_count': [],
            'current_cookies_count': [],
            'traffic_per_minute': [],
            'sales_per_minute': []
        }
        
        logger.info(f"Generated {len(self.advertisers)} advertisers, {len(self.publishers_data)} publishers across {len(self.cohorts)} cohorts")
        logger.info(f"Created {len(self.fraud_cookies)} fraud cookies and {len(self.cohort_cookies)} cohort cookies")
        logger.info(f"Using cohorts: {', '.join(self.cohorts)}")
        
    def generate_structured_data(self):
        """Generate structured data with cohorts and fraud patterns"""
        # Get cohorts from current settings
        self.cohorts = self.current_settings['AFFILIATE_JUNCTION_COHORTS']
        
        # Generate advertisers (unchanged)
        self.advertisers = [f"AID_{i+1:06d}" for i in range(self.current_settings['AFFILIATE_JUNCTION_ADVERTISERS_COUNT'])]
        
        # Generate publishers with cohort structure
        self.publishers_data = {}
        self.publishers = []  # Keep flat list for compatibility
        
        publishers_per_cohort = self.current_settings['AFFILIATE_JUNCTION_PUBLISHERS_COUNT'] // len(self.cohorts)
        remaining_publishers = self.current_settings['AFFILIATE_JUNCTION_PUBLISHERS_COUNT'] % len(self.cohorts)
        
        for cohort_idx, cohort in enumerate(self.cohorts):
            # Add extra publisher to first cohorts if there's a remainder
            count = publishers_per_cohort + (1 if cohort_idx < remaining_publishers else 0)
            
            for i in range(count):
                publisher_id = f"PID_{cohort}_{i+1:03d}"
                self.publishers_data[publisher_id] = {
                    'id': publisher_id,
                    'cohort': cohort
                }
                self.publishers.append(publisher_id)
        
        # Generate fraud cookies (configurable count that always associate with specific publishers)
        self.fraud_cookies = {}
        fraud_count = min(self.current_settings['AFFILIATE_JUNCTION_FRAUD_COOKIES_COUNT'], len(self.publishers))
        fraud_publishers = random.sample(self.publishers, fraud_count)
        
        for i, publisher_id in enumerate(fraud_publishers):
            fraud_cookie_id = f"CID_FRAUD_{i+1:03d}"
            self.fraud_cookies[fraud_cookie_id] = publisher_id
        
        # Generate cohort-based cookies
        self.cohort_cookies = {}
        cohort_cookie_count = min(self.current_settings['AFFILIATE_JUNCTION_COOKIES_COUNT'] - len(self.fraud_cookies), 
                                 len(self.publishers) * 2)  # Up to 2 cookies per publisher
        
        cohort_cookies_per_publisher = max(1, cohort_cookie_count // len(self.publishers))
        
        cookie_counter = 1
        for publisher_id in self.publishers:
            cohort = self.publishers_data[publisher_id]['cohort']
            
            for j in range(cohort_cookies_per_publisher):
                if cookie_counter > cohort_cookie_count:
                    break
                    
                cohort_cookie_id = f"CID_{cohort}_{cookie_counter:06d}"
                self.cohort_cookies[cohort_cookie_id] = cohort
                cookie_counter += 1
        
        # Generate remaining random cookies
        remaining_cookies_count = self.current_settings['AFFILIATE_JUNCTION_COOKIES_COUNT'] - len(self.fraud_cookies) - len(self.cohort_cookies)
        self.random_cookies = []
        
        for i in range(remaining_cookies_count):
            random_cookie_id = f"CID_RANDOM_{i+1:06d}"
            self.random_cookies.append(random_cookie_id)
        
        # Create combined cookie pool for easy access
        self.all_cookies = list(self.fraud_cookies.keys()) + list(self.cohort_cookies.keys()) + self.random_cookies
        
        cohort_distribution = ', '.join([f'{cohort}: {sum(1 for p in self.publishers_data.values() if p["cohort"] == cohort)}' for cohort in self.cohorts])
        logger.info(f"Publisher cohort distribution: {cohort_distribution}")
        logger.info(f"Cookie distribution: {len(self.fraud_cookies)} fraud, {len(self.cohort_cookies)} cohort, {len(self.random_cookies)} random")
    
    def get_cookie_for_publisher(self, publisher_id):
        """Get a cookie ID based on publisher relationships and probabilities"""
        # Check if this publisher has associated fraud cookies (always return fraud cookie)
        for fraud_cookie, fraud_publisher in self.fraud_cookies.items():
            if fraud_publisher == publisher_id:
                return fraud_cookie
        
        # Get publisher cohort
        publisher_cohort = self.publishers_data[publisher_id]['cohort']
        
        # Determine cookie selection with probabilities
        rand = random.random()
        
        cohort_same_prob = self.current_settings['AFFILIATE_JUNCTION_COHORT_SAME_PROBABILITY']
        cohort_diff_prob = cohort_same_prob + self.current_settings['AFFILIATE_JUNCTION_COHORT_DIFFERENT_PROBABILITY']
        fraud_cross_prob = cohort_diff_prob + self.current_settings['AFFILIATE_JUNCTION_FRAUD_CROSS_CONTAMINATION_PROBABILITY']
        
        if rand < cohort_same_prob:  # Configurable chance - cohort cookie from same cohort
            cohort_cookies_same = [cookie for cookie, cohort in self.cohort_cookies.items() if cohort == publisher_cohort]
            if cohort_cookies_same:
                return random.choice(cohort_cookies_same)
        
        elif rand < cohort_diff_prob:  # Configurable chance - cohort cookie from different cohort
            cohort_cookies_different = [cookie for cookie, cohort in self.cohort_cookies.items() if cohort != publisher_cohort]
            if cohort_cookies_different:
                return random.choice(cohort_cookies_different)
        
        elif rand < fraud_cross_prob:  # Configurable chance - fraud cookie (cross-contamination)
            if self.fraud_cookies:
                return random.choice(list(self.fraud_cookies.keys()))
        
        # Remaining configurable chance - random cookie
        if self.random_cookies:
            return random.choice(self.random_cookies)
        
        # Fallback to any available cookie
        return random.choice(self.all_cookies)
        
    def execute_schema(self):
        """Execute the Cassandra schema file to create keyspace and tables"""
        try:
            SchemaExecutor.execute_cassandra_schema(self.script_dir, self.cassandra_session)
                
        except Exception as e:
            logger.error(f"Failed to execute schema: {e}")
            raise
    
    
    def get_random_cookie_id(self):
        """Get a random cookie ID from the predefined pool (legacy method for compatibility)"""
        return random.choice(self.all_cookies)
    
    def connect_to_cassandra(self):
        """Establish connection to Cassandra cluster"""
        try:
            self.cassandra_connection = CassandraConnection()
            self.cassandra_session = self.cassandra_connection.connect()
            
            # Prepare statements for data insertion
            self.prepare_statements()
            
            # Initialize services manager after connecting
            self.services_manager = ServicesManager(
                self.cassandra_session, 
                'generate_traffic',
                'Synthetic traffic generation service'
            )
            
            logger.info("Connected to Cassandra cluster")
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {e}")
            sys.exit(1)
    
    def prepare_statements(self):
        """Prepare Cassandra statements for data insertion"""
        try:
            # Prepare statement for impression tracking insert/update (will overwrite if exists)
            self.impression_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions) 
                VALUES (?, ?, ?, ?, ?)
            """)
            
            # Prepare statement for impressions_by_minute table
            self.impressions_by_minute_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.impressions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, impression_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            # Prepare statement for conversion tracking with configurable TTL
            self.conversion_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversion_tracking (advertisers_id, timestamp, cookie_id) 
                VALUES (?, ?, ?)
            """)
            
            # Prepare statement for conversions_by_minute table
            self.conversions_by_minute_insert_stmt = self.cassandra_session.prepare(f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, conversion_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            logger.info(f"Prepared statements for data insertion with {os.getenv('AFFILIATE_JUNCTION_HISTORY_MINS')}-minute TTL")
            
        except Exception as e:
            logger.error(f"Failed to prepare statements: {e}")
            raise
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            service_record = self.services_manager.poll_services_table()
            if service_record:
                self.update_settings_from_service(service_record)
                
        except Exception as e:
            logger.error(f"Failed to poll services table: {e}")
            # Continue with current settings if polling fails
    
    def insert_service_record(self):
        """Insert a new service record with default settings from .env"""
        try:
            self.services_manager.insert_service_record(self.current_settings)
            
        except Exception as e:
            logger.error(f"Failed to insert service record: {e}")
    
    def update_settings_from_service(self, service_record):
        """Update runtime settings if they have changed in the services table"""
        try:
            if service_record.settings:
                new_settings = json.loads(service_record.settings)
                
                # Define type casting functions for each setting
                type_casters = {
                    'AFFILIATE_JUNCTION_ADVERTISERS_COUNT': int,
                    'AFFILIATE_JUNCTION_PUBLISHERS_COUNT': int,
                    'AFFILIATE_JUNCTION_COOKIES_COUNT': int,
                    'AFFILIATE_JUNCTION_HISTORY_MINS': int,
                    'AFFILIATE_JUNCTION_TRAFFIC_MIN': int,
                    'AFFILIATE_JUNCTION_SALES_MIN': int,
                    'AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT': int,
                    'AFFILIATE_JUNCTION_FRAUD_COOKIES_COUNT': int,
                    'AFFILIATE_JUNCTION_COHORTS': lambda x: x.split(',') if isinstance(x, str) else x,
                    'AFFILIATE_JUNCTION_COHORT_SAME_PROBABILITY': float,
                    'AFFILIATE_JUNCTION_COHORT_DIFFERENT_PROBABILITY': float,
                    'AFFILIATE_JUNCTION_FRAUD_CROSS_CONTAMINATION_PROBABILITY': float,
                    'AFFILIATE_JUNCTION_RANDOM_COOKIE_PROBABILITY': float
                }
                
                # Check if settings have changed
                settings_changed = False
                for key, value in new_settings.items():
                    if key in self.current_settings:
                        # Cast to appropriate type
                        if key in type_casters:
                            try:
                                typed_value = type_casters[key](value)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Failed to cast setting {key}={value} to appropriate type: {e}")
                                continue
                        else:
                            typed_value = value
                        
                        # Check if the value has actually changed
                        if self.current_settings[key] != typed_value:
                            logger.info(f"Setting {key} changed from {self.current_settings[key]} to {typed_value}")
                            self.current_settings[key] = typed_value
                            settings_changed = True
                
                # If settings changed, regenerate the data pools
                if settings_changed:
                    self.regenerate_data_pools()
                    logger.info("Settings updated from services table")
                    
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse settings from services table: {e}")
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
    
    def regenerate_data_pools(self):
        """Regenerate advertisers, publishers, and cookie pools based on updated settings"""
        try:
            # Regenerate all structured data
            self.generate_structured_data()
            
            # Reinitialize cookie tracker with updated window size
            self.cookie_tracker = CookieImpressionTracker(
                window_minutes=self.current_settings['AFFILIATE_JUNCTION_HISTORY_MINS']
            )
            
            logger.info(f"Regenerated pools: {len(self.advertisers)} advertisers, {len(self.publishers)} publishers across {len(self.cohorts)} cohorts, {len(self.all_cookies)} total cookies")
            logger.info(f"Reinitialized cookie tracker with {self.current_settings['AFFILIATE_JUNCTION_HISTORY_MINS']}-minute attribution window")
            
        except Exception as e:
            logger.error(f"Failed to regenerate data pools: {e}")
    
    def collect_iteration_stats(self, impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data, execution_time, attribution_stats=None):
        """Collect stats from current iteration"""
        try:
            current_timestamp = int(time.time())
            
            # Calculate total impressions
            total_impressions = sum(record['impressions'] for record in impression_data) if impression_data else 0
            
            # Collect all stats as (timestamp, value) tuples
            stats = {
                'impression_aggregates_count': (current_timestamp, len(impression_data)),
                'total_impressions': (current_timestamp, total_impressions),
                'impressions_by_minute_count': (current_timestamp, len(impressions_by_minute_data)),
                'conversion_count': (current_timestamp, len(conversion_data)),
                'conversions_by_minute_count': (current_timestamp, len(conversions_by_minute_data)),
                'execution_time_seconds': (current_timestamp, round(execution_time, 2)),
                'current_advertisers_count': (current_timestamp, len(self.advertisers)),
                'current_publishers_count': (current_timestamp, len(self.publishers)),
                'current_cookies_count': (current_timestamp, len(self.all_cookies)),
                'traffic_per_minute': (current_timestamp, self.current_settings['AFFILIATE_JUNCTION_TRAFFIC_MIN']),
                'sales_per_minute': (current_timestamp, self.current_settings['AFFILIATE_JUNCTION_SALES_MIN'])
            }
            
            # Add attribution stats if provided
            if attribution_stats:
                stats.update({
                    'attribution_rate': (current_timestamp, round(attribution_stats['attribution_rate'], 3)),
                    'successful_conversions': (current_timestamp, attribution_stats['successful_conversions']),
                    'attempted_conversions': (current_timestamp, attribution_stats['attempted_conversions']),
                    'eligible_cookies_count': (current_timestamp, attribution_stats['eligible_cookies_count'])
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to collect iteration stats: {e}")
            return {}
    
    def update_timeseries_stats(self, iteration_stats):
        """Update timeseries data with new stats, maintaining 90 datapoints"""
        try:
            self.services_manager.update_timeseries_stats(iteration_stats)
            
        except Exception as e:
            logger.error(f"Failed to update timeseries stats: {e}")
    
    def update_service_stats(self):
        """Update the services table with current stats and query metrics"""
        try:
            # Get query metrics from database connection
            cassandra_metrics = self.cassandra_connection.get_query_metrics()
            
            # Update services table with stats and query metrics
            self.services_manager.update_query_metrics(cassandra_metrics=cassandra_metrics)
            
            # Clear metrics after storing them
            self.cassandra_connection.clear_query_metrics()
            
        except Exception as e:
            logger.error(f"Failed to update service stats: {e}")
    
    def generate_synthetic_data(self):
        """Generate synthetic traffic data with fraud patterns and cohort relationships"""
        logger.info("Generating synthetic traffic data with cohort relationships...")
        
        # Get current time clipped to the minute
        now = datetime.now(timezone.utc)
        clipped_timestamp = now.replace(second=0, microsecond=0)
        
        # Get bucket date (floor timestamp to UTC minute)
        bucket_date = clipped_timestamp
        
        # Aggregate impression data by key (publishers_id, cookie_id, timestamp)
        impression_aggregates = {}
        impressions_by_minute_data = []
        
        for _ in range(self.current_settings['AFFILIATE_JUNCTION_TRAFFIC_MIN']):
            publisher_id = random.choice(self.publishers)
            advertiser_id = random.choice(self.advertisers)
            
            # Use structured cookie selection based on publisher relationships
            cookie_id = self.get_cookie_for_publisher(publisher_id)
            
            # Record this impression in the attribution tracker
            self.cookie_tracker.record_impression(cookie_id, now)
            
            # Create a composite key for aggregation
            key = (publisher_id, cookie_id, clipped_timestamp)
            
            if key in impression_aggregates:
                # Increment the count for this key
                impression_aggregates[key]['impressions'] += 1
            else:
                # Create new entry for this key
                impression_aggregates[key] = {
                    'publishers_id': publisher_id,
                    'cookie_id': cookie_id,
                    'timestamp': clipped_timestamp,
                    'advertisers_id': advertiser_id,
                    'impressions': 1
                }
            
            # Generate individual impression for impressions_by_minute table
            # Create a hash bucket based on publisher_id for write distribution
            bucket = hash(publisher_id) % self.current_settings["AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"]
            
            # Generate timeuuid for precise ordering
            ts_uuid = uuid_from_time(now)
            
            # Generate unique impression ID
            impression_id = uuid.uuid4()
            
            impressions_by_minute_data.append({
                'bucket_date': bucket_date,
                'bucket': bucket,
                'ts': ts_uuid,
                'publishers_id': publisher_id,
                'advertisers_id': advertiser_id,
                'cookie_id': cookie_id,
                'impression_id': impression_id
            })
        
        # Convert aggregated data to list
        impression_data = list(impression_aggregates.values())
        
        # Generate conversion tracking data
        conversion_data = []
        conversions_by_minute_data = []
        
        # Get cookies that have had impressions in the last 90 minutes
        eligible_cookies = self.cookie_tracker.get_eligible_cookies(now)
        
        # Track attribution stats
        attempted_conversions = 0
        successful_conversions = 0
        
        for _ in range(self.current_settings['AFFILIATE_JUNCTION_SALES_MIN']):
            advertiser_id = random.choice(self.advertisers)
            publisher_id = random.choice(self.publishers)
            
            # Try to get a cookie that has recent impressions for proper attribution
            cookie_id = self.get_cookie_for_publisher(publisher_id)
            attempted_conversions += 1
            
            # Only generate conversion if this cookie has had impressions in the last 90 minutes
            if cookie_id in eligible_cookies:
                successful_conversions += 1
                
                conversion_data.append({
                    'advertisers_id': advertiser_id,
                    'timestamp': clipped_timestamp,
                    'cookie_id': cookie_id
                })
                
                # Generate individual conversion for conversions_by_minute table
                # Create a hash bucket based on advertiser_id for write distribution
                bucket = hash(advertiser_id) % self.current_settings["AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"]
                
                # Generate timeuuid for precise ordering
                ts_uuid = uuid_from_time(now)
                
                # Generate unique conversion ID
                conversion_id = uuid.uuid4()
                
                conversions_by_minute_data.append({
                    'bucket_date': bucket_date,
                    'bucket': bucket,
                    'ts': ts_uuid,
                    'publishers_id': publisher_id,
                    'advertisers_id': advertiser_id,
                    'cookie_id': cookie_id,
                    'conversion_id': conversion_id
                })
        
        # Store attribution stats for logging
        attribution_stats = {
            'attempted_conversions': attempted_conversions,
            'successful_conversions': successful_conversions,
            'eligible_cookies_count': len(eligible_cookies),
            'attribution_rate': successful_conversions / attempted_conversions if attempted_conversions > 0 else 0
        }
        
        # Count fraud patterns for logging
        fraud_impressions = sum(1 for record in impression_data if record['cookie_id'].startswith('CID_FRAUD_'))
        cohort_impressions = sum(1 for record in impression_data if any(record['cookie_id'].startswith(f'CID_{cohort}_') for cohort in self.cohorts))
        
        # Get cookie tracker stats
        tracker_stats = self.cookie_tracker.get_stats(now)
        
        logger.info(f"Generated {len(impression_data)} aggregated impression records ({sum(record['impressions'] for record in impression_data)} total impressions)")
        logger.info(f"Pattern breakdown: {fraud_impressions} fraud patterns, {cohort_impressions} cohort patterns")
        logger.info(f"Generated {len(impressions_by_minute_data)} minute-based impression records, {len(conversion_data)} conversion records, and {len(conversions_by_minute_data)} minute-based conversion records")
        logger.info(f"Attribution: {attribution_stats['successful_conversions']}/{attribution_stats['attempted_conversions']} conversions ({attribution_stats['attribution_rate']:.1%} rate), {attribution_stats['eligible_cookies_count']} eligible cookies")
        logger.info(f"Cookie tracker: {tracker_stats['eligible_cookies_count']} cookies with recent impressions, {tracker_stats['total_recent_impressions']} total recent impressions")
        
        # Insert data to Cassandra
        self.insert_data_to_cassandra(impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data)
        
        # Return data for stats collection (include attribution stats)
        return impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data, attribution_stats
    
    def execute_batch_in_chunks(self, data, prepared_statement, param_extractor, batch_size=10000, operation_name="records", representative_query=None):
        """Execute batch operations in chunks to avoid Cassandra batch size limits"""
        from cassandra.query import BatchStatement, BatchType
        
        if not data:
            return
            
        total_records = len(data)
        logger.info(f"Processing {total_records} {operation_name} in chunks of {batch_size}...")
        
        # Process data in chunks
        for i in range(0, total_records, batch_size):
            chunk = data[i:i + batch_size]
            
            # Create batch statement for this chunk
            batch = BatchStatement(batch_type=BatchType.UNLOGGED)
            for record in chunk:
                batch.add(prepared_statement, param_extractor(record))
            
            # Execute the batch using connection wrapper to capture metrics
            batch_description = f"Batch insert {len(chunk)} {operation_name}"
            
            # Pass the batch object directly to the wrapper with representative query
            result = self.cassandra_connection.execute_query(
                query=batch,  # Pass the batch object itself
                parameters=None,
                query_description=batch_description,
                representative_query=representative_query
            )
                
            logger.info(f"Batch inserted {len(chunk)} {operation_name} (chunk {i//batch_size + 1}/{(total_records + batch_size - 1)//batch_size})")

    def insert_data_to_cassandra(self, impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data):
        """Insert data into Cassandra using batch operations with dual write pattern"""
        try:
            logger.info("Inserting data to Cassandra using batch operations...")
            
            # Use batch operations for better performance
            from cassandra.query import BatchStatement, BatchType
            
            # Insert impression tracking data using chunked batches
            if impression_data:
                self.execute_batch_in_chunks(
                    impression_data,
                    self.impression_insert_stmt,
                    lambda record: [
                        record['publishers_id'],
                        record['cookie_id'],
                        record['timestamp'],
                        record['advertisers_id'],
                        record['impressions']
                    ],
                    operation_name="impression tracking records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.impression_tracking (publishers_id, cookie_id, timestamp, advertisers_id, impressions) VALUES (?, ?, ?, ?, ?)"""
                )
            
            # Insert impressions_by_minute data using chunked batches (dual write pattern)
            if impressions_by_minute_data:
                self.execute_batch_in_chunks(
                    impressions_by_minute_data,
                    self.impressions_by_minute_insert_stmt,
                    lambda record: [
                        record['bucket_date'],
                        record['bucket'],
                        record['ts'],
                        record['publishers_id'],
                        record['advertisers_id'],
                        record['cookie_id'],
                        record['impression_id']
                    ],
                    operation_name="impressions_by_minute records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.impressions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, impression_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                )
            
            # Insert conversion tracking data using chunked batches
            if conversion_data:
                self.execute_batch_in_chunks(
                    conversion_data,
                    self.conversion_insert_stmt,
                    lambda record: [
                        record['advertisers_id'],
                        record['timestamp'],
                        record['cookie_id']
                    ],
                    operation_name="conversion tracking records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversion_tracking (advertisers_id, timestamp, cookie_id) VALUES (?, ?, ?)"""
                )
            
            # Insert conversions_by_minute data using chunked batches (dual write pattern)
            if conversions_by_minute_data:
                self.execute_batch_in_chunks(
                    conversions_by_minute_data,
                    self.conversions_by_minute_insert_stmt,
                    lambda record: [
                        record['bucket_date'],
                        record['bucket'],
                        record['ts'],
                        record['publishers_id'],
                        record['advertisers_id'],
                        record['cookie_id'],
                        record['conversion_id']
                    ],
                    operation_name="conversions_by_minute records",
                    representative_query=f"""INSERT INTO {os.getenv('HCD_KEYSPACE')}.conversions_by_minute (bucket_date, bucket, ts, publishers_id, advertisers_id, cookie_id, conversion_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                )
            
            logger.info(f"Successfully inserted all data: {len(impression_data)} impression records, {len(impressions_by_minute_data)} impressions_by_minute records, {len(conversion_data)} conversion records, and {len(conversions_by_minute_data)} conversions_by_minute records")
            
        except Exception as e:
            logger.error(f"Failed to insert data to Cassandra: {e}")
            raise
    
    def cleanup(self):
        """Clean up connections"""
        try:
            if self.cassandra_connection:
                self.cassandra_connection.close()
                logger.info("Cassandra connection closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting Synthetic Traffic Generator")
            
            # Execute schema before connecting to Cassandra
            self.execute_schema()
            
            # Connect to databases
            self.connect_to_cassandra()
            
            # Insert initial service record with current settings
            self.insert_service_record()
            
            # Main loop - no-op for now
            logger.info("Entering main loop...")
            
            while True:
                try:
                    # Record start time for this iteration
                    iteration_start = time.time()
                    
                    # Poll services table for configuration updates
                    self.poll_services_table()
                    
                    # Generate and process synthetic data
                    impression_data, impressions_by_minute_data, conversion_data, conversions_by_minute_data, attribution_stats = self.generate_synthetic_data()
                    
                    # Calculate how long the data generation took
                    execution_time = time.time() - iteration_start
                    
                    # Collect stats from this iteration
                    iteration_stats = self.collect_iteration_stats(
                        impression_data, impressions_by_minute_data, 
                        conversion_data, conversions_by_minute_data, 
                        execution_time, attribution_stats
                    )
                    
                    # Update timeseries data with new stats
                    self.update_timeseries_stats(iteration_stats)
                    
                    # Write stats to services table
                    self.update_service_stats()
                    
                    # Sleep for the remaining time to maintain 60-second intervals
                    sleep_time = max(0, 60 - execution_time)
                    logger.info(f"Data generation took {execution_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds until next traffic generation...")
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
    generator = SyntheticTrafficGenerator()
    generator.run()


if __name__ == "__main__":
    main()