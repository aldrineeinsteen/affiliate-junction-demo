#!/usr/bin/env python
"""
Services table management for affiliate junction demo.
Provides shared logic for services table operations and statistics management.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ServicesManager:
    """Shared services table management logic"""
    
    def __init__(self, cassandra_session, service_name, service_description):
        self.cassandra_session = cassandra_session
        self.service_name = service_name
        self.service_description = service_description
        self.stats_timeseries = {}
    
    @staticmethod
    def load_environment():
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            logger.info("Environment variables loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            raise
    
    def poll_services_table(self):
        """Poll the services table to check for configuration updates"""
        try:
            query = f"SELECT name, description, last_updated, settings FROM {os.getenv('HCD_KEYSPACE')}.services WHERE name = %s"
            result = self.cassandra_session.execute(query, [self.service_name])
            
            service_record = result.one()
            
            if service_record:
                logger.debug(f"Found existing {self.service_name} service record")
                return service_record
            else:
                logger.info(f"No {self.service_name} service record found, inserting new record")
                self.insert_service_record()
                return None
                
        except Exception as e:
            logger.error(f"Failed to poll services table: {e}")
            return None
    
    def insert_service_record(self, settings=None):
        """Insert a new service record with default settings"""
        try:
            settings_json = json.dumps(settings if settings is not None else {})
            
            insert_query = f"""
                INSERT INTO {os.getenv('HCD_KEYSPACE')}.services (name, description, last_updated, settings, stats, query_metrics)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            self.cassandra_session.execute(insert_query, [
                self.service_name,
                self.service_description,
                datetime.now(timezone.utc),
                settings_json,
                '{}',  # Empty stats JSON object
                '[]'   # Empty query metrics JSON array
            ])
            
            logger.info(f"Successfully inserted new {self.service_name} service record")
            
        except Exception as e:
            logger.error(f"Failed to insert service record: {e}")
    
    def update_timeseries_stats(self, iteration_stats):
        """Update timeseries data with new stats, maintaining 90 datapoints"""
        try:
            for metric_name, (timestamp, value) in iteration_stats.items():
                if metric_name not in self.stats_timeseries:
                    self.stats_timeseries[metric_name] = []
                
                # Add new datapoint
                self.stats_timeseries[metric_name].append([timestamp, value])
                
                # Maintain only the most recent 90 datapoints
                if len(self.stats_timeseries[metric_name]) > 90:
                    self.stats_timeseries[metric_name] = self.stats_timeseries[metric_name][-90:]
            
            logger.debug(f"Updated timeseries stats with {len(iteration_stats)} metrics")
            
        except Exception as e:
            logger.error(f"Failed to update timeseries stats: {e}")
    
    def update_service_stats(self, query_metrics=None):
        """Update the services table with current stats and optional query metrics"""
        try:
            # Serialize stats as JSON
            stats_json = json.dumps(self.stats_timeseries)
            
            # Prepare query metrics JSON if provided
            query_metrics_json = json.dumps(query_metrics) if query_metrics else None
            
            if query_metrics_json:
                # Update with query metrics
                update_query = f"""
                    UPDATE {os.getenv('HCD_KEYSPACE')}.services 
                    SET stats = %s, last_updated = %s, query_metrics = %s
                    WHERE name = %s
                """
                self.cassandra_session.execute(update_query, [
                    stats_json,
                    datetime.now(timezone.utc),
                    query_metrics_json,
                    self.service_name
                ])
            else:
                # Update without query metrics (existing behavior)
                update_query = f"""
                    UPDATE {os.getenv('HCD_KEYSPACE')}.services 
                    SET stats = %s, last_updated = %s
                    WHERE name = %s
                """
                self.cassandra_session.execute(update_query, [
                    stats_json,
                    datetime.now(timezone.utc),
                    self.service_name
                ])
            
            logger.debug("Successfully updated service stats" + (" with query metrics" if query_metrics_json else ""))
            
        except Exception as e:
            logger.error(f"Failed to update service stats: {e}")
    
    def update_query_metrics(self, cassandra_metrics=None, presto_metrics=None):
        """Update the services table with query metrics from database connections"""
        try:
            # Combine metrics from both database connections
            all_metrics = []
            
            if cassandra_metrics:
                all_metrics.extend(cassandra_metrics)
                logger.debug(f"Added {len(cassandra_metrics)} Cassandra query metrics")
            
            if presto_metrics:
                all_metrics.extend(presto_metrics)
                logger.debug(f"Added {len(presto_metrics)} Presto query metrics")
            
            # Limit to most recent 50 queries to avoid bloating the services table
            if len(all_metrics) > 50:
                all_metrics = all_metrics[-50:]
            
            # Update services table with query metrics
            self.update_service_stats(query_metrics=all_metrics)
            
            logger.info(f"Updated service with {len(all_metrics)} query metrics")
            
        except Exception as e:
            logger.error(f"Failed to update query metrics: {e}")