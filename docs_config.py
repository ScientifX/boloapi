"""
Role-Based OpenAPI Documentation Visibility

Controls which endpoints are visible in /docs based on user role.
Supports per-endpoint exceptions for custom visibility rules.

Visibility Matrix:
- Not logged in: PUBLIC + BASIC endpoints
- BASIC: PUBLIC + BASIC + PREMIUM endpoints  
- PREMIUM: PUBLIC + BASIC + PREMIUM endpoints (same as BASIC)
- ADMIN: All endpoints (PUBLIC + BASIC + PREMIUM + ADMIN)

Exception system:
- docs_visible_to: Force endpoint visible to a lower role tier
- docs_hidden: Hide from everyone including ADMIN
"""

from typing import Optional, Callable, Dict, Any, List
from functools import wraps
from copy import deepcopy

from fastapi import Request
from fastapi.openapi.utils import get_openapi

from auth import UserRole, ROLE_HIERARCHY
from jwt_utils import decode_access_token, JWTError


# ============================================================================
# VISIBILITY CONFIGURATION
# ============================================================================

# Maps viewer role to the maximum endpoint role they can see in docs
# Each role sees "one level up" except PREMIUM (same as BASIC) and ADMIN (sees all)
DOCS_VISIBILITY_MAP = {
    UserRole.PUBLIC: UserRole.BASIC,      # Not logged in sees up to BASIC
    UserRole.BASIC: UserRole.PREMIUM,     # BASIC sees up to PREMIUM
    UserRole.PREMIUM: UserRole.PREMIUM,   # PREMIUM sees up to PREMIUM (no ADMIN)
    UserRole.ADMIN: UserRole.ADMIN,       # ADMIN sees everything
}

# Storage for endpoint-level visibility overrides
# Key: (method, path), Value: {"visible_to": UserRole, "hidden": bool}
ENDPOINT_VISIBILITY_OVERRIDES: Dict[tuple, Dict[str, Any]] = {}


# ============================================================================
# DECORATOR FOR ENDPOINT VISIBILITY EXCEPTIONS
# ============================================================================

def docs_visibility(
    visible_to: Optional[UserRole] = None,
    hidden: bool = False
) -> Callable:
    """
    Decorator to override default docs visibility for an endpoint.
    
    Args:
        visible_to: Force endpoint visible to this role and above.
                   Use to make an endpoint visible to a lower tier than 
                   its auth requirement would suggest.
        hidden: If True, hide from docs entirely (even ADMIN).
                Use for internal endpoints that shouldn't be documented.
    
    Examples:
        # Make an ADMIN endpoint visible to everyone in docs
        @docs_visibility(visible_to=UserRole.PUBLIC)
        @router.get("/admin/status", dependencies=[Depends(require_jwt_role(UserRole.ADMIN))])
        async def admin_status():
            ...
        
        # Hide an endpoint from docs completely
        @docs_visibility(hidden=True)
        @router.get("/internal/metrics")
        async def internal_metrics():
            ...
    
    Note: Apply this decorator BEFORE (above) the route decorator.
    """
    def decorator(func: Callable) -> Callable:
        # Store visibility info on the function for later retrieval
        func._docs_visible_to = visible_to
        func._docs_hidden = hidden
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        # Copy the visibility attributes to wrapper
        wrapper._docs_visible_to = visible_to
        wrapper._docs_hidden = hidden
        
        return wrapper
    
    return decorator


def register_visibility_override(
    method: str,
    path: str,
    visible_to: Optional[UserRole] = None,
    hidden: bool = False
):
    """
    Programmatically register a visibility override for an endpoint.
    Use this when you can't use the decorator (e.g., for existing endpoints).
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Full path including prefix (e.g., "/v1/search/simple")
        visible_to: Force visibility to this role
        hidden: Hide from docs entirely
    """
    key = (method.upper(), path)
    ENDPOINT_VISIBILITY_OVERRIDES[key] = {
        "visible_to": visible_to,
        "hidden": hidden
    }


# ============================================================================
# ROLE EXTRACTION FROM REQUEST
# ============================================================================

def get_viewer_role_from_request(request: Request) -> UserRole:
    """
    Extract the viewer's role from JWT token (cookie or header).
    Returns PUBLIC if not authenticated or token invalid.
    """
    # Check cookie first (web users)
    token = request.cookies.get("auth_token")
    
    # Then check Authorization header (API users)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        return UserRole.PUBLIC
    
    try:
        payload = decode_access_token(token)
        role_str = payload.get("role")
        if role_str:
            return UserRole(role_str)
    except (JWTError, ValueError):
        pass
    
    return UserRole.PUBLIC


# ============================================================================
# ENDPOINT ROLE DETECTION
# ============================================================================

def get_endpoint_required_role(route) -> Optional[UserRole]:
    """
    Determine the required role for an endpoint by inspecting its dependencies.
    Returns None if no role requirement found (effectively PUBLIC).
    """
    if not hasattr(route, 'dependant') or not route.dependant:
        return None
    
    for dep in route.dependant.dependencies:
        dep_call = dep.call
        
        # Check for require_jwt_role dependency
        if hasattr(dep_call, '__name__') and dep_call.__name__ == 'role_checker':
            # Extract role from closure
            if hasattr(dep_call, '__closure__') and dep_call.__closure__:
                for cell in dep_call.__closure__:
                    try:
                        cell_contents = cell.cell_contents
                        if isinstance(cell_contents, UserRole):
                            return cell_contents
                    except ValueError:
                        # Cell is empty
                        continue
    
    return None


