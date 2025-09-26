import os
import logging
import prestodb
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import our custom modules
from . import hcd_operations
from . import advertisers
from .cassandra_wrapper import cassandra_wrapper

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
presto_connection = None

# Serve static assets from web/assets
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")

# Jinja2 templates in web/templates
templates = Jinja2Templates(directory="web/templates")


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
        hcd_operations.get_cassandra_session()  # This will initialize the connection
        connect_to_presto()
        logger.info("Database connections initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {e}")
        # Don't fail startup - connections can be retried in endpoints


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on app shutdown"""
    try:
        hcd_operations.close_cassandra_connection()
        
        if presto_connection:
            presto_connection.close()
            logger.info("Presto connection closed")
            
    except Exception as e:
        logger.error(f"Error during connection cleanup: {e}")


# --- API endpoint ---
@app.get("/api")
def get_data():
    """API endpoint with database connection status"""
    with cassandra_wrapper.request_context():
        cassandra_session = hcd_operations.get_cassandra_session()
        connection_status = {
            "cassandra": "connected" if cassandra_session else "disconnected",
            "presto": "connected" if presto_connection else "disconnected"
        }
        
        # Get query metrics for this request
        query_metrics = cassandra_wrapper.get_request_queries()
        
        return {
            "message": "Hello from the API", 
            "data": [1, 2, 3, 4, 5],
            "database_connections": connection_status,
            "environment_loaded": bool(os.getenv('HCD_HOST')),
            "query_metrics": query_metrics
        }


# --- Advertisers API endpoint ---
@app.get("/api/advertisers")
def get_advertisers_dropdown():
    """API endpoint to get advertisers for dropdown"""
    with cassandra_wrapper.request_context():
        try:
            advertisers_list = advertisers.get_random_advertisers(limit=10)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return {
                "advertisers": advertisers_list,
                "query_metrics": query_metrics
            }
        except Exception as e:
            logger.error(f"Error fetching advertisers: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch advertisers", 
                    "advertisers": [],
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Details API endpoint ---
@app.get("/api/advertisers/{advertiser_id}")
def get_advertiser_details_endpoint(advertiser_id: str):
    """API endpoint to get detailed information for a specific advertiser"""
    with cassandra_wrapper.request_context():
        try:
            advertiser_details = advertisers.get_advertiser_details(advertiser_id)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            if advertiser_details:
                return {
                    "advertiser": advertiser_details,
                    "query_metrics": query_metrics
                }
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Advertiser {advertiser_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching advertiser details for {advertiser_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch advertiser details",
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Dashboard API endpoint ---
@app.get("/api/advertisers/{advertiser_id}/dashboard")
def get_advertiser_dashboard_endpoint(advertiser_id: str):
    """API endpoint to get dashboard data for a specific advertiser with aggregated totals"""
    with cassandra_wrapper.request_context():
        try:
            dashboard_data = advertisers.get_advertiser_dashboard_data(advertiser_id)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            if dashboard_data:
                return {
                    "dashboard": dashboard_data,
                    "query_metrics": query_metrics
                }
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Advertiser {advertiser_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching advertiser dashboard for {advertiser_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch advertiser dashboard",
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Chart Data API endpoint ---
@app.get("/api/advertisers/{advertiser_id}/chart")
def get_advertiser_chart_endpoint(advertiser_id: str):
    """API endpoint to get chart data for a specific advertiser"""
    with cassandra_wrapper.request_context():
        try:
            chart_data = advertisers.get_advertiser_chart_data(advertiser_id)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            if chart_data:
                return {
                    "chart": chart_data,
                    "query_metrics": query_metrics
                }
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Advertiser {advertiser_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching advertiser chart data for {advertiser_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch advertiser chart data",
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Dashboard UI endpoint ---
@app.get("/advertiser/{advertiser_id}", response_class=HTMLResponse)
def advertiser_dashboard(request: Request, advertiser_id: str):
    """Advertiser dashboard page"""
    return templates.TemplateResponse("advertiser_dashboard.html", {
        "request": request, 
        "advertiser_id": advertiser_id
    })


# --- Services UI endpoint ---
@app.get("/services", response_class=HTMLResponse)
def services_dashboard(request: Request):
    """Service health dashboard page"""
    with cassandra_wrapper.request_context():
        try:
            # Query the services table
            cassandra_session = hcd_operations.get_cassandra_session()
            query = "SELECT name, description, last_updated, stats, settings FROM affiliate_junction.services"
            result = cassandra_session.execute(query)
            
            services = []
            for row in result:
                # Parse the stats JSON if it exists
                parsed_stats = None
                if row.stats:
                    try:
                        import json
                        parsed_stats = json.loads(row.stats)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse stats JSON for service {row.name}: {e}")
                        parsed_stats = None
                
                services.append({
                    'name': row.name,
                    'description': row.description,
                    'last_updated': row.last_updated,
                    'stats': row.stats,
                    'settings': row.settings,
                    'parsed_stats': parsed_stats
                })
            
            # Sort alphabetically by name in Python
            services.sort(key=lambda x: x['name'])
            
            # Create JSON representation for JavaScript
            import json
            services_json = json.dumps(services, default=str)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            logger.info(f"Services query metrics: {query_metrics}")
            
            return templates.TemplateResponse("services.html", {
                "request": request,
                "services": services,
                "services_json": services_json
            })
            
        except Exception as e:
            logger.error(f"Error fetching services data: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return templates.TemplateResponse("services.html", {
                "request": request,
                "services": [],
                "services_json": "[]",
                "error": f"Failed to fetch services data: {str(e)}"
            })


# --- UI endpoint ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
