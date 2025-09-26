#!/usr/bin/env python
"""
Common utilities and constants for affiliate junction demo.
"""

__version__ = "1.0.0"

# Import commonly used classes for easier access
from .database_connections import CassandraConnection, PrestoConnection
from .services_manager import ServicesManager
from .schema_executor import SchemaExecutor

__all__ = [
    'CassandraConnection',
    'PrestoConnection', 
    'ServicesManager',
    'SchemaExecutor'
]