"""
EXAMPLE: Updated app.py to include JWT authentication

Key Changes:
1. Import router_auth
2. Include router_auth in the app
3. Update role middleware to work with JWT (optional - can be removed if using JWT exclusively)
4. Keep session middleware for backward compatibility during migration

This example shows how to integrate the auth router into your existing app.
"""

import httpx, json, re

# FastAPI setup
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

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
from config import APP_GLOBALS, PRICING
import router_etl
import router_search
import router_auth
import router_billing
from auth_middleware import TemplateAuthMiddleware
from docs_config import (
    get_role_filtered_openapi,
    get_viewer_role_from_request,
    register_visibility_override,
)

templates = Jinja2Templates(directory="templates")

templates.env.globals.update(APP_GLOBALS)

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Initialize rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# ============================================================================
# FASTAPI APP WITH CUSTOM DOCS
# ============================================================================

app = FastAPI(
    title="Bolo API",
    description="Bolo API - FBI Wanted Persons Data",
    version="1.0.0",
    # Disable default docs - we'll serve custom role-filtered versions
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(router_billing.router)
app.include_router(router_etl.router) 
app.include_router(router_search.router)
app.include_router(router_auth.router) 


# ============================================================================
# CUSTOM ROLE-FILTERED DOCUMENTATION ENDPOINTS
# ============================================================================

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema(request: Request):
    """
    Serve OpenAPI schema filtered by the viewer's role.
    
    Visibility:
    - Not logged in: PUBLIC + BASIC endpoints
    - BASIC: PUBLIC + BASIC + PREMIUM endpoints
    - PREMIUM: PUBLIC + BASIC + PREMIUM endpoints
    - ADMIN: All endpoints
    """
    filtered_schema = get_role_filtered_openapi(app, request)
    return JSONResponse(content=filtered_schema)


@app.get("/docs", include_in_schema=False)
async def get_docs(request: Request):
    """
    Serve Swagger UI with role-filtered endpoints.
    Shows different endpoints based on viewer's authentication level.
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
    
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"API Docs - BoloDoc",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1}
    )


@app.get("/redoc", include_in_schema=False)
async def get_redoc(request: Request):
    """
    Serve ReDoc with role-filtered endpoints.
    """
    viewer_role = get_viewer_role_from_request(request)
    
    role_labels = {
        UserRole.PUBLIC: "Guest",
        UserRole.BASIC: "Basic",
        UserRole.PREMIUM: "Premium",
        UserRole.ADMIN: "Admin",
    }
    role_label = role_labels.get(viewer_role, "Guest")
    
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=f"Bolo API - {role_label} View",
    )


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
async def list_routes(request: Request):
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
            # Check for slowapi limit decorator info
            current = endpoint
            while current:
                if hasattr(current, '_rate_limit'):
                    rate_limits.append(current._rate_limit)
                if hasattr(current, '__wrapped__'):
                    current = current.__wrapped__
                else:
                    break
        
        # Also check the endpoint's __self__ for limiter decorators
        # SlowAPI stores limits differently - check for _limits attribute
        if hasattr(endpoint, '__self__') and hasattr(endpoint.__self__, '_limits'):
            rate_limits.extend(endpoint.__self__._limits)
        
        # Default rate limit if none found on endpoint
        rate_limit_display = ', '.join(rate_limits) if rate_limits else rate_max
        
        routes_info.append({
            'router': router_name,
            'method': methods,
            'path': path,
            'endpoint': endpoint_name,
            'auth_required': auth_required,
            'rate_limit': rate_limit_display
        })
    
    # Sort routes by router, then by path
    routes_info.sort(key=lambda x: (x['router'], x['path']))
    
    # Generate HTML table
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Routes</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                margin: 40px;
                background: #f5f5f5;
            }
            h1 { 
                color: #333;
                border-bottom: 2px solid #007bff;
                padding-bottom: 10px;
            }
            table { 
                border-collapse: collapse; 
                width: 100%; 
                background: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            th, td { 
                border: 1px solid #ddd; 
                padding: 12px 15px; 
                text-align: left; 
            }
            th { 
                background: #007bff; 
                color: white;
                font-weight: 600;
            }
            tr:nth-child(even) { background: #f8f9fa; }
            tr:hover { background: #e9ecef; }
            .method { 
                font-weight: bold; 
                font-family: monospace;
            }
            .method.GET { color: #28a745; }
            .method.POST { color: #007bff; }
            .method.PUT { color: #ffc107; }
            .method.DELETE { color: #dc3545; }
            .path { 
                font-family: monospace; 
                color: #6c757d;
            }
            .auth-yes { color: #dc3545; font-weight: 500; }
            .auth-no { color: #28a745; }
            .router-tag {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.85em;
                font-weight: 500;
            }
            .router-auth { background: #e7f1ff; color: #0056b3; }
            .router-search { background: #d4edda; color: #155724; }
            .router-etl { background: #fff3cd; color: #856404; }
            .router-billing { background: #f8d7da; color: #721c24; }
            .router-root { background: #e2e3e5; color: #383d41; }
        </style>
    </head>
    <body>
        <h1>API Routes</h1>
        <table>
            <thead>
                <tr>
                    <th>Router</th>
                    <th>Method</th>
                    <th>Path</th>
                    <th>Endpoint</th>
                    <th>Auth Required</th>
                    <th>Rate Limit</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for route in routes_info:
        # Determine method class for styling
        method_class = route['method'].split(',')[0].strip()
        
        # Determine auth class
        auth_class = 'auth-yes' if route['auth_required'].startswith('Yes') else 'auth-no'
        
        # Determine router class
        router_class = 'router-root'
        if 'auth' in route['router']:
            router_class = 'router-auth'
        elif 'search' in route['router']:
            router_class = 'router-search'
        elif 'etl' in route['router']:
            router_class = 'router-etl'
        elif 'billing' in route['router']:
            router_class = 'router-billing'
        
        html += f"""
                <tr>
                    <td><span class="router-tag {router_class}">{route['router']}</span></td>
                    <td class="method {method_class}">{route['method']}</td>
                    <td class="path">{route['path']}</td>
                    <td>{route['endpoint']}</td>
                    <td class="{auth_class}">{route['auth_required']}</td>
                    <td>{route['rate_limit']}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit(rate_max)
async def root(request: Request):
    """
    Homepage - accessible by all roles (PUBLIC and above)
    Shows live FBI data statistics, features, pricing, and use cases
    """
    # Public endpoint - no authentication required
    current_role = get_current_role(request)  # For session-based testing
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(FBI_API_URL, params={"page": 1})
            response.raise_for_status()
            data = response.json()
            total = data.get("total", "N/A")
        except Exception:
            total = "5,200+"  # Fallback if FBI API is unavailable
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total": total,
            "current_role": current_role.value,  # For testing display
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
        }
    )

# ============================================================================
# STATIC CONTENT PAGES
# ============================================================================

@app.get("/about", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
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
        }
    )

@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
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
        }
    )

@app.get("/terms", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
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
        }
    )

@app.get("/contact", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
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
    
    if request.state.user_authenticated and request.state.user_email:
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT role, billing_cycle FROM tbl_users WHERE email = %s",
                        (request.state.user_email,)
                    )
                    user = cur.fetchone()
                    if user:
                        # Determine plan: basic or premium
                        current_plan = "premium" if user['role'] == UserRole.PREMIUM.value else "basic"
                        current_cycle = user['billing_cycle']  # 'monthly', 'quarterly', 'annual', or None
        except Exception as e:
            logger.error(f"Error getting user subscription: {str(e)}")
            # Continue without subscription info
    
    return templates.TemplateResponse(
        "static/plans.html",
        {
            "request": request,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "pricing": PRICING,
            "current_plan": current_plan,
            "current_cycle": current_cycle
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
