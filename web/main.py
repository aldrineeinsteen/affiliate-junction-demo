import os
import logging
import prestodb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Import our custom modules
from . import hcd_operations
from . import advertisers
from . import publishers
from .cassandra_wrapper import cassandra_wrapper
from .presto_wrapper import presto_wrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Authentication models
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    message: str

app = FastAPI()

# Global connections
presto_connection = None

# Serve static assets from web/assets
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")

# Jinja2 templates in web/templates
templates = Jinja2Templates(directory="web/templates")

# Authentication helper functions
def set_auth_cookie(response, username: str, password: str):
    """Set authentication cookie with user credentials"""
    # Simple approach for demo: store username and password in cookie
    import base64
    import json
    
    auth_data = json.dumps({"username": username, "password": password})
    encoded_data = base64.b64encode(auth_data.encode()).decode()
    
    response.set_cookie(
        key="auth_token",
        value=encoded_data,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=86400 * 365  # 1 year - persists across restarts
    )

def get_current_user(request: Request) -> Optional[str]:
    """Check if user is authenticated via cookie"""
    token = request.cookies.get("auth_token")
    if not token:
        return None
    
    try:
        import base64
        import json
        
        # Decode the cookie data
        decoded_data = base64.b64decode(token.encode()).decode()
        auth_data = json.loads(decoded_data)
        
        username = auth_data.get("username")
        password = auth_data.get("password")
        
        # Validate against environment variables
        expected_username = os.getenv("WEB_AUTH_USER")
        expected_password = os.getenv("WEB_AUTH_PASSWD")
        
        if username == expected_username and password == expected_password:
            return username
        else:
            return None
            
    except (ValueError, json.JSONDecodeError, KeyError):
        # Invalid cookie data
        return None

def require_auth(request: Request) -> str:
    """Dependency that requires authentication"""
    user = get_current_user(request)
    if not user:
        # For API requests, return 401
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Authentication required")
        # For web pages, we need to handle this differently
        # We'll let the route handle the redirect instead of doing it in the dependency
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def check_auth_or_redirect(request: Request):
    """Helper function to check auth and redirect if necessary for web pages"""
    user = get_current_user(request)
    if not user:
        redirect_url = f"/login?redirect={request.url.path}"
        return RedirectResponse(url=redirect_url, status_code=302)
    return None


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


# --- Authentication routes ---
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, redirect: str = "/"):
    """Display login page"""
    # If user is already authenticated, redirect to intended page
    if get_current_user(request):
        return RedirectResponse(url=redirect, status_code=302)
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """Handle login authentication"""
    expected_username = os.getenv("WEB_AUTH_USER")
    expected_password = os.getenv("WEB_AUTH_PASSWD")
    
    if not expected_username or not expected_password:
        logger.error("Web authentication environment variables not configured")
        return JSONResponse(
            status_code=500,
            content=LoginResponse(
                success=False, 
                message="Server configuration error"
            ).dict()
        )
    
    if login_data.username == expected_username and login_data.password == expected_password:
        # Create response with cookie containing credentials
        response = JSONResponse(
            content=LoginResponse(
                success=True,
                message="Login successful"
            ).dict()
        )
        set_auth_cookie(response, login_data.username, login_data.password)
        
        logger.info(f"User {login_data.username} logged in successfully")
        return response
    else:
        logger.warning(f"Failed login attempt for username: {login_data.username}")
        return JSONResponse(
            status_code=401,
            content=LoginResponse(
                success=False,
                message="Invalid username or password"
            ).dict()
        )

@app.post("/auth/logout")
async def logout(request: Request):
    """Handle logout"""
    response = JSONResponse(content={"success": True, "message": "Logged out successfully"})
    response.delete_cookie("auth_token")
    return response


# --- API endpoint ---
@app.get("/api")
def get_data(request: Request, current_user: str = Depends(require_auth)):
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
def get_advertisers_dropdown(request: Request, current_user: str = Depends(require_auth)):
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


