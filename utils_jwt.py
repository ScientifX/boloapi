"""
JWT utilities for authentication
Handles token generation, validation, and claims extraction
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from auth import UserRole
from config import API_JWT_SECRET_KEY, API_JWT_ALGORITHM, API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES

class JWTError(Exception):
    """Custom exception for JWT-related errors"""
    pass


def resolve_display_name(
    codename: str = None,
    first_name: str = None,
    last_name: str = None,
    email: str = None
) -> Optional[str]:
    """
    Resolve the display name for a user using priority order:
    1. Codename (if set)
    2. Full name assembled from first and/or last name (whichever are set)
    3. Email address as fallback (returned as-is; caller may choose to strip domain)

    Returns None only when all inputs are absent.
    """
    if codename:
        return codename
    name_parts = [p for p in [first_name, last_name] if p]
    if name_parts:
        return " ".join(name_parts)
    if email:
        return email
    return None


def create_access_token(
    user_id: str,
    role: UserRole,
    email: str = None,
    codename: str = None,
    first_name: str = None,
    last_name: str = None,
    billing_cycle: str = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token with user claims.
    
    Args:
        user_id: The user's UUID as string
        role: The user's role (from UserRole enum)
        email: User email address
        codename: Optional codename (takes display priority if set)
        first_name: Optional first name (used for display when no codename)
        last_name: Optional last name (used for display when no codename)
        billing_cycle: Optional billing cycle (monthly, quarterly, annual)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token as string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Ensure we have an integer for timedelta
        expire_minutes = int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) if isinstance(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES, str) else API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    
    to_encode = {
        "sub": user_id,               # Subject (user_id)
        "role": role.value,           # User role
        "email": email,               # User email
        "codename": codename,         # Codename (optional, highest display priority)
        "first_name": first_name,     # First name (optional)
        "last_name": last_name,       # Last name (optional)
        "billing_cycle": billing_cycle,  # Billing cycle (monthly, quarterly, annual, or None)
        "exp": expire,                # Expiration time
        "iat": datetime.now(timezone.utc),  # Issued at
        "type": "access"              # Token type
        }
    
    encoded_jwt = jwt.encode(to_encode, API_JWT_SECRET_KEY, algorithm=API_JWT_ALGORITHM)
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
        payload = jwt.decode(token, API_JWT_SECRET_KEY, algorithms=[API_JWT_ALGORITHM])
        
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