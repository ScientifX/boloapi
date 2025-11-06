from enum import Enum
from typing import Optional
from fastapi import HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse

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

# Session key for storing role
SESSION_ROLE_KEY = "user_role"

def get_current_role(request: Request) -> UserRole:
    """
    Get the current user role from session.
    Defaults to PUBLIC if no role is set.
    """
    role_str = request.session.get(SESSION_ROLE_KEY, UserRole.PUBLIC.value)
    try:
        return UserRole(role_str)
    except ValueError:
        # Invalid role in session, default to PUBLIC
        return UserRole.PUBLIC

def set_user_role(request: Request, role: UserRole):
    """Set the user role in session"""
    request.session[SESSION_ROLE_KEY] = role.value

def has_role(user_role: UserRole, required_role: UserRole) -> bool:
    """
    Check if user_role meets the required_role threshold.
    Uses hierarchical comparison (ADMIN > PREMIUM > BASIC > PUBLIC)
    """
    return ROLE_HIERARCHY[user_role] >= ROLE_HIERARCHY[required_role]

def require_role(required_role: UserRole):
    """
    Dependency that requires a minimum role level.
    Returns the current user role if authorized.
    Raises 403 if unauthorized.
    """
    async def role_checker(request: Request) -> UserRole:
        current_role = get_current_role(request)
        
        if not has_role(current_role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {required_role.value} or higher. Your role: {current_role.value}"
            )
        
        return current_role
    
    return role_checker

def get_data_field_for_role(role: UserRole) -> str:
    """
    Determine which data field to return based on user role.
    
    - BASIC: full_data
    - PREMIUM: full_data_clean
    - ADMIN: full_data_clean
    - PUBLIC: full_data (for any public endpoints)
    """
    if role in [UserRole.PREMIUM, UserRole.ADMIN]:
        return "full_data_clean"
    else:
        return "full_data"

def get_max_limit_for_role(role: UserRole) -> int:
    """
    Get maximum result limit based on user role.
    
    - PUBLIC: N/A (no search access)
    - BASIC: 25
    - PREMIUM: 5000
    - ADMIN: 5000
    """
    if role == UserRole.BASIC:
        return 25
    elif role in [UserRole.PREMIUM, UserRole.ADMIN]:
        return 5000
    else:
        return 0  # PUBLIC has no search access

def validate_limit_for_role(role: UserRole, requested_limit: int) -> int:
    """
    Validate and cap the requested limit based on user role.
    Returns the actual limit to use.
    Raises HTTPException if requested limit exceeds role permissions.
    """
    max_limit = get_max_limit_for_role(role)
    
    if role == UserRole.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Search access denied. Required role: basic or higher."
        )
    
    if requested_limit > max_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requested limit ({requested_limit}) exceeds maximum for {role.value} role ({max_limit}). Upgrade to premium for higher limits."
        )
    
    return requested_limit

# For testing: manually set role (will be replaced by proper auth later)
MANUAL_TEST_ROLE = UserRole.PUBLIC 