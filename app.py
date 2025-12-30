import httpx, json, re, logging

# FastAPI setup
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse 

# Rate limiting libraries
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded 

from lookups import COUNTRIES, STATES
from auth import (
    UserRole, 
    get_current_role, 
    set_user_role, 
    require_role, 
    MANUAL_TEST_ROLE,
    SESSION_ROLE_KEY, 
    ROLE_HIERARCHY
    )
from config import APP_GLOBALS, PRICING, DB_CONFIG, API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES, API_APP_BASE_URL
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import router_etl
import router_search
import router_auth
import router_billing
import router_analytics

from auth_middleware import TemplateAuthMiddleware
from config_docs import (
    get_role_filtered_openapi,
    get_viewer_role_from_request,
    register_visibility_override,
	)
from auth_jwt import require_jwt_role
import config_visibility

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

templates.env.globals.update(APP_GLOBALS)

# ============================================================================
# DATABASE HELPER
# ============================================================================

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Initialize rate limiter
rate_max = "3000/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# ============================================================================
# FASTAPI APP WITH CUSTOM DOCS
# ============================================================================

app = FastAPI(
    title="BoloDoc API",
    description="Enhanced FBI Wanted API data. <br><br><a href='/v1/auth/signup'>Sign up free</a> to get started, then <a href='/v1/auth/login'>log in</a> to see the full API docs",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
	)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================================
# CUSTOM VALIDATION ERROR HANDLER
# ============================================================================

# Build quickstart URL for error messages
QUICKSTART_FIELDS_URL = f"{API_APP_BASE_URL}/quickstart#fields-reference" if API_APP_BASE_URL else "/quickstart#fields-reference"

