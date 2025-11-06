"""
EXAMPLE: Updated router_search.py to use JWT Authentication
This shows how to modify existing endpoints to use JWT tokens instead of sessions.

Key Changes:
1. Import jwt_auth instead of/in addition to auth
2. Replace Depends(require_role(UserRole.X)) with Depends(require_jwt_role(UserRole.X))
3. Access user_id and role from current_user dict instead of session
4. The rest of the logic remains the same

Below is a snippet showing the changes needed for the simple_search endpoint.
Apply the same pattern to all protected endpoints.
"""

# OLD IMPORTS (session-based):
# from auth import UserRole, require_role, get_data_field_for_role, validate_limit_for_role

# NEW IMPORTS (JWT-based):
from auth import UserRole, get_data_field_for_role, validate_limit_for_role
from jwt_auth import require_jwt_role

# ============================================================================
# EXAMPLE: Simple Search with JWT Authentication
# ============================================================================

@router.post(
    "/simple",
    summary="Simple Search with Wildcards",
    description="""
    Perform a simple search using wildcard patterns.
    
    **Authentication Required:** Include JWT token in Authorization header:
    `Authorization: Bearer {your_jwt_token}`
    
    Get your token from POST /auth/token with your API key.
    
    **Access:** BASIC role or higher
    **Result limits by role:**
    - BASIC: Maximum 25 results, returns full_data
    - PREMIUM: Maximum 5000 results, returns full_data_clean
    - ADMIN: Maximum 5000 results, returns full_data_clean
    
    [Rest of the description remains the same...]
    """,
    response_description="Query parameters, count, and array of JSONB records"
)
@limiter.limit(rate_max)
async def simple_search(
    request: Request, 
    search_request: SimpleSearchRequest,
    # OLD: current_role: UserRole = Depends(require_role(UserRole.BASIC))
    # NEW: Get full user context from JWT
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Execute a simple search with wildcard support.
    All string comparisons are case-insensitive.
    Requires BASIC role or higher via JWT authentication.
    """
    
    # Extract role and user_id from JWT claims
    current_role = current_user["role"]
    user_id = current_user["user_id"]  # Available for logging, rate limiting, etc.
    
    # The rest of the function remains exactly the same
    actual_limit = validate_limit_for_role(current_role, search_request.limit)
    data_field = get_data_field_for_role(current_role)
    
    # ... rest of the function unchanged ...
    
    # In the response, you can now include user_id if needed for auditing
    return {
        "query": search_request.model_dump(),
        "role": current_role.value,
        "user_id": user_id,  # Optional: include for audit trail
        "data_field": data_field,
        "resultcount": len(items),
        "items": items
    }

# ============================================================================
# EXAMPLE: Advanced Search with JWT Authentication
# ============================================================================

@router.post(
    "/advanced",
    summary="Advanced Search with Grouped Conditions",
    description="""
    Perform advanced searches with grouped conditions and multiple operators.
    
    **Authentication Required:** Include JWT token in Authorization header:
    `Authorization: Bearer {your_jwt_token}`
    
    [Rest of the description remains the same...]
    """,
    response_description="Query parameters, count, and array of JSONB records"
)
@limiter.limit(rate_max)
async def advanced_search(
    request: Request, 
    search_request: AdvancedSearchRequest,
    # OLD: current_role: UserRole = Depends(require_role(UserRole.PREMIUM))
    # NEW:
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
):
    """
    Execute an advanced search with grouped conditions.
    Requires PREMIUM role or higher via JWT authentication.
    """
    
    # Extract role and user_id from JWT claims
    current_role = current_user["role"]
    user_id = current_user["user_id"]
    
    # The rest of the function remains exactly the same
    actual_limit = validate_limit_for_role(current_role, search_request.limit)
    data_field = get_data_field_for_role(current_role)
    
    # ... rest of the function unchanged ...

# ============================================================================
# EXAMPLE: Public Endpoint (no authentication required)
# ============================================================================

@router.get(
    "/",
    summary="API Information",
    description="Get information about this API and available endpoints"
)
async def root():
    """Return API information and usage guide - accessible to all roles"""
    # No authentication dependency needed - this is public
    return {
        "name": "Advanced Search API",
        "version": "1.0.0",
        "authentication": {
            "type": "JWT Bearer Token",
            "get_token": "POST /auth/token with your API key",
            "usage": "Include 'Authorization: Bearer {token}' header in requests"
        },
        "endpoints": {
            "/simple": "Simple wildcard-based search (BASIC role or higher)",
            "/advanced": "Advanced search with grouped conditions (PREMIUM role or higher)",
        },
        # ... rest unchanged ...
    }

# ============================================================================
# MIGRATION NOTES
# ============================================================================

"""
To migrate all endpoints to JWT authentication:

1. Update imports:
   from auth import UserRole, get_data_field_for_role, validate_limit_for_role
   from jwt_auth import require_jwt_role

2. For each protected endpoint, change:
   OLD: current_role: UserRole = Depends(require_role(UserRole.X))
   NEW: current_user: dict = Depends(require_jwt_role(UserRole.X))

3. In the endpoint function, extract what you need:
   current_role = current_user["role"]
   user_id = current_user["user_id"]  # Optional, for logging/auditing

4. Update endpoint descriptions to mention JWT authentication

5. The authorization logic (has_role, get_data_field_for_role, etc.) 
   remains unchanged because it works with UserRole enum

6. For endpoints that should work with or without auth, use:
   from jwt_auth import get_optional_user
   current_user: Optional[dict] = Depends(get_optional_user)
   
   Then check: if current_user is not None: ...

7. Rate limiting can now be per-user instead of per-IP:
   Use user_id from JWT for more accurate rate limiting
"""
