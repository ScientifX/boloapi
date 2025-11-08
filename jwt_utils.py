"""
JWT utilities for authentication
Handles token generation, validation, and claims extraction
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import jwt

from auth import UserRole

# JWT Configuration
API_JWT_SECRET_KEY = os.getenv("API_JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production-min-32-chars")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour

class JWTError(Exception):
    """Custom exception for JWT-related errors"""
    pass

def create_access_token(user_id: str, role: UserRole, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token with user claims.
    
    Args:
        user_id: The user's UUID as string
        role: The user's role (from UserRole enum)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token as string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": user_id,  # Subject (user_id)
        "role": role.value,  # User role
        "exp": expire,  # Expiration time
        "iat": datetime.utcnow(),  # Issued at
        "type": "access"  # Token type
    }
    
    encoded_jwt = jwt.encode(to_encode, API_JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: The JWT token string
        
    Returns:
        Dictionary containing the token claims (sub, role, exp, iat, type)
        
    Raises:
        JWTError: If token is invalid, expired, or malformed
    """
    try:
        payload = jwt.decode(token, API_JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Validate token type
        if payload.get("type") != "access":
            raise JWTError("Invalid token type")
        
        return payload
    
    except jwt.ExpiredSignatureError:
        raise JWTError("Token has expired")
    except jwt.InvalidTokenError:
        raise JWTError("Invalid token")
    except Exception as e:
        raise JWTError(f"Token validation error: {str(e)}")

def extract_user_id(token: str) -> str:
    """
    Extract user_id from token without full validation (for logging).
    Returns None if extraction fails.
    """
    try:
        payload = decode_access_token(token)
        return payload.get("sub")
    except:
        return None

def extract_role(token: str) -> Optional[UserRole]:
    """
    Extract role from token.
    Returns None if extraction fails or role is invalid.
    """
    try:
        payload = decode_access_token(token)
        role_str = payload.get("role")
        return UserRole(role_str)
    except:
        return None

def verify_token_not_expired(token: str) -> bool:
    """
    Quick check if token is expired without full validation.
    Returns True if not expired, False otherwise.
    """
    try:
        decode_access_token(token)
        return True
    except JWTError as e:
        if "expired" in str(e).lower():
            return False
        return False
    except:
        return False