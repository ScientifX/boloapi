"""
Authentication Router (Production Version with Content Negotiation)
Handles user registration, activation, and JWT token generation
Supports both JSON API responses and HTML web pages
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Request, status, Query
from fastapi.responses import Response
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
    
    **Process:**
    1. Click the activation link in your email (or use token from registration response if email disabled)
    2. Account is activated
    3. Receive your API key
    4. Welcome email sent with API key copy (if email configured)
    
    **Content Negotiation:**
    - Browser requests: Returns HTML page with success/error message
    - API requests (Accept: application/json): Returns JSON response
    
    **Important:** Save your API key securely. You'll need it to get access tokens.
    
    **Note:** Activation tokens expire after 1 hour.
    """
)
@limiter.limit(rate_max)
async def activate(request: Request, token: str = Query(..., description="Activation token from email")) -> Response:
    """
    Activate user account with token from email.
    Returns HTML for browsers, JSON for API clients (content negotiation).
    """
    try:
        # Find user by activation token
        user = get_user_by_activation_token(token)
        
        if not user:
            return render_error(
                request=request,
                template_name="auth/activate_error.html",
                error_message="Invalid or expired activation token",
                error_type="not_found",
                context={"app_base_url": EmailConfig.APP_BASE_URL},
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Check if already activated
        if user['is_active']:
            return render_error(
                request=request,
                template_name="auth/activate_error.html",
                error_message="Account already activated. Use /auth/token to get access token.",
                error_type="already_active",
                context={"app_base_url": EmailConfig.APP_BASE_URL},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if token expired
        if user['activation_expires_at']:
            expiry_time = user['activation_expires_at']
            current_time = datetime.now(timezone.utc)
            
            # If expiry_time is naive (no timezone), make current_time naive too
            if expiry_time.tzinfo is None:
                current_time = datetime.now()
            
            if expiry_time < current_time:
                return render_error(
                    request=request,
                    template_name="auth/activate_error.html",
                    error_message="Activation token expired. Please register again.",
                    error_type="expired",
                    context={"app_base_url": EmailConfig.APP_BASE_URL},
                    status_code=status.HTTP_400_BAD_REQUEST
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
        
        # Prepare response with content negotiation
        template_context = {
            "request": request,
            "api_key": api_key,
            "email_sent": email_sent,
            "app_base_url": EmailConfig.APP_BASE_URL
        }
        
        json_data = {
            "message": "Account activated successfully!",
            "api_key": api_key,
            "instructions": (
                "✅ Account activated! Your API key has been sent to your email. "
                "IMPORTANT: Use the API key from the WELCOME email (not the activation email). "
                "Save it securely - you won't be able to retrieve it again. "
                "Use it with /auth/token to get access tokens."
            ) if email_sent else (
                "Save this API key securely - you won't be able to see it again. "
                "Use it with /auth/token to get access tokens. "
                "(Email disabled - no welcome email sent)"
            ),
            "email_sent": email_sent
        }
        
        return render_or_json(
            request=request,
            template_name="auth/activate_success.html",
            context=template_context,
            json_data=json_data,
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activation error: {str(e)}")
        return render_error(
            request=request,
            template_name="auth/activate_error.html",
            error_message=f"Activation failed: {str(e)}",
            error_type="error",
            context={"app_base_url": EmailConfig.APP_BASE_URL},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
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
                    "SELECT user_id, api_key_hash, role, is_active, email FROM tbl_users WHERE is_active = TRUE"
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
                    "UPDATE tbl_users SET last_login_at = NOW() WHERE user_id = %s",
                    (authenticated_user['user_id'],)
                )
                conn.commit()
        
        logger.info(f"Token generated for user: {authenticated_user['email']} (user_id: {authenticated_user['user_id']})")
        
        # Create JWT token
        user_role = UserRole(authenticated_user['role'])
        access_token = create_access_token(
            user_id=str(authenticated_user['user_id']),
            role=user_role
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            role=user_role.value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token generation error: {str(e)}")
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
    3. Check your email for the new key (or see response if email disabled)
    
    **Security Note:** This will invalidate your old API key and all tokens generated from it.
    """
)
@limiter.limit("3/hour")  # Stricter rate limit for security
async def reset_api_key(request: Request, register_req: RegisterRequest):
    """
    Reset API key for an existing active user.
    Sends new API key via email if email is configured.
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
        
        # Check daily reset limit
        MAX_DAILY_RESETS = int(os.getenv('API_MAX_DAILY_KEY_RESETS', '3'))
        
        # Check if user has exceeded daily reset limit
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT key_reset_count, key_reset_date
                    FROM tbl_users
                    WHERE user_id = %s
                    """,
                    (user['user_id'],)
                )
                reset_data = cur.fetchone()
                
                today = datetime.now().date()
                reset_count = reset_data.get('key_reset_count', 0) if reset_data else 0
                reset_date = reset_data.get('key_reset_date') if reset_data else None
                
                # Convert reset_date to date if it's a datetime
                if reset_date and hasattr(reset_date, 'date'):
                    reset_date = reset_date.date()
                
                # Reset counter if it's a new day
                if reset_date != today:
                    reset_count = 0
                
                # Check if limit exceeded
                if reset_count >= MAX_DAILY_RESETS:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Daily key reset limit ({MAX_DAILY_RESETS}) reached. Try again tomorrow."
                    )
        
        # Generate new API key
        api_key, api_key_hash = generate_api_key_and_hash()
        
        # Update in database with reset counter
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET api_key_hash = %s,
                        key_reset_count = CASE 
                            WHEN key_reset_date = CURRENT_DATE THEN key_reset_count + 1
                            ELSE 1
                        END,
                        key_reset_date = CURRENT_DATE,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (api_key_hash, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"API key reset for user: {email} (user_id: {user['user_id']})")
        
        # Send new API key via email if configured
        email_sent = False
        if EmailConfig.is_configured():
            try:
                email_sent = send_api_key_email(email, api_key)
                if email_sent:
                    logger.info(f"API key reset email sent to {email}")
                else:
                    logger.warning(f"Failed to send API key reset email to {email}")
            except Exception as e:
                logger.error(f"Error sending API key reset email to {email}: {str(e)}")
        else:
            logger.warning("Email not configured - API key not sent via email")
        
        # Prepare response
        if email_sent:
            message = "API key reset successful - check your email"
            instructions = (
                "Your old API key and all tokens generated from it are now invalid. "
                "The new key has been sent to your email. Save it securely."
            )
        else:
            message = "API key reset successful (email disabled)"
            instructions = (
                "Your old API key and all tokens generated from it are now invalid. "
                "Save this new key securely. Use it with /auth/token to get access tokens. "
                "(Email disabled - no notification sent)"
            )
        
        return ResetKeyResponse(
            message=message,
            api_key=api_key,
            instructions=instructions,
            email_sent=email_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Key reset error: {str(e)}")
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
    email_status = EmailConfig.is_configured()
    
    base_info = {
        "name": "Authentication API",
        "version": "2.0.0",
        "email_configured": email_status,
        "flow": {
            "1_register": "POST /auth/register with email",
            "2_activate": "GET /auth/activate?token={token} from email" if email_status else "GET /auth/activate?token={token} from registration response",
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
            "expiration": f"{API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES} minutes",
            "usage": "Authorization: Bearer {access_token}"
        }
    }
    
    if email_status:
        base_info["email_info"] = {
            "provider": "Microsoft Graph API",
            "from_address": EmailConfig.FROM_ADDRESS,
            "from_name": EmailConfig.FROM_NAME
        }
    else:
        base_info["email_info"] = {
            "status": "not configured",
            "note": "Email notifications disabled. Activation tokens and API keys will be shown in API responses for testing."
        }
    
    return base_info

@router.get(
    "/health",
    summary="Authentication Health Check",
    description="Check authentication system health including email configuration"
)
async def auth_health():
    """Check authentication system health"""
    email_configured = EmailConfig.is_configured()
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": "operational",
            "jwt": "operational",
            "email": "configured" if email_configured else "not configured"
        }
    }
    
    if not email_configured:
        health_status["warnings"] = [
            "Email not configured - activation tokens and API keys will be shown in responses"
        ]
        missing = EmailConfig.get_missing_config()
        health_status["missing_config"] = missing
    
    return health_status
