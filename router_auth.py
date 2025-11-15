"""
Authentication Router - COMPLETE LOGIN & PASSWORD MANAGEMENT SYSTEM
Handles: registration, activation, login, password setting, forgot password, 
password reset, password change
Supports: Content negotiation (JSON + HTML), email notifications, JWT tokens
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Request, status, Query, Depends
from fastapi.responses import Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DB_CONFIG, API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from auth import UserRole
from jwt_auth import require_jwt_role
from security_utils import (
    generate_api_key_and_hash,
    generate_activation_token,
    verify_api_key,
    is_valid_email,
    hash_password,
    verify_password,
    validate_password_strength
    )
from jwt_utils import create_access_token
from email_utils import (
    send_activation_email,
    send_api_key_email,
    send_welcome_email,
    send_password_reset_email,
    send_password_changed_email,
    EmailConfig
    )
from response_utils import render_or_json, render_error

templates = Jinja2Templates(directory="templates")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# Router
router = APIRouter(prefix="/v1/auth", tags=["Authentication"])

# ====================================================================
# REQUEST/RESPONSE MODELS
# ====================================================================

class RegisterRequest(BaseModel):
    email: str = Field(..., description="Valid email address", max_length=255)
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class LoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class SetPasswordRequest(BaseModel):
    user_id: str
    password: str = Field(..., min_length=8)
    password_confirm: str = Field(..., min_length=8)
    
    @field_validator('password')
    @classmethod
    def validate_password_strength_field(cls, v):
        is_valid, error = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @field_validator('password_confirm')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError("Passwords do not match")
        return v

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str = Field(..., min_length=8)
    
    @field_validator('new_password')
    @classmethod
    def validate_password_strength_field(cls, v):
        is_valid, error = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @field_validator('new_password_confirm')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError("Passwords do not match")
        return v

class ForgotPasswordRequest(BaseModel):
    email: str
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    password_confirm: str = Field(..., min_length=8)
    
    @field_validator('password')
    @classmethod
    def validate_password_strength_field(cls, v):
        is_valid, error = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @field_validator('password_confirm')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError("Passwords do not match")
        return v

class TokenRequest(BaseModel):
    """Request model for token generation"""
    api_key: str = Field(..., description="Your API key", min_length=32, max_length=64)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str

# ====================================================================
# DATABASE HELPERS
# ====================================================================

@contextmanager
def get_db_connection():
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
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM tbl_users WHERE email = %s", (email,))
            return cur.fetchone()

def get_user_by_id(user_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM tbl_users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def get_user_by_activation_token(token: str) -> Optional[dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM tbl_users WHERE activation_token = %s", (token,))
            return cur.fetchone()

def get_user_by_reset_token(token: str) -> Optional[dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM tbl_users 
                   WHERE password_reset_token = %s 
                   AND password_reset_expires_at > NOW()""",
                (token,)
            )
            return cur.fetchone()

# ====================================================================
# WEB PAGE ROUTES (Serve HTML)
# ====================================================================

@router.get("/login")
@limiter.limit(rate_max)
async def login_page(request: Request):
    """Display login form"""
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.get("/signup")
@limiter.limit(rate_max)
async def signup_page(request: Request):
    """Display signup form"""
    return templates.TemplateResponse("auth/signup.html", {"request": request})

@router.get("/set_password")
@limiter.limit(rate_max)
async def set_password_page(
    request: Request,
    user_id: str = Query(...),
    token: str = Query(None)
):
    """Display set password form after activation"""
    user = get_user_by_id(user_id)
    
    if not user or not user['is_active'] or user['password_hash']:
        return templates.TemplateResponse(
            "auth/set_password_error.html",
            {"request": request, "error": "Invalid request"}
        )
    
    return templates.TemplateResponse(
        "auth/set_password.html",
        {"request": request, "user_id": user_id, "email": user['email']}
    )

@router.get("/forgot_password")
@limiter.limit(rate_max)
async def forgot_password_page(request: Request):
    """Display forgot password form"""
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})

