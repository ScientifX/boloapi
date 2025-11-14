"""
JWT Authentication Dependencies
Provides FastAPI dependencies for protecting endpoints with JWT tokens
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import UserRole, has_role
from jwt_utils import decode_access_token, JWTError

# HTTP Bearer token scheme
security = HTTPBearer(
    scheme_name="JWT Bearer Token",
    description="Enter your JWT access token (get from /v1/auth/token)",
    auto_error=False  # Don't auto-error, we'll handle it ourselves
)

def get_current_user_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Extract and validate JWT token from Authorization header.
    Returns user claims (user_id, role) from valid token.
    
    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token. Include 'Authorization: Bearer {token}' header.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    
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
        
        return {
            "user_id": user_id,
            "role": role
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
                detail=f"Access denied. Required role: {required_role.value} or higher. Your role: {user_role.value}"
            )
        
        return current_user
    
    return role_checker

# Optional: Dependency for endpoints that work with or without authentication
def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Optional authentication - returns user info if token provided and valid,
    None otherwise. Useful for endpoints that provide different features
    based on authentication status.
    """
    if not credentials:
        return None
    
    try:
        return get_current_user_from_token(credentials)
    except HTTPException:
        return None