async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for validation errors that adds helpful reference URLs.
    
    Specifically enhances error messages for invalid field names in search endpoints
    by providing a link to the quickstart page with valid field documentation.
    """
    errors = exc.errors()
    enhanced_errors = []
    
    # Check if this is a search endpoint request
    is_search_endpoint = "/v1/search" in str(request.url.path)
    
    for error in errors:
        error_detail = dict(error)
        
        # Check if this is an invalid field error (enum validation failure)
        error_type = error.get("type", "")
        error_loc = error.get("loc", [])
        error_msg = error.get("msg", "")
        
        # Detect field validation errors in search requests
        # These typically have 'field' in the location path and are enum errors
        is_field_error = (
            is_search_endpoint and 
            any("field" in str(loc).lower() for loc in error_loc) and
            ("literal" in error_type.lower() or 
             "enum" in error_type.lower() or
             "input should be" in error_msg.lower() or
             "unexpected value" in error_msg.lower())
        )
        
        if is_field_error:
            # Extract the invalid value from the error if possible
            invalid_value = None
            if "input" in error_detail:
                invalid_value = error_detail["input"]
            
            # Build enhanced error message
            if invalid_value:
                enhanced_msg = (
                    f"Invalid field name: '{invalid_value}'. "
                    f"See valid fields at: {QUICKSTART_FIELDS_URL}"
                )
            else:
                enhanced_msg = (
                    f"{error_msg}. "
                    f"See valid fields at: {QUICKSTART_FIELDS_URL}"
                )
            
            error_detail["msg"] = enhanced_msg
            error_detail["help_url"] = QUICKSTART_FIELDS_URL
        
        enhanced_errors.append(error_detail)
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": enhanced_errors,
            "help": "For valid field names and operators, see: " + QUICKSTART_FIELDS_URL if is_search_endpoint else None
        }
    )

app.add_exception_handler(RequestValidationError, custom_validation_exception_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(router_billing.router)
if router_billing.test_router:
    app.include_router(router_billing.test_router)
app.include_router(router_etl.router) 
app.include_router(router_search.router)
app.include_router(router_auth.router) 
app.include_router(router_analytics.router, tags=["Analytics"])


# ============================================================================
# CUSTOM ROLE-FILTERED DOCUMENTATION ENDPOINTS
# ============================================================================

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema(request: Request):
    """
    Serve OpenAPI schema filtered by the viewer's role.
    
    Visibility (users see their role level and below):
      - PUBLIC: Only PUBLIC endpoints
      - BASIC: PUBLIC + BASIC endpoints
      - PREMIUM: PUBLIC + BASIC + PREMIUM endpoints
    
    Cache-Control: no-store prevents browser from caching role-specific schemas.
    This ensures users see the correct endpoints after login/logout.
    """
    filtered_schema = get_role_filtered_openapi(app, request)
    return JSONResponse(
        content=filtered_schema,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/docs", include_in_schema=False)
async def get_docs(request: Request):
    """
    Serve Swagger UI with role-filtered endpoints and custom styling.
    Shows different endpoints based on viewer's authentication level.
    
    Cache-Control: no-store ensures fresh content after login/logout.
    """
    viewer_role = get_viewer_role_from_request(request)
    
    # Customize title based on role
    role_labels = {
        UserRole.PUBLIC: "Guest",
        UserRole.BASIC: "Basic",
        UserRole.PREMIUM: "Premium", 
        UserRole.ADMIN: "Admin",
    }
    role_label = role_labels.get(viewer_role, "Guest")
    
    # Get the base Swagger UI HTML response
    html = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"API Docs - BoloDoc",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1}
    )
    
    # Inject custom CSS for better markdown rendering
    html_body = html.body.decode('utf-8')
    # html_body = html_body.replace('</head>', f'{SWAGGER_UI_CUSTOM_CSS}</head>')
    
    # Create response with updated HTML
    response = HTMLResponse(content=html_body)
    
    # Add cache-control headers to prevent browser caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response

@app.get("/redoc", include_in_schema=False)
async def get_redoc(request: Request):
    """
    Serve ReDoc with role-filtered endpoints.
    
    Cache-Control: no-store ensures fresh content after login/logout.
    """
    viewer_role = get_viewer_role_from_request(request)
    
    role_labels = {
        UserRole.PUBLIC: "Guest",
        UserRole.BASIC: "Basic",
        UserRole.PREMIUM: "Premium",
        UserRole.ADMIN: "Admin",
    }
    role_label = role_labels.get(viewer_role, "Guest")
    
    # Get the ReDoc HTML response
    redoc_response = get_redoc_html(
        openapi_url="/openapi.json",
        title=f"Bolo API - {role_label} View",
    )
    
    # Add cache-control headers to prevent browser caching
    redoc_response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    redoc_response.headers["Pragma"] = "no-cache"
    redoc_response.headers["Expires"] = "0"
    
    return redoc_response


# ============================================================================
# MIDDLEWARE
# ============================================================================

# Custom middleware class for role and trimming
class RoleAndTrimMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # TESTING ONLY: Automatically set role from MANUAL_TEST_ROLE
        # NOTE: This is now optional if using JWT authentication
        # You can remove this block once fully migrated to JWT
        if SESSION_ROLE_KEY not in request.session:
            set_user_role(request, MANUAL_TEST_ROLE)
        
        # Trim query parameters (GET data)
        if request.query_params:
            trimmed_query = {}
            for key, value in request.query_params.items():
                if isinstance(value, str):
                    trimmed_value = value.strip()
                    error = validate_string(trimmed_value, key)
                    if error:
                        return JSONResponse(
                            status_code=400,
                            content={"error": error}
                        )
                    trimmed_query[key] = trimmed_value
                else:
                    trimmed_query[key] = value
            request._query_params = trimmed_query
        
        # Trim body data (POST data)
        if request.method in ["POST", "PUT", "PATCH"]:
            # Don't process webhook - it needs raw body for signature verification
            if request.url.path == "/v1/billing/webhook":
                response = await call_next(request)
                return response
            
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                    trimmed_data, error = trim_recursive(data)
                    
                    if error:
                        return JSONResponse(
                            status_code=400,
                            content={"error": error}
                        )
                    
                    # Replace the body with trimmed data
                    async def receive():
                        return {
                            "type": "http.request",
                            "body": json.dumps(trimmed_data).encode(),
                        }
                    request._receive = receive
                except json.JSONDecodeError:
                    pass  # Not JSON, skip trimming
        
        response = await call_next(request)
        return response

# Add custom middleware FIRST (executes LAST due to reverse order)
app.add_middleware(RoleAndTrimMiddleware)

# Add template auth middleware to check JWT cookies and set user_authenticated
app.add_middleware(TemplateAuthMiddleware)

# Add session middleware LAST (executes FIRST due to reverse order)
# NOTE: Can be removed once fully migrated to JWT, but keeping for backward compatibility
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-change-this-in-production-min-32-chars",
    session_cookie="bolo_session",
    max_age=3600,
    same_site="lax",
    https_only=False
)


# ============================================================================
# ROUTES AND TESTING ENDPOINTS
# ============================================================================ 
@app.get("/routes", response_class=HTMLResponse, include_in_schema=False)
async def list_routes(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    List all API routes with their router, endpoint name, auth requirements, and rate limits.
    No authentication required.
    """
    routes_info = []
    
    for route in app.routes:
        # Skip non-API routes (static files, etc.)
        if not hasattr(route, 'methods') or not hasattr(route, 'endpoint'):
            continue
        
        path = getattr(route, 'path', '')
        endpoint = route.endpoint
        endpoint_name = endpoint.__name__ if endpoint else 'N/A'
        methods = ', '.join(sorted(route.methods - {'HEAD', 'OPTIONS'})) if route.methods else 'N/A'
        
        # Determine router name from path prefix
        if path.startswith('/v1/auth'):
            router_name = 'router_auth'
        elif path.startswith('/v1/search'):
            router_name = 'router_search'
        elif path.startswith('/v1/etl'):
            router_name = 'router_etl'
        elif path.startswith('/v1/billing'):
            router_name = 'router_billing'
        else:
            router_name = 'app (root)'
        
        # Check for auth requirements by examining dependencies
        auth_required = 'No'
        required_role = None
        
        # Check route dependencies
        if hasattr(route, 'dependant') and route.dependant:
            for dep in route.dependant.dependencies:
                dep_call = dep.call
                # Check if it's a require_jwt_role dependency
                if hasattr(dep_call, '__name__') and dep_call.__name__ == 'role_checker':
                    auth_required = 'Yes'
                    # Try to extract the required role from closure
                    if hasattr(dep_call, '__closure__') and dep_call.__closure__:
                        for cell in dep_call.__closure__:
                            cell_contents = cell.cell_contents
                            if hasattr(cell_contents, 'value'):
                                required_role = cell_contents.value
                                break
                elif hasattr(dep_call, '__name__') and 'jwt' in dep_call.__name__.lower():
                    auth_required = 'Yes'
                elif hasattr(dep_call, '__name__') and 'auth' in dep_call.__name__.lower():
                    auth_required = 'Yes'
        
        if required_role:
            auth_required = f'Yes ({required_role})'
        
        # Extract rate limits from endpoint function decorators
        rate_limits = []
        if hasattr(endpoint, '__wrapped__'):
            # Check for limiter decorators
            wrapped = endpoint
            while hasattr(wrapped, '__wrapped__'):
                if hasattr(wrapped, '_rate_limit'):
                    rate_limits.append(wrapped._rate_limit)
                wrapped = wrapped.__wrapped__
        
        # Try to get rate limit from function attributes
        if hasattr(endpoint, '__self__') and hasattr(endpoint.__self__, 'limit'):
            rate_limits.append(endpoint.__self__.limit)
        
        routes_info.append({
            'path': path,
            'methods': methods,
            'router': router_name,
            'endpoint': endpoint_name,
            'auth_required': auth_required,
            'rate_limits': ', '.join(rate_limits) if rate_limits else 'default'
        })
    
    # Sort by router, then path
    routes_info.sort(key=lambda x: (x['router'], x['path']))
    
    # Build HTML table
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Routes</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #3d4461; color: white; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            tr:hover { background-color: #f1f1f1; }
            .method-get { color: #61affe; font-weight: bold; }
            .method-post { color: #49cc90; font-weight: bold; }
            .method-put { color: #fca130; font-weight: bold; }
            .method-delete { color: #f93e3e; font-weight: bold; }
            .auth-yes { color: #49cc90; }
            .auth-no { color: #999; }
        </style>
    </head>
    <body>
        <h1>API Routes</h1>
        <p>Total routes: """ + str(len(routes_info)) + """</p>
        <table>
            <tr>
                <th>Path</th>
                <th>Methods</th>
                <th>Router</th>
                <th>Endpoint</th>
                <th>Auth Required</th>
                <th>Rate Limits</th>
            </tr>
    """
    
    for route in routes_info:
        method_class = ''
        if 'GET' in route['methods']:
            method_class = 'method-get'
        elif 'POST' in route['methods']:
            method_class = 'method-post'
        elif 'PUT' in route['methods']:
            method_class = 'method-put'
        elif 'DELETE' in route['methods']:
            method_class = 'method-delete'
        
        auth_class = 'auth-yes' if route['auth_required'].startswith('Yes') else 'auth-no'
        
        html += f"""
            <tr>
                <td>{route['path']}</td>
                <td class="{method_class}">{route['methods']}</td>
                <td>{route['router']}</td>
                <td>{route['endpoint']}</td>
                <td class="{auth_class}">{route['auth_required']}</td>
                <td>{route['rate_limits']}</td>
            </tr>
        """
    
    html += """
        </table>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


# ============================================================================
# ROOT AND STATIC ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")  # More permissive for landing page
async def home(request: Request):
    """Home page with API overview and login/signup links"""
    # Get session role
    current_role = get_current_role(request)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "current_role": current_role.value,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
        }
    )

@app.get("/quickstart", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")
async def quickstart_page(request: Request):
    """QuickStart guide for authenticated users"""
    current_role = get_current_role(request)
    
    # Get user's API key if authenticated
    user_api_key = None
    if request.state.user_authenticated and request.state.user_id:
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT api_key_hash FROM tbl_users WHERE user_id = %s",
                        (request.state.user_id,)
                    )
                    user = cur.fetchone()
                    if user:
                        # Note: We can't decrypt the hash, so we'll show a placeholder
                        # The actual API key was sent via email during registration
                        # Users can reset it from profile page if needed
                        user_api_key = "Check your email or reset from Profile page"
        except Exception as e:
            logger.error(f"Error fetching API key: {str(e)}")
    
    return templates.TemplateResponse(
        "static/quickstart.html",
        {
            "request": request,
            "current_role": current_role.value,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user_role": current_role.value,
            "user_api_key": user_api_key,
            "base_url": API_APP_BASE_URL or "https://127.0.0.1:8000", 
            "token_expiry_minutes": API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        }
    )

@app.get("/about", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")  # More permissive
async def about_page(request: Request):
    """About BoloDoc and the FBI Wanted API"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/about.html",
        {
            "request": request,
            "current_role": current_role.value,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
        }
    )

@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")  # More permissive
async def privacy_page(request: Request):
    """Privacy Policy"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/privacy.html",
        {
            "request": request,
            "current_role": current_role.value,
            "last_updated": "November 2025",
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
        }
    )

@app.get("/terms", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")  # More permissive
async def terms_page(request: Request):
    """Terms of Service"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/terms.html",
        {
            "request": request,
            "current_role": current_role.value,
            "last_updated": "November 2025",
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
        }
    )

@app.get("/contact", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("3000/minute")  # More permissive
async def contact_page(request: Request):
    """Contact Information"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/contact.html",
        {
            "request": request,
            "current_role": current_role.value,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
        }
    )

@app.get(
    "/plans",
    response_class=HTMLResponse,
    summary="Pricing Plans Page",
    description="Display pricing plans in HTML format",
    include_in_schema=False  # Hide from API docs
    )
@limiter.limit(rate_max)
async def pricing_plans_page(request: Request):
    """
    Pricing plans page - displays all subscription options.
    Public page - no authentication required.
    """
    # Get current user's subscription info if logged in
    current_plan = None
    current_cycle = None
    subscription_status = None
    
    logger.info(f"[plans] user_authenticated={request.state.user_authenticated}, user_id={request.state.user_id}, user_email={request.state.user_email}")
    
    if request.state.user_authenticated:
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Use user_id (always in token) as primary lookup
                    if request.state.user_id:
                        logger.info(f"[plans] Looking up user by user_id: {request.state.user_id}")
                        cur.execute(
                            "SELECT role, billing_cycle, subscription_status FROM tbl_users WHERE user_id = %s",
                            (request.state.user_id,)
                        )
                    elif request.state.user_email:
                        # Fallback to email if user_id not available
                        logger.info(f"[plans] Looking up user by email: {request.state.user_email}")
                        cur.execute(
                            "SELECT role, billing_cycle, subscription_status FROM tbl_users WHERE email = %s",
                            (request.state.user_email,)
                        )
                    else:
                        logger.warning("[plans] No user_id or email available for lookup")
                        cur = None
                    
                    if cur:
                        user = cur.fetchone()
                        logger.info(f"[plans] Database result: {user}")
                        if user:
                            # Determine plan: basic or premium
                            current_plan = "premium" if user['role'] == UserRole.PREMIUM.value else "basic"
                            current_cycle = user['billing_cycle']  # 'monthly', 'quarterly', 'annual', or None
                            subscription_status = user['subscription_status']  # 'active', 'cancelled', 'expired', etc.
                            logger.info(f"[plans] Determined: current_plan={current_plan}, current_cycle={current_cycle}, subscription_status={subscription_status}")
        except Exception as e:
            logger.error(f"Error getting user subscription: {str(e)}")
            # Continue without subscription info
    
    logger.info(f"[plans] Rendering with current_plan={current_plan}, current_cycle={current_cycle}, subscription_status={subscription_status}")
            # Continue without subscription info
    
    return templates.TemplateResponse(
        "static/plans.html",
        {
            "request": request,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "pricing": PRICING,
            "current_plan": current_plan,
            "current_cycle": current_cycle, 
            "subscription_status": subscription_status
        }
    )

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_string(value, field_name):
    """
    Validate string is not empty, not wildcard-only, not exceeding 100 characters,
    and doesn't contain potentially dangerous characters.
    Returns error message if invalid, None if valid.
    """
    if value == "":
        return f"{field_name} cannot be empty"
    
    if re.match(r'^\*+$', value):
        return f"{field_name} cannot be only wildcards"
    
    if len(value) > 100:
        return f"{field_name} cannot exceed 100 characters (current length: {len(value)})"
    
    if '\x00' in value:
        return f"{field_name} cannot contain null bytes"
    
    if re.search(r'\*{4,}', value):
        return f"{field_name} cannot contain more than 3 consecutive wildcards"
    
    # Check for control characters (except common whitespace)
    control_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
    if control_chars.search(value):
        return f"{field_name} cannot contain control characters"
    
    return None

def trim_recursive(data, path="", depth=0, max_depth=7):
    """
    Recursively trim strings in dict/list structures and validate.
    Returns (trimmed_data, error_message)
    """
    # Prevent deeply nested structures that could cause stack overflow
    if depth > max_depth:
        return None, f"Maximum nesting depth ({max_depth}) exceeded at {path}"
    
    if isinstance(data, dict):
        # Limit number of keys to prevent memory exhaustion
        if len(data) > 100:
            return None, f"Object at {path} cannot have more than 100 keys"
        
        result = {}
        for k, v in data.items():
            current_path = f"{path}.{k}" if path else k
            trimmed_value, error = trim_recursive(v, current_path, depth + 1, max_depth)
            if error:
                return None, error
            result[k] = trimmed_value
        return result, None
        
    elif isinstance(data, list):
        # Limit array length to prevent memory exhaustion
        if len(data) > 100:
            return None, f"Array at {path} cannot have more than 100 items"
        
        result = []
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            trimmed_item, error = trim_recursive(item, current_path, depth + 1, max_depth)
            if error:
                return None, error
            result.append(trimmed_item)
        return result, None
        
    elif isinstance(data, str):
        trimmed = data.strip()
        error = validate_string(trimmed, path)
        if error:
            return None, error
        return trimmed, None
        
    return data, None
