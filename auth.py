"""
Authentication and Authorization Module
Supports both session-based auth (for testing) and JWT auth (for production)
"""
from enum import Enum
from typing import Optional
from fastapi import HTTPException, Request, status

class UserRole(str, Enum):
    """User roles with hierarchical permissions"""
    PUBLIC = "public"
    BASIC = "basic"
    PREMIUM = "premium"
    ADMIN = "admin"

# Role hierarchy for permission checks
ROLE_HIERARCHY = {
    UserRole.PUBLIC: 0,
    UserRole.BASIC: 1,
    UserRole.PREMIUM: 2,
    UserRole.ADMIN: 3
}

# Session key for storing role (for session-based auth)
SESSION_ROLE_KEY = "user_role"

# ============================================================================
# SESSION-BASED AUTH (for testing/backward compatibility)
# ============================================================================

def get_current_role(request: Request) -> UserRole:
    """
    Get the current user role from session.
    Defaults to PUBLIC if no role is set.
    
    NOTE: This is for session-based auth only. For JWT auth, use jwt_auth.py
    """
    role_str = request.session.get(SESSION_ROLE_KEY, UserRole.PUBLIC.value)
    try:
        return UserRole(role_str)
    except ValueError:
        # Invalid role in session, default to PUBLIC
        return UserRole.PUBLIC

def set_user_role(request: Request, role: UserRole):
    """Set the user role in session (for testing only)"""
    request.session[SESSION_ROLE_KEY] = role.value

def require_role(required_role: UserRole):
    """
    Dependency that requires a minimum role level (session-based).
    Returns the current user role if authorized.
    Raises 403 if unauthorized.
    
    NOTE: This is for session-based auth only. For JWT auth, use jwt_auth.require_jwt_role()
    """
    async def role_checker(request: Request) -> UserRole:
        current_role = get_current_role(request)
        
        if not has_role(current_role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied."
            )
        
        return current_role
    
    return role_checker

# For testing: manually set role (will be replaced by proper auth later)
MANUAL_TEST_ROLE = UserRole.PUBLIC

# ============================================================================
# SHARED AUTHORIZATION LOGIC (works for both session and JWT)
# ============================================================================

def has_role(user_role: UserRole, required_role: UserRole) -> bool:
    """
    Check if user_role meets the required_role threshold.
    Uses hierarchical comparison (ADMIN > PREMIUM > BASIC > PUBLIC)
    
    This function works for both session-based and JWT-based auth.
    """
    return ROLE_HIERARCHY[user_role] >= ROLE_HIERARCHY[required_role]

def get_data_field_for_role(role: UserRole) -> str:
    """
    Determine which data field to return based on user role.
    
    - BASIC: full_data
    - PREMIUM: full_data_clean
    - ADMIN: full_data_clean
    - PUBLIC: full_data (for any public endpoints)
    
    This function works for both session-based and JWT-based auth.
    """
    if role in [UserRole.PREMIUM, UserRole.ADMIN]:
        return "full_data_clean"
    else:
        return "full_data"

def get_max_limit_for_role(role: UserRole, billing_cycle: Optional[str] = None) -> int:
    """
    Get maximum result limit based on user role and billing cycle.
    
    - PUBLIC: N/A (no search access)
    - BASIC: 25
    - PREMIUM (annual): 5000
    - PREMIUM (monthly or other): 25
    - ADMIN: 5000
    
    This function works for both session-based and JWT-based auth.
    """
    if role == UserRole.BASIC:
        return 25
    elif role == UserRole.ADMIN:
        return 5000
    elif role == UserRole.PREMIUM:
        # PREMIUM annual subscribers get 5000, others get 25
        return 5000 if billing_cycle == "annual" else 25
    else:
        return 0  # PUBLIC has no search access

def validate_limit_for_role(role: UserRole, requested_limit: int, billing_cycle: Optional[str] = None) -> int:
    """
    Validate and cap the requested limit based on user role and billing cycle.
    Returns the actual limit to use.
    
    - BASIC: Always returns 25 (silently capped, no error)
    - PREMIUM (annual): Returns requested limit up to 5000
    - PREMIUM (monthly/other): Always returns 25 (silently capped, no error)
    - ADMIN: Returns requested limit up to 5000
    - PUBLIC: Raises HTTPException (no search access)
    
    This function works for both session-based and JWT-based auth.
    """
    if role == UserRole.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Search access denied. Sign up with BoloDoc for access."
        )
    
    # BASIC users always get 25 results, silently capped
    if role == UserRole.BASIC:
        return 25
    
    # PREMIUM users: check billing cycle
    if role == UserRole.PREMIUM:
        # Annual subscribers can request up to 5000, others capped at 25
        if billing_cycle == "annual":
            return min(requested_limit, 5000)
        else:
            return 25
    
    # ADMIN: cap at max limit
    if role == UserRole.ADMIN:
        return min(requested_limit, 5000)
    
    # Fallback (should not reach here)
    return 25
