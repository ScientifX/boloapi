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

import router_etl
import router_search
import router_auth 
# import router_billing
from auth_middleware import TemplateAuthMiddleware

templates = Jinja2Templates(directory="templates")

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Initialize rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

app = FastAPI(
    title="Bolo API",
    description="Bolo API",
    version="1.0.0", 
    swagger_ui_parameters={"defaultModelsExpandDepth": -1} # Hides the schemas in /docs 
    )

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
# app.include_router(router_billing.router)
app.include_router(router_etl.router) 
app.include_router(router_search.router)
app.include_router(router_auth.router) 

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

@app.get("/role", include_in_schema=False, tags=["Testing"])
@limiter.limit(rate_max)
async def get_role(request: Request):
    """Get current user role - for testing purposes (session-based)"""
    current_role = get_current_role(request)
    return {
        "current_role": current_role.value,
        "role_level": ROLE_HIERARCHY[current_role],
        "test_mode": True,
        "note": "For JWT authentication, use /v1/auth/token endpoint",
        "migration_note": "This endpoint uses session-based auth and will be deprecated"
    }

@app.post("/role/set", include_in_schema=False, tags=["Testing"])
@limiter.limit(rate_max)
async def set_role(request: Request, role: UserRole):
    """
    Manually set user role - for testing purposes only (session-based)
    In production, use JWT authentication via /v1/auth/token
    """
    set_user_role(request, role)
    return {
        "message": f"Role set to {role.value}",
        "current_role": role.value,
        "note": "This is session-based auth for testing. Use JWT auth in production."
    }

# ============================================================================
# STATIC CONTENT PAGES
# ============================================================================

@app.get("/about", response_class=HTMLResponse, include_in_schema=False, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
async def about_page(request: Request):
    """About Scientifics.io and the FBI Wanted API"""
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
            "support_email": "support@scientifics.io", 
            "business_email": "contact@scientifics.io",
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
        }
    )


# Validation functions (unchanged)
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