# --- Publishers API endpoint ---
@app.get("/api/publishers")
def get_publishers_dropdown(request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get publishers for dropdown"""
    with cassandra_wrapper.request_context():
        try:
            publishers_list = publishers.get_random_publishers(limit=10)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return {
                "publishers": publishers_list,
                "query_metrics": query_metrics
            }
        except Exception as e:
            logger.error(f"Error fetching publishers: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch publishers", 
                    "publishers": [],
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Details API endpoint ---
@app.get("/api/advertisers/{advertiser_id}")
def get_advertiser_details_endpoint(advertiser_id: str, request: Request, current_user: str = Depends(require_auth)):
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
def get_advertiser_dashboard_endpoint(advertiser_id: str, request: Request, current_user: str = Depends(require_auth)):
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
def get_advertiser_chart_endpoint(advertiser_id: str, request: Request, current_user: str = Depends(require_auth)):
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


# --- Advertiser Conversions API endpoint ---
@app.get("/api/advertisers/{advertiser_id}/conversions")
def get_advertiser_conversions_endpoint(advertiser_id: str, request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get conversions for a specific advertiser"""
    with cassandra_wrapper.request_context(), presto_wrapper.request_context():
        try:
            conversions_data = advertisers.get_advertiser_conversions(advertiser_id)
            
            # Get query metrics for this request (both Cassandra and Presto)
            cassandra_metrics = cassandra_wrapper.get_request_queries()
            presto_metrics = presto_wrapper.get_request_queries()
            
            # Combine both metrics
            combined_metrics = cassandra_metrics + presto_metrics
            
            return {
                "conversions": conversions_data,
                "query_metrics": combined_metrics
            }
            
        except Exception as e:
            logger.error(f"Error fetching advertiser conversions for {advertiser_id}: {e}")
            
            # Still get query metrics even if there was an error
            cassandra_metrics = cassandra_wrapper.get_request_queries()
            presto_metrics = presto_wrapper.get_request_queries()
            combined_metrics = cassandra_metrics + presto_metrics
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch advertiser conversions",
                    "query_metrics": combined_metrics
                }
            )


# --- Advertiser Conversion Timeline API endpoint ---
@app.get("/api/advertisers/{advertiser_id}/conversions/{cookie_id}/timeline")
def get_conversion_timeline_endpoint(
    advertiser_id: str, 
    cookie_id: str, 
    request: Request, 
    current_user: str = Depends(require_auth)
):
    """API endpoint to get impression timeline for a specific conversion"""
    with presto_wrapper.request_context():
        try:
            timeline_data = advertisers.get_conversion_timeline(advertiser_id, cookie_id)
            
            # Get query metrics for this request
            query_metrics = presto_wrapper.get_request_queries()
            
            # Check if there was an error in the timeline data
            if "error" in timeline_data:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": timeline_data["error"],
                        "timeline": timeline_data.get("timeline", []),
                        "query_metrics": query_metrics
                    }
                )
            
            # Return successful response with timeline data and query metrics
            response_data = timeline_data.copy()
            response_data["query_metrics"] = query_metrics
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error fetching conversion timeline for {advertiser_id}/{cookie_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = presto_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch conversion timeline",
                    "detail": str(e),
                    "query_metrics": query_metrics
                }
            )


# --- Publisher Details API endpoint ---
@app.get("/api/publishers/{publisher_id}")
def get_publisher_details_endpoint(publisher_id: str, request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get detailed information for a specific publisher"""
    with cassandra_wrapper.request_context():
        try:
            publisher_details = publishers.get_publisher_details(publisher_id)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            if publisher_details:
                return {
                    "publisher": publisher_details,
                    "query_metrics": query_metrics
                }
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Publisher {publisher_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching publisher details for {publisher_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch publisher details",
                    "query_metrics": query_metrics
                }
            )


# --- Publisher Dashboard API endpoint ---
@app.get("/api/publishers/{publisher_id}/dashboard")
def get_publisher_dashboard_endpoint(publisher_id: str, request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get dashboard data for a specific publisher with aggregated totals"""
    with cassandra_wrapper.request_context():
        try:
            dashboard_data = publishers.get_publisher_dashboard_data(publisher_id)
            
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
                        "error": f"Publisher {publisher_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching publisher dashboard for {publisher_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch publisher dashboard",
                    "query_metrics": query_metrics
                }
            )


