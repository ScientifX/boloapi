"""
Authentication Router (Production Version with Email Integration)
Handles user registration, activation, and JWT token generation
Includes Microsoft Graph API email functionality
Supports both HTML and JSON responses via content negotiation
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Request, status, Query
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DB_CONFIG, API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from auth import UserRole
from security_utils import (
    generate_api_key_and_hash,
    generate_activation_token,
    verify_api_key,
    is_valid_email
)
from jwt_utils import create_access_token
from email_utils import (
    send_activation_email,
    send_api_key_email,
    send_welcome_email,
    EmailConfig
)
from response_utils import render_or_json, render_error

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    email_sent: bool

class ActivateResponse(BaseModel):
    """Response after successful activation"""
    message: str
    api_key: str
    instructions: str
    email_sent: bool

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
    email_sent: bool

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
                "SELECT * FROM tbl_users WHERE email = %s",
                (email,)
            )
            return cur.fetchone()

def get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by user_id"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM tbl_users WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()

def get_user_by_activation_token(token: str) -> Optional[dict]:
    """Get user by activation token"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM tbl_users WHERE activation_token = %s",
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
    
    **Email:** Activation email will be sent if email is configured. Otherwise, activation token 
    will be provided in response for testing purposes.
    """
)
@limiter.limit(rate_max)
async def register(request: Request, register_req: RegisterRequest):
    """
    Register a new user account.
    Sends activation email with secure token if email is configured.
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
                activation_expires = datetime.now(timezone.utc) + timedelta(hours=1)
                
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE tbl_users 
                            SET activation_token = %s,
                                activation_expires_at = %s,
                                updated_at = NOW()
                            WHERE user_id = %s
                            """,
                            (activation_token, activation_expires.replace(tzinfo=None), user_id)
                        )
                        conn.commit()
                
                # Send activation email if configured
                email_sent = False
                if EmailConfig.is_configured():
                    try:
                        email_sent = send_activation_email(email, activation_token)
                        if email_sent:
                            logger.info(f"Activation email resent to {email}")
                        else:
                            logger.warning(f"Failed to send activation email to {email}")
                    except Exception as e:
                        logger.error(f"Error sending activation email to {email}: {str(e)}")
                else:
                    logger.warning("Email not configured - activation email not sent")
                
                # Prepare response
                if email_sent:
                    note = "Check your email for the activation link."
                else:
                    note = f"Email not configured. For testing, activate at: /auth/activate?token={activation_token}"
                
                return RegisterResponse(
                    message="Activation email resent" if email_sent else "Registration record updated (email disabled)",
                    user_id=str(user_id),
                    email=email,
                    note=note,
                    email_sent=email_sent
                )
        
        # Create new user
        api_key, api_key_hash = generate_api_key_and_hash()
        activation_token = generate_activation_token()
        activation_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO tbl_users (
                        email, role, api_key_hash, activation_token, activation_expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING user_id
                    """,
                    (email, UserRole.BASIC.value, api_key_hash, activation_token, activation_expires.replace(tzinfo=None))
                )
                result = cur.fetchone()
                user_id = result['user_id']
                conn.commit()
        
        logger.info(f"New user registered: {email} (user_id: {user_id})")
        
        # Send activation email if configured
        email_sent = False
        if EmailConfig.is_configured():
            try:
                email_sent = send_activation_email(email, activation_token)
                if email_sent:
                    logger.info(f"Activation email sent to {email}")
                else:
                    logger.warning(f"Failed to send activation email to {email}")
            except Exception as e:
                logger.error(f"Error sending activation email to {email}: {str(e)}")
        else:
            logger.warning("Email not configured - activation email not sent")
        
        # Prepare response
        if email_sent:
            message = "Registration successful. Check your email for activation link."
            note = (
                "📧 STEP 1: Check your email for the ACTIVATION link and click it. "
                "📧 STEP 2: After clicking, you'll receive a WELCOME email with your API key. "
                "Use the API key from the WELCOME email (not the activation email)."
            )
        else:
            message = "Registration successful (email disabled)"
            note = f"For testing, activate at: /auth/activate?token={activation_token}"
        
        return RegisterResponse(
            message=message,
            user_id=str(user_id),
            email=email,
            note=note,
            email_sent=email_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.get(
    "/activate",
    summary="Activate Account",
    description="""
    Activate your account using the token sent to your email.
    
    **Response Format:**
    - Browser/HTML request: Returns styled activation page
    - API/JSON request (Accept: application/json): Returns JSON with activation details
    
    **Process:**
    1. Click the activation link in your email (or use token from registration response if email disabled)
    2. Account is activated
    3. Receive your API key on the page (and via email if configured)
    4. Welcome email sent with API key copy (if email configured)
    
    **Important:** Save your API key securely. You'll need it to get access tokens.
    
    **Note:** Activation tokens expire after 1 hour.
    """
)
@limiter.limit(rate_max)
async def activate(request: Request, token: str = Query(..., description="Activation token from email")):
    """
    Activate user account with token from email.
    Generates and returns API key.
    Sends welcome email with API key if email is configured.
    Returns HTML page for browser requests, JSON for API requests.
    """
    try:
        # Find user by activation token
        user = get_user_by_activation_token(token)
        
        if not user:
            return render_error(
                request=request,
                template_name="auth/activate_error.html",
                error_message="The activation link is invalid or has expired.",
                error_type="Invalid or expired activation token",
                context={"base_url": EmailConfig.APP_BASE_URL},
                status_code=404
            )
        
        # Check if already activated
        if user['is_active']:
            return render_error(
                request=request,
                template_name="auth/activate_error.html",
                error_message="Your account is already active. You can use your existing API key to get access tokens.",
                error_type="Account already activated",
                context={"base_url": EmailConfig.APP_BASE_URL},
                status_code=400
            )
        
        # Check if token expired
        if user['activation_expires_at']:
            # Make comparison timezone-aware or timezone-naive depending on database value
            expiry_time = user['activation_expires_at']
            current_time = datetime.now(timezone.utc)
            
            # If expiry_time is naive (no timezone), make current_time naive too
            if expiry_time.tzinfo is None:
                current_time = datetime.now()
            
            if expiry_time < current_time:
                return render_error(
                    request=request,
                    template_name="auth/activate_error.html",
                    error_message="The activation link has expired (links are valid for 1 hour). Please register again to receive a new activation link.",
                    error_type="Invalid or expired activation token",
                    context={"base_url": EmailConfig.APP_BASE_URL},
                    status_code=400
                )
        
        # Generate new API key for activation
        api_key, api_key_hash = generate_api_key_and_hash()
        
        # Activate account
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
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
        
        logger.info(f"Account activated: {user['email']} (user_id: {user['user_id']})")
        
        # Send welcome email with API key if configured
        email_sent = False
        if EmailConfig.is_configured():
            try:
                email_sent = send_welcome_email(user['email'], api_key)
                if email_sent:
                    logger.info(f"Welcome email sent to {user['email']}")
                else:
                    logger.warning(f"Failed to send welcome email to {user['email']}")
            except Exception as e:
                logger.error(f"Error sending welcome email to {user['email']}: {str(e)}")
        else:
            logger.warning("Email not configured - welcome email not sent")
        
        # Prepare response data
        json_data = {
            "message": "Account activated successfully!",
            "api_key": api_key,
            "email_sent": email_sent,
            "instructions": "Save this API key securely. Use it with /auth/token to get access tokens."
        }
        
        template_context = {
            "api_key": api_key,
            "email_sent": email_sent,
            "base_url": EmailConfig.APP_BASE_URL
        }
        
        return render_or_json(
            request=request,
            template_name="auth/activate_success.html",
            context=template_context,
            json_data=json_data,
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Activation error: {str(e)}")
        return render_error(
            request=request,
            template_name="auth/activate_error.html",
            error_message=f"An unexpected error occurred: {str(e)}",
            error_type="Activation Failed",
            context={"base_url": EmailConfig.APP_BASE_URL},
            status_code=500
        )

# ... (rest of the endpoints remain unchanged - /token, /key/reset, /, /health)
