import httpx, json, re

# FastAPI setup
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
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

templates = Jinja2Templates(directory="templates")

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Initialize rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

app = FastAPI(title = "Bolo API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(router_etl.router) 
app.include_router(router_search.router)

# Custom middleware class for role and trimming
from starlette.middleware.base import BaseHTTPMiddleware

class RoleAndTrimMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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

# Add session middleware LAST (executes FIRST due to reverse order)
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-change-this-in-production-min-32-chars",
    session_cookie="bolo_session",
    max_age=3600,
    same_site="lax",
    https_only=False
)

@app.get("/", response_class=HTMLResponse)
@limiter.limit(rate_max)
async def root(request: Request):
    """
    Homepage - accessible by all roles (PUBLIC and above)
    Shows current user role for testing purposes
    """
    # Public endpoint - no role check needed
    current_role = get_current_role(request)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(FBI_API_URL, params={"page": 1})
            response.raise_for_status()
            data = response.json()
            total = data.get("total", "unknown")
            items = data.get("items", [])[:5]
        except Exception:
            total = "unavailable"
            items = []

    return templates.TemplateResponse(
        "index.htm",
        {
            "request": request,
            "total": total,
            "items": items,
            "current_role": current_role.value  # Pass role to template for display
        }
    )

@app.get("/health", include_in_schema=False)
@limiter.limit(rate_max)
async def health_check(request: Request):
    """Health check endpoint - accessible by all roles"""
    current_role = get_current_role(request)
    return {
        "status": "healthy",
        "role": current_role.value
    }

@app.get("/role", include_in_schema=True)
@limiter.limit(rate_max)
async def get_role(request: Request):
    """Get current user role - for testing purposes"""
    current_role = get_current_role(request)
    return {
        "current_role": current_role.value,
        "role_level": ROLE_HIERARCHY[current_role],
        "test_mode": True,
        "note": "Change MANUAL_TEST_ROLE in auth.py to test different roles"
    }

@app.post("/role/set", include_in_schema=True)
@limiter.limit(rate_max)
async def set_role(request: Request, role: UserRole):
    """
    Manually set user role - for testing purposes only
    In production, this would be replaced by proper authentication
    """
    set_user_role(request, role)
    return {
        "message": f"Role set to {role.value}",
        "current_role": role.value
    }


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