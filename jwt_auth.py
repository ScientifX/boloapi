"""
JWT Authentication Dependencies
Provides FastAPI dependencies for protecting endpoints with JWT tokens
Supports both Authorization header (API) and httpOnly cookie (web pages)

Updated to include billing_cycle from database for subscription-based access control.
"""
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import UserRole, has_role
from jwt_utils import decode_access_token, JWTError
from config import DB_CONFIG

# HTTP Bearer token scheme
security = HTTPBearer(
    scheme_name="JWT Bearer Token",
    description="Enter your JWT access token (get from /v1/auth/token)",
    auto_error=False  # Don't auto-error, we'll handle it ourselves
)


def get_user_subscription_info(user_id: str) -> dict:
    """
    Fetch billing_cycle and subscription_status from database.
    Returns dict with billing_cycle and subscription_status.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT billing_cycle, subscription_status
                FROM tbl_users
                WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
        conn.close()
        
        if row:
            return {
                "billing_cycle": row.get("billing_cycle"),
                "subscription_status": row.get("subscription_status")
            }
        return {"billing_cycle": None, "subscription_status": None}
        
    except Exception:
        return {"billing_cycle": None, "subscription_status": None}


def get_token_from_cookie_or_header(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Extract JWT token from either:
    1. httpOnly cookie (for web pages) - checked first
    2. Authorization header (for API calls)
    
    Returns token string or None if not found
    """
    # First, check for httpOnly cookie (web page authentication)
    token = request.cookies.get("auth_token")
    if token:
        return token
    
    # Second, check Authorization header (API authentication)
    if credentials:
        return credentials.credentials
    
    return None


def get_current_user_from_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Extract and validate JWT token from either httpOnly cookie or Authorization header.
    Returns user claims (user_id, role, billing_cycle, subscription_status) from valid token.
    
    Checks in order:
    1. httpOnly cookie named 'auth_token' (for web pages)
    2. Authorization: Bearer header (for API calls)
    
    Also fetches billing_cycle from database for subscription-based access control.
    
    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    # Get token from cookie or header
    token = get_token_from_cookie_or_header(request, credentials)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token. Please log in or include 'Authorization: Bearer {token}' header.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        payload = decode_access_token(token)
        
        # Extract user_id and role from token claims
        user_id = payload.get("sub")
        role_str = payload.get("role")
        
        if not user_id or not role_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate role
        try:
            role = UserRole(role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid role in token: {role_str}",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Fetch subscription info from database
        # This ensures we always have current billing_cycle even if it changed after token was issued
        subscription_info = get_user_subscription_info(user_id)
        
        return {
            "user_id": user_id,
            "role": role,
            "billing_cycle": subscription_info.get("billing_cycle"),
            "subscription_status": subscription_info.get("subscription_status")
        }
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


def get_current_user_role(
    current_user: dict = Depends(get_current_user_from_token)
) -> UserRole:
    """
    Get the current user's role from validated token.
    Use this as a dependency when you just need the role.
    """
    return current_user["role"]


def require_jwt_role(required_role: UserRole):
    """
    Create a dependency that requires a minimum JWT role level.
    This replaces the session-based require_role for JWT authentication.
    
    Usage:
        @router.get("/protected", dependencies=[Depends(require_jwt_role(UserRole.BASIC))])
        async def protected_endpoint():
            ...
    
    Or to access the user info:
        @router.get("/protected")
        async def protected_endpoint(current_user: dict = Depends(require_jwt_role(UserRole.BASIC))):
            user_id = current_user["user_id"]
            role = current_user["role"]
            billing_cycle = current_user["billing_cycle"]
            ...
    """
    def role_checker(current_user: dict = Depends(get_current_user_from_token)) -> dict:
        user_role = current_user["role"]
        
        if not has_role(user_role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied."
            )
        
        return current_user
    
    return role_checker


def require_annual_subscription(current_user: dict = Depends(get_current_user_from_token)) -> dict:
    """
    Dependency that requires an annual subscription or ADMIN role.
    Use this for features exclusive to annual subscribers.
    
    Usage:
        @router.get("/premium-annual-feature")
        async def annual_feature(current_user: dict = Depends(require_annual_subscription)):
            ...
    """
    role = current_user.get("role")
    billing_cycle = current_user.get("billing_cycle")
    subscription_status = current_user.get("subscription_status")
    
    # ADMIN always has access
    if role == UserRole.ADMIN:
        return current_user
    
    # Must have PREMIUM role
    if not has_role(role, UserRole.PREMIUM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a PREMIUM subscription."
        )
    
    # Must have active annual subscription
    if billing_cycle != "annual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature is exclusive to annual subscribers. "
                   f"Your billing cycle is: {billing_cycle or 'none'}. "
                   f"Upgrade to an annual plan to access this feature."
        )
    
    if subscription_status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your subscription status is: {subscription_status}. "
                   f"An active subscription is required for this feature."
        )
    
    return current_user


# Optional: Dependency for endpoints that work with or without authentication
def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Optional authentication - returns user info if token provided and valid,
    None otherwise. Useful for endpoints that provide different features
    based on authentication status.
    
    Checks both httpOnly cookie and Authorization header.
    """
    token = get_token_from_cookie_or_header(request, credentials)
    
    if not token:
        return None
    
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        role_str = payload.get("role")
        
        if not user_id or not role_str:
            return None
        
        try:
            role = UserRole(role_str)
        except ValueError:
            return None
        
        # Fetch subscription info
        subscription_info = get_user_subscription_info(user_id)
        
        return {
            "user_id": user_id,
            "role": role,
            "billing_cycle": subscription_info.get("billing_cycle"),
            "subscription_status": subscription_info.get("subscription_status")
        }
    except (JWTError, Exception):
        return None