def get_endpoint_visibility_config(route) -> Dict[str, Any]:
    """
    Get visibility configuration for an endpoint.
    Checks decorator attributes first, then registered overrides.
    
    Returns:
        {
            "visible_to": UserRole or None (use default),
            "hidden": bool,
            "required_role": UserRole or None
        }
    """
    method = list(route.methods - {'HEAD', 'OPTIONS'})[0] if route.methods else 'GET'
    path = route.path
    endpoint = route.endpoint
    
    config = {
        "visible_to": None,
        "hidden": False,
        "required_role": get_endpoint_required_role(route)
    }
    
    # Check decorator attributes on endpoint function
    if endpoint:
        # Check the endpoint itself
        if hasattr(endpoint, '_docs_hidden'):
            config["hidden"] = endpoint._docs_hidden
        if hasattr(endpoint, '_docs_visible_to'):
            config["visible_to"] = endpoint._docs_visible_to
        
        # Also check wrapped function if exists
        if hasattr(endpoint, '__wrapped__'):
            wrapped = endpoint.__wrapped__
            if hasattr(wrapped, '_docs_hidden'):
                config["hidden"] = wrapped._docs_hidden
            if hasattr(wrapped, '_docs_visible_to'):
                config["visible_to"] = wrapped._docs_visible_to
    
    # Check registered overrides (these take precedence)
    key = (method, path)
    if key in ENDPOINT_VISIBILITY_OVERRIDES:
        override = ENDPOINT_VISIBILITY_OVERRIDES[key]
        if override.get("hidden") is not None:
            config["hidden"] = override["hidden"]
        if override.get("visible_to") is not None:
            config["visible_to"] = override["visible_to"]
    
    return config


# ============================================================================
# VISIBILITY DETERMINATION
# ============================================================================

def can_viewer_see_endpoint(viewer_role: UserRole, route) -> bool:
    """
    Determine if a viewer with given role can see an endpoint in docs.
    
    Logic:
    1. If endpoint has include_in_schema=False, hide it (unchanged behavior)
    2. If endpoint has docs_hidden=True, hide it from everyone
    3. If endpoint has docs_visible_to override, use that
    4. Otherwise, use the endpoint's required_role and visibility matrix
    """
    # Check include_in_schema (FastAPI's built-in hiding)
    if hasattr(route, 'include_in_schema') and not route.include_in_schema:
        return False
    
    config = get_endpoint_visibility_config(route)
    
    # Hidden from everyone
    if config["hidden"]:
        return False
    
    # Determine the minimum role needed to SEE this endpoint in docs
    if config["visible_to"] is not None:
        # Explicit override
        min_role_to_see = config["visible_to"]
    elif config["required_role"] is not None:
        # Default: endpoint's auth requirement
        min_role_to_see = config["required_role"]
    else:
        # No auth requirement = PUBLIC endpoint
        min_role_to_see = UserRole.PUBLIC
    
    # Get the maximum role this viewer can see
    max_visible_role = DOCS_VISIBILITY_MAP.get(viewer_role, UserRole.BASIC)
    
    # Viewer can see endpoint if its required role <= viewer's max visible role
    return ROLE_HIERARCHY[min_role_to_see] <= ROLE_HIERARCHY[max_visible_role]


# ============================================================================
# OPENAPI SCHEMA FILTERING
# ============================================================================

def filter_openapi_schema(app, viewer_role: UserRole) -> Dict[str, Any]:
    """
    Generate an OpenAPI schema filtered for the viewer's role.
    Only includes endpoints the viewer is allowed to see.
    """
    # Get the full schema
    full_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Deep copy to avoid modifying the original
    filtered_schema = deepcopy(full_schema)
    
    # Build a map of path+method to route for visibility checking
    route_map = {}
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods - {'HEAD', 'OPTIONS'}:
                route_map[(route.path, method.lower())] = route
    
    # Filter paths
    paths_to_remove = []
    for path, methods in filtered_schema.get("paths", {}).items():
        methods_to_remove = []
        
        for method in methods:
            if method in ('get', 'post', 'put', 'patch', 'delete'):
                route = route_map.get((path, method))
                if route and not can_viewer_see_endpoint(viewer_role, route):
                    methods_to_remove.append(method)
        
        # Remove hidden methods
        for method in methods_to_remove:
            del filtered_schema["paths"][path][method]
        
        # If no methods left, mark path for removal
        remaining_methods = [m for m in filtered_schema["paths"][path] 
                          if m in ('get', 'post', 'put', 'patch', 'delete')]
        if not remaining_methods:
            paths_to_remove.append(path)
    
    # Remove empty paths
    for path in paths_to_remove:
        del filtered_schema["paths"][path]
    
    # Clean up unused schemas/components (optional but keeps schema tidy)
    # This is complex to do properly, so we'll leave components as-is
    
    return filtered_schema


def get_role_filtered_openapi(app, request: Request) -> Dict[str, Any]:
    """
    Main entry point: Get OpenAPI schema filtered for the requesting user's role.
    """
    viewer_role = get_viewer_role_from_request(request)
    return filter_openapi_schema(app, viewer_role)
