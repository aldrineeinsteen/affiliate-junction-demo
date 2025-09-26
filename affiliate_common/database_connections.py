#!/usr/bin/env python
"""
Database connection classes for affiliate junction demo.
Provides shared connection logic for Cassandra (HCD) and Presto.
"""

import os
import logging
import prestodb
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

logger = logging.getLogger(__name__)


class CassandraConnection:
    """Shared Cassandra connection logic"""
    
    def __init__(self):
        self.session = None
        self.cluster = None
    
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
    """Shared Presto connection logic"""
    
    def __init__(self):
        self.connection = None
    
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
    
    def close(self):
        """Clean up Presto connection"""
        try:
            if self.connection:
                self.connection.close()
            logger.info("Presto connection closed")
        except Exception as e:
            logger.error(f"Error closing Presto connection: {e}")