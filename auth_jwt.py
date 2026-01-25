"""
JWT Authentication Dependencies
Provides FastAPI dependencies for protecting endpoints with JWT tokens
Supports both Authorization header (API) and httpOnly cookie (web pages)
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import UserRole, has_role
from utils_jwt import decode_access_token, JWTError
from config import DB_CONFIG

# HTTP Bearer token scheme
security = HTTPBearer(
    scheme_name="JWT Bearer Token",
    description="Enter your JWT access token (get from /v1/auth/token)",
    auto_error=False  # Don't auto-error, we'll handle it ourselves
)

@contextmanager
def get_db_connection():
    """Database connection context manager"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

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
    Returns user claims (user_id, role) from valid token.
    
    Checks in order:
    1. httpOnly cookie named 'auth_token' (for web pages)
    2. Authorization: Bearer header (for API calls)
    
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
        email = payload.get("email")
        codename = payload.get("codename")
        
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
        
        # CRITICAL: Check database to ensure user is still active
        # This allows immediate revocation when admin disables a user
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT is_active FROM base.tbl_users WHERE user_id = %s",
                    (user_id,)
                )
                user_record = cur.fetchone()
                
                if not user_record:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                if not user_record['is_active']:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Account disabled. Contact support for assistance.",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
        
        return {
            "user_id": user_id,
            "role": role,
            "email": email,
            "codename": codename
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
        email = payload.get("email")
        codename = payload.get("codename")
        
        if not user_id or not role_str:
            return None
        
        try:
            role = UserRole(role_str)
        except ValueError:
            return None
        
        # Check database to ensure user is still active
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT is_active FROM base.tbl_users WHERE user_id = %s",
                    (user_id,)
                )
                user_record = cur.fetchone()
                
                if not user_record or not user_record['is_active']:
                    return None
        
        return {
            "user_id": user_id,
            "role": role,
            "email": email,
            "codename": codename
        }
    except (JWTError, Exception):
        return None


def get_user_or_none(request: Request) -> Optional[dict]:
    """
    Get current user from JWT token without raising exceptions.
    Returns user dict if authenticated, None otherwise.
    
    Use this for browser-facing pages that should redirect to login
    instead of returning JSON errors.
    
    Usage:
        @router.get("/profile")
        async def profile_page(request: Request):
            current_user = get_user_or_none(request)
            if not current_user:
                return RedirectResponse(url="/v1/auth/login", status_code=303)
            # ... rest of endpoint
    """
    # Check for httpOnly cookie first (web authentication)
    token = request.cookies.get("auth_token")
    
    # Fall back to Authorization header
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
    
    if not token:
        return None
    
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        role_str = payload.get("role")
        email = payload.get("email")
        codename = payload.get("codename")
        
        if not user_id or not role_str:
            return None
        
        try:
            role = UserRole(role_str)
        except ValueError:
            return None
        
        # Check database to ensure user is still active
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT is_active FROM base.tbl_users WHERE user_id = %s",
                    (user_id,)
                )
                user_record = cur.fetchone()
                
                if not user_record or not user_record['is_active']:
                    return None
        
        return {
            "user_id": user_id,
            "role": role,
            "email": email,
            "codename": codename
        }
    except (JWTError, Exception):
        return None


def require_browser_auth(required_role: UserRole = UserRole.BASIC):
    """
    Create a dependency for browser-facing pages that returns None 
    instead of raising HTTPException when auth fails.
    
    The endpoint must handle the None case by redirecting to login.
    
    Usage:
        @router.get("/profile")
        async def profile_page(
            request: Request, 
            current_user: Optional[dict] = Depends(require_browser_auth())
        ):
            if not current_user:
                return RedirectResponse(url="/v1/auth/login", status_code=303)
            # ... rest of endpoint
    """
    def auth_checker(request: Request) -> Optional[dict]:
        current_user = get_user_or_none(request)
        
        if not current_user:
            return None
        
        # Check role requirement
        user_role = current_user["role"]
        if not has_role(user_role, required_role):
            return None
        
        return current_user
    
    return auth_checker