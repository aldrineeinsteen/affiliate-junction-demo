import os
import logging
import prestodb
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ExecutionProfile
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI()

# Global connections
cassandra_session = None
presto_connection = None

# Serve static assets from web/assets
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")

# Jinja2 templates in web/templates
templates = Jinja2Templates(directory="web/templates")


def connect_to_cassandra():
    """Establish connection to Cassandra cluster - reusing from hcd_to_presto.py"""
    global cassandra_session
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
        
        cluster = Cluster(
            [os.getenv('HCD_HOST', 'localhost')],
            port=int(os.getenv('HCD_PORT', '9042')),
            auth_provider=auth_provider,
            protocol_version=5,
            execution_profiles={'default': profile}
        )
        
        cassandra_session = cluster.connect()
        
        # Set keyspace if specified
        if os.getenv('HCD_KEYSPACE'):
            cassandra_session.set_keyspace(os.getenv('HCD_KEYSPACE'))
        
        logger.info(f"Connected to Cassandra cluster at {os.getenv('HCD_HOST', 'localhost')}:{os.getenv('HCD_PORT', '9042')}")
        return cassandra_session
        
    except Exception as e:
        logger.error(f"Failed to connect to Cassandra: {e}")
        raise


def connect_to_presto():
    """Establish connection to Presto"""
    global presto_connection
    try:           
        presto_connection = prestodb.dbapi.connect(
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
        presto_connection._http_session.verify = "/certs/presto.crt"
        
        logger.info(f"Connected to Presto at {os.getenv('PRESTO_HOST')}:{os.getenv('PRESTO_PORT')}")
        return presto_connection
        
    except Exception as e:
        logger.error(f"Failed to connect to Presto: {e}")
        raise


# Initialize connections on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database connections on app startup"""
    try:
        connect_to_cassandra()
        connect_to_presto()
        logger.info("Database connections initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {e}")
        # Don't fail startup - connections can be retried in endpoints


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on app shutdown"""
    try:
        if cassandra_session:
            cassandra_session.shutdown()
            logger.info("Cassandra connection closed")
        
        if presto_connection:
            presto_connection.close()
            logger.info("Presto connection closed")
            
    except Exception as e:
        logger.error(f"Error during connection cleanup: {e}")


# --- API endpoint ---
@app.get("/api")
def get_data():
    """API endpoint with database connection status"""
    connection_status = {
        "cassandra": "connected" if cassandra_session else "disconnected",
        "presto": "connected" if presto_connection else "disconnected"
    }
    
    return {
        "message": "Hello from the API", 
        "data": [1, 2, 3, 4, 5],
        "database_connections": connection_status,
        "environment_loaded": bool(os.getenv('HCD_HOST'))
    }


# --- UI endpoint ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
