#!/usr/bin/env python
"""
Schema execution utilities for affiliate junction demo.
Provides shared logic for executing Cassandra and Presto schema files.
"""

import os
import logging
import subprocess
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

logger = logging.getLogger(__name__)


class SchemaExecutor:
    """Shared schema execution logic"""
    
    @staticmethod
    def execute_cassandra_schema(script_dir, cassandra_session=None):
        """Execute the Cassandra schema file to create keyspace and tables"""
        try:
            schema_file_path = os.path.join(script_dir, 'hcd_schema.cql')
            
            if not os.path.exists(schema_file_path):
                logger.error(f"Schema file not found at: {schema_file_path}")
                raise FileNotFoundError(f"Schema file not found: {schema_file_path}")
            
            logger.info(f"Executing schema file: {schema_file_path}")
            
            # First try using cqlsh
            try:
                SchemaExecutor._execute_schema_with_cqlsh(schema_file_path)
                return
            except Exception as e:
                logger.warning(f"cqlsh execution failed: {e}. Trying direct Cassandra session approach...")
            
            # Fallback to direct Cassandra session execution
            if cassandra_session:
                SchemaExecutor._execute_schema_with_session(schema_file_path, cassandra_session)
            else:
                # Create a temporary session for schema execution
                SchemaExecutor._execute_schema_with_temp_session(schema_file_path)
                
        except Exception as e:
            logger.error(f"Failed to execute schema: {e}")
            raise
    
    @staticmethod
    def _execute_schema_with_cqlsh(schema_file_path):
        """Execute schema using cqlsh command"""
        # Build cqlsh command
        cmd = ['cqlsh']
        
        # Add host and port
        cmd.extend(['-e', f"SOURCE '{schema_file_path}';"])
        cmd.extend([os.getenv('HCD_HOST', 'localhost')])
        cmd.append(str(os.getenv('HCD_PORT', '9042')))
        
        # Add authentication if provided
        if os.getenv('HCD_USER') and os.getenv('HCD_PASSWD'):
            cmd.extend(['-u', os.getenv('HCD_USER')])
            cmd.extend(['-p', os.getenv('HCD_PASSWD')])
        
        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logger.info("Schema executed successfully with cqlsh")
            if result.stdout:
                logger.debug(f"cqlsh output: {result.stdout}")
        else:
            logger.error(f"cqlsh execution failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"cqlsh error: {result.stderr}")
            raise RuntimeError(f"cqlsh execution failed: {result.stderr}")
    
    @staticmethod
    def _execute_schema_with_session(schema_file_path, temp_session):
        """Execute schema using direct Cassandra session"""
        logger.info("Executing schema using direct Cassandra session")
        
        try:
            # Read and execute the schema file
            with open(schema_file_path, 'r') as f:
                schema_content = f.read()
            
            # Split statements by semicolon and execute each one
            statements = [stmt.strip() for stmt in schema_content.split(';') if stmt.strip()]
            
            for statement in statements:
                if statement:
                    logger.debug(f"Executing statement: {statement[:100]}...")
                    temp_session.execute(statement)
            
            logger.info("Schema executed successfully with direct session")
            
        except Exception as e:
            logger.error(f"Failed to execute schema with session: {e}")
            raise
    
    @staticmethod
    def _execute_schema_with_temp_session(schema_file_path):
        """Execute schema using a temporary Cassandra session"""
        logger.info("Executing schema using temporary Cassandra session")
        
        # Create a temporary connection just for schema execution
        auth_provider = None
        if os.getenv('HCD_USER') and os.getenv('HCD_PASSWD'):
            auth_provider = PlainTextAuthProvider(
                username=os.getenv('HCD_USER'),
                password=os.getenv('HCD_PASSWD')
            )
        
        profile = ExecutionProfile(
            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc=os.getenv('HCD_DATACENTER')),
            request_timeout=10
        )
        
        cluster = Cluster(
            [os.getenv('HCD_HOST', 'localhost')],
            port=int(os.getenv('HCD_PORT', '9042')),
            auth_provider=auth_provider,
            protocol_version=5,
            execution_profiles={'default': profile}
        )
        
        temp_session = cluster.connect()
        
        try:
            SchemaExecutor._execute_schema_with_session(schema_file_path, temp_session)
            
        finally:
            temp_session.shutdown()
            cluster.shutdown()
    
    @staticmethod
    def execute_presto_schema(script_dir, presto_connection):
        """Execute the Presto schema file to create tables"""
        try:
            schema_file_path = os.path.join(script_dir, 'presto_schema.sql')
            
            if not os.path.exists(schema_file_path):
                logger.error(f"Presto schema file not found at: {schema_file_path}")
                raise FileNotFoundError(f"Presto schema file not found: {schema_file_path}")
            
            logger.info(f"Executing Presto schema file: {schema_file_path}")
            
            # Read and execute the schema file
            with open(schema_file_path, 'r') as f:
                schema_content = f.read()
            
            # Remove comments and split by semicolons
            lines = schema_content.split('\n')
            cleaned_lines = []
            for line in lines:
                # Remove comments but keep the rest of the line
                if '--' in line:
                    line = line[:line.index('--')]
                cleaned_lines.append(line)
            
            cleaned_content = '\n'.join(cleaned_lines)
            statements = [stmt.strip() for stmt in cleaned_content.split(';') if stmt.strip()]
            
            logger.info(f"Found {len(statements)} SQL statements to execute")
            
            cursor = presto_connection.cursor()
            for i, statement in enumerate(statements, 1):
                if statement:
                    logger.info(f"Executing statement {i}/{len(statements)}: {statement[:100]}...")
                    try:
                        cursor.execute(statement)
                        result = cursor.fetchall()
                        logger.info(f"Statement {i} executed successfully. Result: {result}")
                    except Exception as stmt_error:
                        logger.error(f"Error executing statement {i}: {stmt_error}")
                        logger.error(f"Statement was: {statement}")
                        raise
            
            cursor.close()
            logger.info("Presto schema executed successfully")
            
        except Exception as e:
            logger.error(f"Failed to execute Presto schema: {e}")
            raise