@router.get("/reset_password")
@limiter.limit(rate_max)
async def reset_password_page(request: Request, token: str = Query(...)):
    """Display reset password form with token"""
    user = get_user_by_reset_token(token)
    
    if not user:
        return templates.TemplateResponse(
            "auth/reset_password_error.html",
            {"request": request, "error": "Invalid or expired token"}
        )
    
    return templates.TemplateResponse(
        "auth/reset_password.html",
        {"request": request, "token": token, "email": user['email']}
    )

@router.get("/change_password")
@limiter.limit(rate_max)
async def change_password_page(request: Request):
    """Display change password form (dashboard)"""
    return templates.TemplateResponse("auth/change_password.html", {"request": request})

# ====================================================================
# AUTHENTICATION ENDPOINTS
# ====================================================================

@router.post("/register")
@limiter.limit(rate_max)
async def register(request: Request, register_req: RegisterRequest):
    """Register new user - sends activation email"""
    try:
        email = register_req.email
        existing_user = get_user_by_email(email)
        
        if existing_user and existing_user['is_active']:
            return await render_error(
                request, "auth/register_error.html",
                status.HTTP_400_BAD_REQUEST,
                "Email already registered"
            )
        
        if existing_user:
            # Resend activation
            send_activation_email(email, existing_user['activation_token'])
            return await render_or_json(
                request, "auth/register_success.html",
                {"message": "Activation email resent", "email": email}
            )
        
        # Create new user
        activation_token = generate_activation_token()
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tbl_users (email, activation_token, role, is_active)
                       VALUES (%s, %s, %s, %s) RETURNING user_id""",
                    (email, activation_token, UserRole.BASIC.value, False)
                )
                user_id = cur.fetchone()[0]
                conn.commit()
        
        logger.info(f"New user registered: {email}")
        send_activation_email(email, activation_token)
        
        return await render_or_json(
            request, "auth/register_success.html",
            {"message": "Registration successful", "email": email, "user_id": str(user_id)}
        )
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return await render_error(
            request, "auth/register_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.get("/activate")
@limiter.limit(rate_max)
async def activate(request: Request, token: str = Query(...)):
    """Activate account and redirect to set password"""
    try:
        user = get_user_by_activation_token(token)
        
        if not user:
            return await render_error(
                request, "auth/activate_error.html",
                status.HTTP_404_NOT_FOUND, "Invalid token"
            )
        
        if user['is_active']:
            return RedirectResponse("/v1/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
        # Generate API key and activate
        api_key, api_key_hash = generate_api_key_and_hash()
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET is_active = TRUE, api_key_hash = %s, 
                           activated_at = NOW(), updated_at = NOW()
                       WHERE user_id = %s""",
                    (api_key_hash, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"User activated: {user['email']}")
        send_welcome_email(user['email'], api_key)
        
        # Redirect to set password
        return RedirectResponse(
            f"/v1/auth/set_password?user_id={user['user_id']}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        logger.error(f"Activation error: {str(e)}")
        return await render_error(
            request, "auth/activate_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

# ====================================================================
# PASSWORD MANAGEMENT ENDPOINTS
# ====================================================================

@router.post("/set_password")
@limiter.limit(rate_max)
async def set_password(request: Request, password_req: SetPasswordRequest):
    """Set password after activation"""
    try:
        user = get_user_by_id(password_req.user_id)
        
        if not user or not user['is_active'] or user['password_hash']:
            return await render_error(
                request, "auth/set_password_error.html",
                status.HTTP_400_BAD_REQUEST, "Invalid request"
            )
        
        password_hash = hash_password(password_req.password)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET password_hash = %s, password_set_at = NOW(), updated_at = NOW()
                       WHERE user_id = %s""",
                    (password_hash, password_req.user_id)
                )
                conn.commit()
        
        logger.info(f"Password set for: {user['email']}")
        
        return await render_or_json(
            request, "auth/set_password_success.html",
            {"message": "Password set successfully", "login_link": "/v1/auth/login"}
        )
        
    except Exception as e:
        logger.error(f"Set password error: {str(e)}")
        return await render_error(
            request, "auth/set_password_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.post("/login", response_model=TokenResponse)
@limiter.limit(rate_max)
async def login(request: Request, login_req: LoginRequest):
    """Login with email/password"""
    try:
        user = get_user_by_email(login_req.email)
        
        if not user or not user['is_active'] or not user['password_hash']:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        
        if not verify_password(login_req.password, user['password_hash']):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        
        # Update last login
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tbl_users SET last_login_at = NOW() WHERE user_id = %s",
                    (user['user_id'],)
                )
                conn.commit()
        
        logger.info(f"User logged in: {user['email']}")
        
        # Create JWT
        user_role = UserRole(user['role'])
        access_token = create_access_token(user_id=str(user['user_id']), role=user_role)
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            role=user_role.value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Login failed")

@router.post("/forgot_password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, forgot_req: ForgotPasswordRequest):
    """Request password reset"""
    try:
        user = get_user_by_email(forgot_req.email)
        
        # Always return success (prevent enumeration)
        if not user or not user['is_active']:
            return await render_or_json(
                request, "auth/forgot_password_success.html",
                {"message": "If account exists, reset email sent"}
            )
        
        # Generate reset token (valid 1 hour)
        reset_token = generate_activation_token()
        reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET password_reset_token = %s, password_reset_expires_at = %s,
                           updated_at = NOW()
                       WHERE user_id = %s""",
                    (reset_token, reset_expires, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"Password reset requested: {user['email']}")
        send_password_reset_email(user['email'], reset_token)
        
        return await render_or_json(
            request, "auth/forgot_password_success.html",
            {"message": "Reset email sent", "email": forgot_req.email}
        )
        
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        return await render_error(
            request, "auth/forgot_password_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.post("/reset_password")
@limiter.limit(rate_max)
async def reset_password(request: Request, reset_req: ResetPasswordRequest):
    """Reset password with token"""
    try:
        user = get_user_by_reset_token(reset_req.token)
        
        if not user:
            return await render_error(
                request, "auth/reset_password_error.html",
                status.HTTP_400_BAD_REQUEST, "Invalid or expired token"
            )
        
        password_hash = hash_password(reset_req.password)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET password_hash = %s, password_reset_token = NULL,
                           password_reset_expires_at = NULL,
                           last_password_change_at = NOW(), updated_at = NOW()
                       WHERE user_id = %s""",
                    (password_hash, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"Password reset: {user['email']}")
        send_password_changed_email(user['email'])
        
        return await render_or_json(
            request, "auth/reset_password_success.html",
            {"message": "Password reset successful", "login_link": "/v1/auth/login"}
        )
        
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}")
        return await render_error(
            request, "auth/reset_password_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.post("/change_password")
@limiter.limit(rate_max)
async def change_password(
    request: Request,
    password_req: ChangePasswordRequest,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """Change password (authenticated)"""
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user['password_hash']:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No password set")
        
        if not verify_password(password_req.current_password, user['password_hash']):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password incorrect")
        
        new_password_hash = hash_password(password_req.new_password)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET password_hash = %s, last_password_change_at = NOW(),
                           updated_at = NOW()
                       WHERE user_id = %s""",
                    (new_password_hash, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"Password changed: {user['email']}")
        send_password_changed_email(user['email'])
        
        return await render_or_json(
            request, "auth/change_password_success.html",
            {"message": "Password changed successfully"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to change password")

# ====================================================================
# API KEY ENDPOINTS
# ====================================================================

@router.post("/token", response_model=TokenResponse)
@limiter.limit(rate_max)
async def get_token(request: Request, token_req: TokenRequest):
    """Generate JWT from API key"""
    try:
        api_key = token_req.get('api_key')
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM tbl_users WHERE is_active = TRUE")
                users = cur.fetchall()
        
        user = None
        for u in users:
            if verify_api_key(api_key, u['api_key_hash']):
                user = u
                break
        
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        
        user_role = UserRole(user['role'])
        access_token = create_access_token(user_id=str(user['user_id']), role=user_role)
        
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
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to generate token")