# --- Publisher Chart Data API endpoint ---
@app.get("/api/publishers/{publisher_id}/chart")
def get_publisher_chart_endpoint(publisher_id: str, request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get chart data for a specific publisher"""
    with cassandra_wrapper.request_context():
        try:
            chart_data = publishers.get_publisher_chart_data(publisher_id)
            
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
                        "error": f"Publisher {publisher_id} not found",
                        "query_metrics": query_metrics
                    }
                )
        except Exception as e:
            logger.error(f"Error fetching publisher chart data for {publisher_id}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch publisher chart data",
                    "query_metrics": query_metrics
                }
            )


# --- Services Settings API endpoint ---
@app.put("/api/services/{service_name}/settings")
async def update_service_settings(service_name: str, settings: dict, request: Request, current_user: str = Depends(require_auth)):
    """Update settings for a specific service"""
    with cassandra_wrapper.request_context():
        try:
            # Convert settings dict to JSON string
            import json
            settings_json = json.dumps(settings)
            
            # Get Cassandra session
            cassandra_session = hcd_operations.get_cassandra_session()
            
            # Update the settings in the database
            query = """
                UPDATE affiliate_junction.services 
                SET settings = %s, last_updated = toUnixTimestamp(now()) 
                WHERE name = %s
            """
            cassandra_session.execute(query, (settings_json, service_name))
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            logger.info(f"Service settings update metrics: {query_metrics}")
            
            return {
                "message": "Settings updated successfully",
                "service_name": service_name,
                "settings": settings,
                "query_metrics": query_metrics
            }
            
        except Exception as e:
            logger.error(f"Error updating service settings: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to update service settings",
                    "detail": str(e),
                    "query_metrics": query_metrics
                }
            )


# --- Advertiser Dashboard UI endpoint ---
@app.get("/advertiser/{advertiser_id}", response_class=HTMLResponse)
def advertiser_dashboard(request: Request, advertiser_id: str):
    """Advertiser dashboard page"""
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    return templates.TemplateResponse("advertiser_dashboard.html", {
        "request": request, 
        "advertiser_id": advertiser_id
    })


# --- Publisher Dashboard UI endpoint ---
@app.get("/publisher/{publisher_id}", response_class=HTMLResponse)
def publisher_dashboard(request: Request, publisher_id: str):
    """Publisher dashboard page"""
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    return templates.TemplateResponse("publisher_dashboard.html", {
        "request": request, 
        "publisher_id": publisher_id
    })


# --- Services API endpoints ---
@app.get("/api/services")
def get_services_api(request: Request, current_user: str = Depends(require_auth)):
    """API endpoint to get all services data in JSON format"""
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
                
                # Parse the settings JSON if it exists
                parsed_settings = {}
                if row.settings:
                    try:
                        import json
                        parsed_settings = json.loads(row.settings)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse settings JSON for service {row.name}: {e}")
                        parsed_settings = {}

                services.append({
                    'name': row.name,
                    'description': row.description,
                    'last_updated': int(datetime.now(timezone.utc).timestamp() - row.last_updated.replace(tzinfo=timezone.utc).timestamp()),
                    'stats': row.stats,
                    'settings': row.settings,
                    'parsed_settings': parsed_settings,
                    'parsed_stats': parsed_stats
                })
            
            # Sort services in custom order
            service_order = ['generate_traffic', 'hcd_to_presto', 'presto_insights', 'presto_to_hcd', 'presto_cleanup']
            def get_sort_key(service):
                try:
                    return service_order.index(service['name'])
                except ValueError:
                    # If service name not in the defined order, put it at the end
                    return len(service_order)
            
            services.sort(key=get_sort_key)
            
            # Get query metrics for this request
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return {
                "services": services,
                "query_metrics": query_metrics
            }
            
        except Exception as e:
            logger.error(f"Error fetching services data via API: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to fetch services data",
                    "detail": str(e),
                    "services": [],
                    "query_metrics": query_metrics
                }
            )

@app.get("/api/services/{service_name}/query-metrics")
def get_service_query_metrics(service_name: str, request: Request):
    """Get query metrics for a specific service"""
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    with cassandra_wrapper.request_context():
        try:
            # Query the services table for query_metrics for the specific service
            cassandra_session = hcd_operations.get_cassandra_session()
            query = "SELECT name, query_metrics FROM affiliate_junction.services WHERE name = %s"
            result = cassandra_session.execute(query, [service_name])
            
            all_query_metrics = []
            for row in result:
                if row.query_metrics:
                    try:
                        import json
                        service_metrics = json.loads(row.query_metrics)
                        if isinstance(service_metrics, list) and service_metrics:
                            # Add service name to each metric for identification
                            for metric in service_metrics:
                                metric['service_name'] = row.name
                            all_query_metrics.extend(service_metrics)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse query_metrics JSON for service {row.name}: {e}")
                        continue
            
            # Get query metrics for this API request itself
            query_metrics = cassandra_wrapper.get_request_queries()
            
            # Combine service historical metrics with the current API call metrics
            combined_query_metrics = all_query_metrics + query_metrics
            
            logger.info(f"Retrieved {len(all_query_metrics)} query metrics for service {service_name}")
            
            return {
                "query_metrics": combined_query_metrics
            }
            
        except Exception as e:
            logger.error(f"Error fetching query metrics for service {service_name}: {e}")
            
            # Still get query metrics even if there was an error
            query_metrics = cassandra_wrapper.get_request_queries()
            
            return {
                "error": str(e),
                "query_metrics": query_metrics
            }

# --- Services UI endpoint ---
@app.get("/services", response_class=HTMLResponse)
def services_dashboard(request: Request):
    """Service health dashboard page"""
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
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
                
                # Parse the settings JSON if it exists
                parsed_settings = {}
                if row.settings:
                    try:
                        import json
                        parsed_settings = json.loads(row.settings)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse settings JSON for service {row.name}: {e}")
                        parsed_settings = {}
                
                services.append({
                    'name': row.name,
                    'description': row.description,
                    'last_updated': row.last_updated,
                    'stats': row.stats,
                    'settings': row.settings,
                    'parsed_settings': parsed_settings,
                    'parsed_stats': parsed_stats
                })
            
            # Sort services in custom order
            service_order = ['generate_traffic', 'hcd_to_presto', 'presto_insights', 'presto_to_hcd', 'presto_cleanup']
            def get_sort_key(service):
                try:
                    return service_order.index(service['name'])
                except ValueError:
                    # If service name not in the defined order, put it at the end
                    return len(service_order)
            
            services.sort(key=get_sort_key)
            
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


# --- Fraud Detection endpoints ---
@app.get("/fraud", response_class=HTMLResponse)
def fraud_dashboard(request: Request):
    """Fraud detection dashboard page"""
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    return templates.TemplateResponse("fraud_dashboard.html", {"request": request})


@app.get("/api/fraud/stage1")
def get_fraud_stage1_data(request: Request, current_user: str = Depends(require_auth)):
    """API endpoint for fraud detection stage 1 - High conversion cookies"""
    try:
        # Stage 1 query for cookies with high conversions in the last minute
        stage1_query = """
        SELECT cookie_id, count(*) as num
        FROM hcd.affiliate_junction.conversions_by_minute 
        WHERE bucket_date = date_add('minute', -1, date_trunc('minute', now()))
          AND bucket IN (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        GROUP BY cookie_id
        ORDER BY num DESC
        LIMIT 100
        """
        
        # Execute the query using presto_operations
        from .presto_operations import execute_query
        stage1_results = execute_query(
            stage1_query, 
            query_description="Fraud Stage 1: High-conversion cookies last minute"
        )
        
        # Transform results into expected format
        stage1_data = []
        for row in stage1_results:
            # Debug: Log the row structure
            logger.info(f"Stage 1 row type: {type(row)}, content: {row}")
            
            # Handle both Row objects and tuples/lists
            if hasattr(row, '_asdict'):
                # Named tuple or Row object
                row_dict = row._asdict()
                stage1_data.append({
                    'cookie_id': row_dict.get('cookie_id'),
                    'conversion_count': row_dict.get('num')
                })
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                # List or tuple format
                stage1_data.append({
                    'cookie_id': row[0],
                    'conversion_count': row[1]
                })
            else:
                # Try to access as object attributes
                stage1_data.append({
                    'cookie_id': getattr(row, 'cookie_id', None),
                    'conversion_count': getattr(row, 'num', None)
                })
        
        # Get query metrics
        with presto_wrapper.request_context():
            query_metrics = presto_wrapper.get_request_queries()
        
        return {
            "stage1_data": stage1_data,
            "total_cookies": len(stage1_data),
            "timestamp": datetime.now().isoformat(),
            "query_metrics": query_metrics
        }
        
    except Exception as e:
        logger.error(f"Error in fraud stage 1: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to execute fraud stage 1 analysis: {str(e)}"}
        )


@app.post("/api/fraud/stage2")
def get_fraud_stage2_data_optimized(request: Request, stage2_request: dict, current_user: str = Depends(require_auth)):
    """API endpoint for fraud detection stage 2 - Optimized with targeted cookie_ids"""
    try:
        # Extract optimization parameters from request
        cookie_ids = stage2_request.get('cookie_ids', [])
        min_conversions = stage2_request.get('min_conversions', 5)
        
        logger.info(f"Stage 2 optimization: Targeting {len(cookie_ids)} cookies with {min_conversions}+ conversions")
        
        # Create optimized stage 2 query with targeted cookie_ids and conversion filter
        if cookie_ids:
            # Format cookie_ids for SQL IN clause
            cookie_ids_str = "', '".join(cookie_ids)
            cassandra_filter = f"AND cbm.cookie_id IN ('{cookie_ids_str}')"
            iceberg_filter = f"AND ci.cookie_id IN ('{cookie_ids_str}')"
        else:
            cassandra_filter = ""
            iceberg_filter = ""
        
        stage2_query = f"""
        WITH last_minute AS (
          -- Top cookies in the previous full minute (Cassandra) with conversion filter
          SELECT
              cbm.cookie_id,
              COUNT(*) AS num
          FROM hcd.affiliate_junction.conversions_by_minute cbm
          WHERE cbm.bucket_date = date_add('minute', -1, date_trunc('minute', now()))
            AND cbm.bucket IN (0,1,2,3,4,5,6,7,8,9)
            {cassandra_filter}
          GROUP BY cbm.cookie_id
          HAVING COUNT(*) >= {min_conversions}
          ORDER BY num DESC
          LIMIT 100
        ),
        identified_90m AS (
          -- 90-minute window (Iceberg) with targeted cookie_ids
          SELECT
              ci.cookie_id,
              ci.publishers_id
          FROM iceberg_data.affiliate_junction.conversions_identified ci
          WHERE ci.conversion_timestamp >= date_add('minute', -90, date_trunc('minute', now()))
            AND ci.conversion_timestamp <  date_trunc('minute', now())
            {iceberg_filter}
        )
        SELECT
            lm.cookie_id,
            lm.num                                                       AS total_conversions_last_minute,
            COUNT(DISTINCT i90.publishers_id)                            AS unique_publishers_last_90m,
            slice(
              array_sort(array_distinct(array_agg(i90.publishers_id))),
              1, 10
            )                                                           AS sample_publishers_90m
        FROM last_minute lm
        LEFT JOIN identified_90m i90
          ON lm.cookie_id = i90.cookie_id
        GROUP BY lm.cookie_id, lm.num
        ORDER BY total_conversions_last_minute DESC, unique_publishers_last_90m DESC
        """
        
        # Execute the optimized query
        from .presto_operations import execute_query
        stage2_results = execute_query(
            stage2_query, 
            query_description=f"Fraud Stage 2: Optimized publisher analysis ({len(cookie_ids)} targeted cookies, {min_conversions}+ conversions, 90min window)"
        )
        
        # Transform results into expected format
        fraud_data = []
        for row in stage2_results:
            # Debug: Log the row structure
            logger.debug(f"Stage 2 row type: {type(row)}, content: {row}")
            
            # Handle both Row objects and tuples/lists
            if hasattr(row, '_asdict'):
                # Named tuple or Row object
                row_dict = row._asdict()
                fraud_data.append({
                    'cookie_id': row_dict.get('cookie_id'),
                    'total_conversions_last_minute': row_dict.get('total_conversions_last_minute'),
                    'unique_publishers_last_90m': row_dict.get('unique_publishers_last_90m', 0),
                    'sample_publishers_90m': row_dict.get('sample_publishers_90m', [])
                })
            elif isinstance(row, (list, tuple)) and len(row) >= 4:
                # List or tuple format
                fraud_data.append({
                    'cookie_id': row[0],
                    'total_conversions_last_minute': row[1],
                    'unique_publishers_last_90m': row[2] if row[2] is not None else 0,
                    'sample_publishers_90m': row[3] if row[3] is not None else []
                })
            else:
                # Try to access as object attributes
                fraud_data.append({
                    'cookie_id': getattr(row, 'cookie_id', None),
                    'total_conversions_last_minute': getattr(row, 'total_conversions_last_minute', None),
                    'unique_publishers_last_90m': getattr(row, 'unique_publishers_last_90m', 0),
                    'sample_publishers_90m': getattr(row, 'sample_publishers_90m', [])
                })
        
        # Calculate summary statistics based on risk levels
        summary = {'high': 0, 'medium': 0, 'low': 0, 'clean': 0}
        for fraud in fraud_data:
            conversions = fraud['total_conversions_last_minute'] or 0
            publishers = fraud['unique_publishers_last_90m'] or 0
            
            # Calculate risk level using same logic as JavaScript
            if conversions >= 20 and publishers >= 10:
                summary['high'] += 1
            elif conversions >= 10 and publishers >= 5:
                summary['medium'] += 1
            elif conversions >= 5 or publishers >= 3:
                summary['low'] += 1
            else:
                summary['clean'] += 1
        
        # Get query metrics
        with presto_wrapper.request_context():
            query_metrics = presto_wrapper.get_request_queries()
        
        logger.info(f"Stage 2 optimization: Processed {len(fraud_data)} records with {min_conversions}+ conversions filter")
        
        return {
            "fraud_data": fraud_data,
            "summary": summary,
            "last_updated": datetime.now().isoformat(),
            "analysis_window": f"90 minutes publisher analysis (optimized: {len(cookie_ids)} targeted cookies, {min_conversions}+ conversions)",
            "total_analyzed": len(fraud_data),
            "query_metrics": query_metrics
        }
        
    except Exception as e:
        logger.error(f"Error in optimized fraud stage 2: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to execute optimized fraud stage 2 analysis: {str(e)}"}
        )


@app.get("/api/fraud/stage2")
def get_fraud_stage2_data(request: Request, current_user: str = Depends(require_auth)):
    """API endpoint for fraud detection stage 2 - Enhanced publisher analysis (fallback)"""
    try:
        # Stage 2 query with CTE for comprehensive analysis (original version for fallback)
        stage2_query = """
        WITH last_minute AS (
          -- Top cookies in the previous full minute (Cassandra)
          SELECT
              cbm.cookie_id,
              COUNT(*) AS num
          FROM hcd.affiliate_junction.conversions_by_minute cbm
          WHERE cbm.bucket_date = date_add('minute', -1, date_trunc('minute', now()))
            AND cbm.bucket IN (0,1,2,3,4,5,6,7,8,9)
          GROUP BY cbm.cookie_id
          ORDER BY num DESC
          LIMIT 100
        ),
        identified_90m AS (
          -- 90-minute window (Iceberg)
          SELECT
              ci.cookie_id,
              ci.publishers_id
          FROM iceberg_data.affiliate_junction.conversions_identified ci
          WHERE ci.conversion_timestamp >= date_add('minute', -90, date_trunc('minute', now()))
            AND ci.conversion_timestamp <  date_trunc('minute', now())
        )
        SELECT
            lm.cookie_id,
            lm.num                                                       AS total_conversions_last_minute,
            COUNT(DISTINCT i90.publishers_id)                            AS unique_publishers_last_90m,
            slice(
              array_sort(array_distinct(array_agg(i90.publishers_id))),
              1, 10
            )                                                           AS sample_publishers_90m
        FROM last_minute lm
        LEFT JOIN identified_90m i90
          ON lm.cookie_id = i90.cookie_id
        GROUP BY lm.cookie_id, lm.num
        ORDER BY total_conversions_last_minute DESC, unique_publishers_last_90m DESC
        """
        
        # Execute the query using presto_operations
        from .presto_operations import execute_query
        stage2_results = execute_query(
            stage2_query, 
            query_description="Fraud Stage 2: Enhanced publisher analysis (90min window, fallback mode)"
        )
        # Transform results into expected format
        fraud_data = []
        for row in stage2_results:
            # Debug: Log the row structure
            logger.debug(f"Stage 2 fallback row type: {type(row)}, content: {row}")
            
            # Handle both Row objects and tuples/lists
            if hasattr(row, '_asdict'):
                # Named tuple or Row object
                row_dict = row._asdict()
                fraud_data.append({
                    'cookie_id': row_dict.get('cookie_id'),
                    'total_conversions_last_minute': row_dict.get('total_conversions_last_minute'),
                    'unique_publishers_last_90m': row_dict.get('unique_publishers_last_90m', 0),
                    'sample_publishers_90m': row_dict.get('sample_publishers_90m', [])
                })
            elif isinstance(row, (list, tuple)) and len(row) >= 4:
                # List or tuple format
                fraud_data.append({
                    'cookie_id': row[0],
                    'total_conversions_last_minute': row[1],
                    'unique_publishers_last_90m': row[2] if row[2] is not None else 0,
                    'sample_publishers_90m': row[3] if row[3] is not None else []
                })
            else:
                # Try to access as object attributes
                fraud_data.append({
                    'cookie_id': getattr(row, 'cookie_id', None),
                    'total_conversions_last_minute': getattr(row, 'total_conversions_last_minute', None),
                    'unique_publishers_last_90m': getattr(row, 'unique_publishers_last_90m', 0),
                    'sample_publishers_90m': getattr(row, 'sample_publishers_90m', [])
                })
        
        # Calculate summary statistics based on risk levels
        summary = {'high': 0, 'medium': 0, 'low': 0, 'clean': 0}
        for fraud in fraud_data:
            conversions = fraud['total_conversions_last_minute'] or 0
            publishers = fraud['unique_publishers_last_90m'] or 0
            
            # Calculate risk level using same logic as JavaScript
            if conversions >= 20 and publishers >= 10:
                summary['high'] += 1
            elif conversions >= 10 and publishers >= 5:
                summary['medium'] += 1
            elif conversions >= 5 or publishers >= 3:
                summary['low'] += 1
            else:
                summary['clean'] += 1
        
        # Get query metrics
        with presto_wrapper.request_context():
            query_metrics = presto_wrapper.get_request_queries()
        
        return {
            "fraud_data": fraud_data,
            "summary": summary,
            "last_updated": datetime.now().isoformat(),
            "analysis_window": "90 minutes publisher analysis + 1 minute conversion window (fallback mode)",
            "total_analyzed": len(fraud_data),
            "query_metrics": query_metrics
        }
        
    except Exception as e:
        logger.error(f"Error in fraud stage 2 fallback: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to execute fraud stage 2 analysis: {str(e)}"}
        )


@app.get("/api/fraud")
def get_fraud_data(request: Request, current_user: str = Depends(require_auth)):
    """API endpoint for fraud detection data (legacy - redirects to stage 2)"""
    return get_fraud_stage2_data(request, current_user)


# --- UI endpoint ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Check authentication and redirect if necessary
    redirect_response = check_auth_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    return templates.TemplateResponse("index.html", {"request": request})
