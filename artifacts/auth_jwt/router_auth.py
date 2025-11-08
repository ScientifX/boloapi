"""
Authentication Router
Handles user registration, activation, and JWT token generation
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DB_CONFIG, API_AZURE_CLIENT_ID, API_EMAIL_FROM_ADDRESS
from auth import UserRole
from security_utils import (
    generate_api_key_and_hash,
    generate_activation_token,
    verify_api_key,
    is_valid_email
)
from jwt_utils import create_access_token, decode_access_token, JWTError

# Rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# Router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class RegisterRequest(BaseModel):
    """Request model for user registration"""
    email: str = Field(..., description="Valid email address", max_length=255)
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format"""
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class RegisterResponse(BaseModel):
    """Response after successful registration"""
    message: str
    user_id: str
    email: str
    note: str

class ActivateResponse(BaseModel):
    """Response after successful activation"""
    message: str
    api_key: str
    instructions: str

class TokenRequest(BaseModel):
    """Request model for token generation"""
    api_key: str = Field(..., description="Your API key", min_length=32, max_length=64)

class TokenResponse(BaseModel):
    """Response containing JWT access token"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    role: str

class ResetKeyResponse(BaseModel):
    """Response after API key reset"""
    message: str
    api_key: str
    instructions: str

# ============================================================================
# DATABASE HELPERS
# ============================================================================

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email address"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )
            return cur.fetchone()

def get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by user_id"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()

def get_user_by_activation_token(token: str) -> Optional[dict]:
    """Get user by activation token"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users WHERE activation_token = %s",
                (token,)
            )
            return cur.fetchone()

# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="""
    Register a new user account with email.
    
    **Process:**
    1. Submit a valid email address
    2. Receive confirmation with user_id
    3. Check your email for activation link
    4. Click link to activate and receive API key
    
    **Note:** If email already exists and is inactive, a new activation email will be sent.
    If already active, you'll be informed to use the existing account.
    """
)
@limiter.limit(rate_max)
async def register(request: Request, register_req: RegisterRequest):
    """
    Register a new user account.
    Sends activation email with secure token.
    """
    try:
        email = register_req.email
        
        # Check if user already exists
        existing_user = get_user_by_email(email)
        
        if existing_user:
            if existing_user['is_active']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered and active. Use /auth/token to get access token or /auth/key/reset to reset your API key."
                )
            else:
                # User exists but not activated - resend activation
                user_id = existing_user['user_id']
                activation_token = generate_activation_token()
                activation_expires = datetime.now(timezone.utc) + timedelta(hours=48)
                
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE users 
                            SET activation_token = %s,
                                activation_expires_at = %s,
                                updated_at = NOW()
                            WHERE user_id = %s
                            """,
                            (activation_token, activation_expires, user_id)
                        )
                        conn.commit()
                
                # TODO: Send activation email
                # send_activation_email(email, activation_token)
                
                return RegisterResponse(
                    message="Activation email resent",
                    user_id=str(user_id),
                    email=email,
                    note=f"Check your email for the activation link. For testing: /auth/activate?token={activation_token}"
                )
        
        # Create new user
        api_key, api_key_hash = generate_api_key_and_hash()
        activation_token = generate_activation_token()
        activation_expires = datetime.now(timezone.utc) + timedelta(hours=48)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (
                        email, role, api_key_hash, activation_token, activation_expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING user_id
                    """,
                    (email, UserRole.BASIC.value, api_key_hash, activation_token, activation_expires)
                )
                result = cur.fetchone()
                user_id = result['user_id']
                conn.commit()
        
        # TODO: Send activation email
        # send_activation_email(email, activation_token)
        
        return RegisterResponse(
            message="Registration successful. Check your email for activation link.",
            user_id=str(user_id),
            email=email,
            note=f"For testing, activate at: /auth/activate?token={activation_token}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.get(
    "/activate",
    response_model=ActivateResponse,
    summary="Activate Account",
    description="""
    Activate your account using the token from your activation email.
    
    **Process:**
    1. Click the link in your activation email
    2. Your account will be activated
    3. You'll receive your API key
    
    **Important:** Save your API key securely. You'll need it to get access tokens.
    """
)
@limiter.limit(rate_max)
async def activate(request: Request, token: str):
    """
    Activate user account with activation token.
    Returns the API key upon successful activation.
    """
    try:
        # Get user by activation token
        user = get_user_by_activation_token(token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired activation token"
                )
        
        # Check if already activated
        if user['is_active']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account already activated. Use /auth/token to get access token."
                )
        
        # Check if token expired
        if user['activation_expires_at'] and user['activation_expires_at'] < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Activation token expired. Please register again."
                )
        
        # Get the API key hash (we'll need to show instructions)
        # Note: We can't retrieve the original API key since it's hashed
        # For activation, we need to generate a new one
        api_key, api_key_hash = generate_api_key_and_hash()
        
        # Activate account
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET is_active = TRUE,
                        activation_token = NULL,
                        activation_expires_at = NULL,
                        api_key_hash = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (api_key_hash, user['user_id'])
                    )
                conn.commit()
        
        return ActivateResponse(
            message="Account activated successfully!",
            api_key=api_key,
            instructions="Save this API key securely. Use it with /auth/token to get access tokens. You won't be able to see this key again."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Activation failed: {str(e)}"
            )

@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Get Access Token",
    description="""
    Exchange your API key for a JWT access token.
    
    **Process:**
    1. Submit your API key
    2. Receive a JWT access token (valid for 1 hour)
    3. Include token in Authorization header for API requests: `Authorization: Bearer {token}`
    
    **Note:** Tokens expire after 1 hour. Request a new token when needed.
    """
    )
@limiter.limit(rate_max)
async def get_token(request: Request, token_req: TokenRequest):
    """
    Generate JWT access token from API key.
    """
    try:
        api_key = token_req.api_key
        
        # Find user by verifying API key against all active users
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT user_id, api_key_hash, role, is_active FROM users WHERE is_active = TRUE"
                    )
                users = cur.fetchall()
        
        # Verify API key against each user's hash
        authenticated_user = None
        for user in users:
            if verify_api_key(api_key, user['api_key_hash']):
                authenticated_user = user
                break
        
        if not authenticated_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key or account not activated"
                )
        
        # Update last login timestamp
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE user_id = %s",
                    (authenticated_user['user_id'],)
                    )
                conn.commit()
        
        # Create JWT token
        user_role = UserRole(authenticated_user['role'])
        access_token = create_access_token(
            user_id=str(authenticated_user['user_id']),
            role=user_role
            )
        
        from jwt_utils import JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
            role=user_role.value
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token generation failed: {str(e)}"
            )

@router.post(
    "/key/reset",
    response_model=ResetKeyResponse,
    summary="Reset API Key",
    description="""
    Reset your API key (for lost keys or security reasons).
    
    **Process:**
    1. Submit your email address
    2. A new API key will be generated
    3. Check your email for the new key
    
    **Security Note:** This will invalidate your old API key and all tokens generated from it.
    """
)
@limiter.limit("3/hour")  # Stricter rate limit for security
async def reset_api_key(request: Request, register_req: RegisterRequest):
    """
    Reset API key for an existing active user.
    Sends new API key via email.
    """
    try:
        email = register_req.email
        
        # Get user
        user = get_user_by_email(email)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found. Please register first."
            )
        
        if not user['is_active']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account not activated. Please activate your account first."
            )
        
        # Generate new API key
        api_key, api_key_hash = generate_api_key_and_hash()
        
        # Update in database
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET api_key_hash = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (api_key_hash, user['user_id'])
                )
                conn.commit()
        
        # TODO: Send new API key via email
        # send_api_key_email(email, api_key)
        
        return ResetKeyResponse(
            message="API key reset successful",
            api_key=api_key,
            instructions="Your old API key and all tokens generated from it are now invalid. Save this new key securely."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Key reset failed: {str(e)}"
        )

@router.get(
    "/",
    summary="Authentication Information",
    description="Get information about authentication endpoints and flow"
)
async def auth_info():
    """Return authentication information"""
    return {
        "name": "Authentication API",
        "version": "1.0.0",
        "flow": {
            "1_register": "POST /auth/register with email",
            "2_activate": "GET /auth/activate?token={token} from email",
            "3_get_token": "POST /auth/token with API key",
            "4_use_token": "Include 'Authorization: Bearer {token}' header in requests"
        },
        "endpoints": {
            "/register": "Register new user account",
            "/activate": "Activate account with email token",
            "/token": "Get JWT access token from API key",
            "/key/reset": "Reset API key for existing user"
        },
        "token_info": {
            "type": "JWT Bearer",
            "expiration": "1 hour",
            "usage": "Authorization: Bearer {access_token}"
        }
    }
