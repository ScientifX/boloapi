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
from fastapi.responses import Response, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DB_CONFIG, API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES, APP_GLOBALS
from auth import UserRole
from jwt_auth import require_jwt_role, require_browser_auth, get_current_user_from_token
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
from captcha_utils import (
    generate_captcha_token,
    set_captcha_cookie,
    validate_captcha,
    clear_captcha_cookie
)

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(APP_GLOBALS)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiter
rate_max = "3000/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])
captcha_enforce = True

# Router
router = APIRouter(prefix="/v1/auth", tags=["Authentication"])

# ====================================================================
# REQUEST/RESPONSE MODELS
# ====================================================================

class RegisterRequest(BaseModel):
    email: str = Field(..., description="Valid email address", max_length=255)
    captcha_token: str = Field(..., description="CAPTCHA token")
    captcha_checked: bool = Field(..., description="CAPTCHA checkbox status")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class LoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")
    captcha_token: str = Field(..., description="CAPTCHA token")
    captcha_checked: bool = Field(..., description="CAPTCHA checkbox status")
    
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
    captcha_token: str = Field(..., description="CAPTCHA token")
    captcha_checked: bool = Field(..., description="CAPTCHA checkbox status")
    
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
    captcha_token: str = Field(..., description="CAPTCHA token")
    captcha_checked: bool = Field(..., description="CAPTCHA checkbox status")
    
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
    redirect_url: str

class ProfileUpdateRequest(BaseModel):
    email: Optional[str] = None
    codename: Optional[str] = Field(None, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    job_role: Optional[str] = Field(None, max_length=100)
    data_usage: Optional[list[str]] = None
    notify_list_changes: Optional[bool] = None
    notify_status_changes: Optional[bool] = None

    @field_validator('email')
    @classmethod
    def validate_email_field(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                raise ValueError("Email address is required")
            if not is_valid_email(v):
                raise ValueError("Invalid email format")
            return v.lower()
        return None
    
    @field_validator('codename')
    @classmethod
    def validate_codename_field(cls, v):
        if v:
            v = v.strip()
            if len(v) == 0:
                return None
            if len(v) < 2:
                raise ValueError("codename must be at least 2 characters")
            # Allow alphanumeric, spaces, hyphens, underscores
            import re
            if not re.match(r'^[\w\s\-]+$', v):
                raise ValueError("codename can only contain letters, numbers, spaces, hyphens, and underscores")
        return v
    
    @field_validator('first_name', 'last_name', 'company', 'job_role')
    @classmethod
    def validate_string_fields(cls, v):
        if v:
            v = v.strip()
            if len(v) == 0:
                return None
        return v
    
    @field_validator('data_usage')
    @classmethod
    def validate_data_usage(cls, v):
        if v is not None and not isinstance(v, list):
            raise ValueError("data_usage must be a list")
        return v

class ProfileResponse(BaseModel):
    user_id: str
    email: str
    codename: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    company: Optional[str]
    job_role: Optional[str]
    data_usage: Optional[list[str]]
    role: str
    is_active: bool
    created_at: str
    last_login_at: Optional[str]
    api_key_preview: str
    notify_list_changes: Optional[bool] = None
    notify_status_changes: Optional[bool] = None
    last_notification_at: Optional[str] = None

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
    # Generate CAPTCHA token
    captcha_token, captcha_hash = generate_captcha_token()
    
    response = templates.TemplateResponse("auth/login.html", {
        "request": request,
        "user_authenticated": request.state.user_authenticated,
        "user_email": request.state.user_email,
        "user_display_name": request.state.user_display_name,
        "captcha_token": captcha_token
    })
    
    # Set CAPTCHA cookie
    set_captcha_cookie(response, captcha_hash)
    
    return response

@router.get("/signup")
@limiter.limit(rate_max)
async def signup_page(request: Request):
    """Display signup form"""
    # Generate CAPTCHA token
    captcha_token, captcha_hash = generate_captcha_token()
    
    response = templates.TemplateResponse("auth/signup.html", {
        "request": request,
        "user_authenticated": request.state.user_authenticated,
        "user_email": request.state.user_email,
        "user_display_name": request.state.user_display_name,
        "captcha_token": captcha_token
    })
    
    # Set CAPTCHA cookie
    set_captcha_cookie(response, captcha_hash)
    
    return response

@router.get("/set_password")
@limiter.limit(rate_max)
async def set_password_page(
    request: Request,
    user_id: str = Query(...)
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
    # Generate CAPTCHA token
    captcha_token, captcha_hash = generate_captcha_token()
    
    response = templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "captcha_token": captcha_token
    })
    
    # Set CAPTCHA cookie
    set_captcha_cookie(response, captcha_hash)
    
    return response

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
    
    # Generate CAPTCHA token
    captcha_token, captcha_hash = generate_captcha_token()
    
    response = templates.TemplateResponse(
        "auth/reset_password.html",
        {
            "request": request,
            "token": token,
            "email": user['email'],
            "captcha_token": captcha_token
        }
    )
    
    # Set CAPTCHA cookie
    set_captcha_cookie(response, captcha_hash)
    
    return response

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
        # Validate CAPTCHA first
        if ( captcha_enforce):
            is_valid, error_message = validate_captcha(
                request,
                register_req.captcha_token,
                register_req.captcha_checked
            )
            
            if not is_valid:
                return render_error(
                    request, "auth/register_error.html",
                    status.HTTP_400_BAD_REQUEST,
                    error_message
                )
        
        email = register_req.email
        existing_user = get_user_by_email(email)
        
        if existing_user and existing_user['is_active']:
            return render_error(
                request, "auth/register_error.html",
                status.HTTP_400_BAD_REQUEST,
                "Email already registered"
            )
        
        if existing_user:
            # Resend activation
            send_activation_email(email, existing_user['activation_token'])
            return render_or_json(
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
        
        return render_or_json(
            request, "auth/register_success.html",
            {"message": "Registration successful", "email": email, "user_id": str(user_id)}
        )
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return render_error(
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
            return render_error(
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
        return render_error(
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
            return render_error(
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
        
        return render_or_json(
            request, "auth/set_password_success.html",
            {"message": "Password set successfully", "login_link": "/v1/auth/login"}
        )
        
    except Exception as e:
        logger.error(f"Set password error: {str(e)}")
        return render_error(
            request, "auth/set_password_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.post("/login")
@limiter.limit(rate_max)
async def login(request: Request, login_req: LoginRequest):
    """Login with email/password"""
    try:
        # Validate CAPTCHA first
        if ( captcha_enforce):
            is_valid, error_message = validate_captcha(
                request,
                login_req.captcha_token,
                login_req.captcha_checked
            )
            
            if not is_valid:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, error_message)
        
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
        access_token = create_access_token(
            user_id=str(user['user_id']), 
            role=user_role,
            email=user['email'],
            codename=user.get('codename')
            )

        # Create response with cookie
        response_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            "role": user_role.value,
            "redirect_url": request.url.scheme + "://" + request.client.host + ":8000" + "/v1/auth/profile"
        }
        
        response = JSONResponse(content=response_data)
        
        # Set httpOnly cookie for server-side authentication
        response.set_cookie(
            key="auth_token",
            value=access_token,
            httponly=True,  # Prevents JavaScript access for security
            max_age=int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
        
        # Clear CAPTCHA cookie after successful login
        clear_captcha_cookie(response)
        
        return response
        
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
        # Validate CAPTCHA first
        if ( captcha_enforce):
            is_valid, error_message = validate_captcha(
                request,
                forgot_req.captcha_token,
                forgot_req.captcha_checked
            )
            
            if not is_valid:
                return render_error(
                    request, "auth/forgot_password_error.html",
                    status.HTTP_400_BAD_REQUEST,
                    error_message
                )
        
        user = get_user_by_email(forgot_req.email)
        
        # Always return success (prevent enumeration)
        if not user or not user['is_active']:
            return render_or_json(
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
        
        return render_or_json(
            request, "auth/forgot_password_success.html",
            {"message": "Reset email sent", "email": forgot_req.email}
        )
        
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        return render_error(
            request, "auth/forgot_password_error.html",
            status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)
        )

@router.post("/reset_password")
@limiter.limit(rate_max)
async def reset_password(request: Request, reset_req: ResetPasswordRequest):
    """Reset password with token"""
    try:
        # Validate CAPTCHA first
        if ( captcha_enforce):
            is_valid, error_message = validate_captcha(
                request,
                reset_req.captcha_token,
                reset_req.captcha_checked
            )
            
            if not is_valid:
                return render_error(
                    request, "auth/reset_password_error.html",
                    status.HTTP_400_BAD_REQUEST,
                    error_message
                )
        
        user = get_user_by_reset_token(reset_req.token)
        
        if not user:
            return render_error(
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
        
        return render_or_json(
            request, "auth/reset_password_success.html",
            {"message": "Password reset successful", "login_link": "/v1/auth/login"}
        )
        
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}")
        return render_error(
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
        
        return render_or_json(
            request, "auth/change_password_success.html",
            {"message": "Password changed successfully"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to change password")

@router.get("/logout")
@limiter.limit(rate_max)
async def logout_page(request: Request):
    """Logout - clears authentication cookie and redirects to home"""
    # Create redirect response to home page
    response = RedirectResponse(url="/v1/auth/login", status_code=303)
    
    # Clear the auth_token cookie
    response.delete_cookie(
        key="auth_token",
        path="/",
        samesite="lax"
    )
    
    return response

# ====================================================================
# PROFILE ENDPOINTS
# ====================================================================

@router.get("/profile")
@limiter.limit(rate_max)
async def profile_page(
    request: Request, 
    current_user: Optional[dict] = Depends(require_browser_auth(UserRole.BASIC))
):
    """Display user profile page with current data"""
    # If not authenticated, redirect to login page
    if not current_user:
        return RedirectResponse(url="/v1/auth/login", status_code=303)
    
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            return RedirectResponse(url="/v1/auth/login", status_code=303)
        
        # Parse data_usage JSON if exists
        data_usage = []
        if user.get('data_usage'):
            import json
            try:
                data_usage = json.loads(user['data_usage'])
            except:
                data_usage = []
        
        # Create API key preview (first 8 and last 4 chars)
        api_key_preview = "No API key set"
        if user.get('api_key_hash'):
            api_key_preview = "sk_..." + "x" * 24 + "..."
        
        # Job roles list
        job_roles = [
            "Background Check Specialist",
            "Compliance Officer",
            "Data Analyst/Scientist",
            "Human Resources Professional",
            "Journalist/Reporter",
            "Law Enforcement Officer",
            "Legal Professional/Attorney",
            "Private Investigator",
            "Public Safety Official",
            "Researcher/Academic",
            "Risk Analyst",
            "Security Professional",
            "Software Developer",
            "Other"
            ]
        
        # Data usage options
        data_usage_options = [
            "Analytics/Data Science",
            "Background Screening",
            "Compliance/Regulatory",
            "Due Diligence",
            "Journalism/Reporting",
            "Law Enforcement",
            "Public Safety Awareness",
            "Research/Academic Study",
            "Security/Risk Assessment",
            "Software Development/Integration",
            "Other"
            ]
        
        return templates.TemplateResponse("auth/profile.html", {
            "request": request,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user": user,
            "data_usage": data_usage,
            "job_roles": job_roles,
            "data_usage_options": data_usage_options,
            "api_key_preview": api_key_preview
        })
        
    except Exception as e:
        logger.error(f"Profile page error: {str(e)}")
        return RedirectResponse(url="/v1/auth/login", status_code=303)

@router.get("/profile/data", response_model=ProfileResponse)
@limiter.limit(rate_max)
async def get_profile_data(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
    ):
    """Get user profile data as JSON"""
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        
        # Parse data_usage JSON
        data_usage = []
        if user.get('data_usage'):
            import json
            try:
                data_usage = json.loads(user['data_usage'])
            except:
                data_usage = []
        
        # Create API key preview
        api_key_preview = "No API key"
        if user.get('api_key_hash'):
            api_key_preview = "sk_...xxxx" 
        
        return ProfileResponse(
            user_id=str(user['user_id']),
            email=user['email'],
            codename=user.get('codename'),
            first_name=user.get('first_name'),
            last_name=user.get('last_name'),
            company=user.get('company'),
            job_role=user.get('job_role'),
            data_usage=data_usage,
            role=user['role'],
            is_active=user['is_active'],
            created_at=user['created_at'].isoformat() if user.get('created_at') else None,
            last_login_at=user['last_login_at'].isoformat() if user.get('last_login_at') else None,
            api_key_preview=api_key_preview
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile data error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to get profile")

@router.put("/profile")
@limiter.limit(rate_max)
async def update_profile(
    request: Request,
    profile_update: ProfileUpdateRequest,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """Update user profile"""
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        
        # Check if email is being changed and if it's already taken
        if profile_update.email and profile_update.email != user['email']:
            existing_user = get_user_by_email(profile_update.email)
            if existing_user:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already in use")
        
        # Build update query dynamically based on provided fields
        update_fields = []
        update_values = []
        
        if profile_update.email is not None:
            update_fields.append("email = %s")
            update_values.append(profile_update.email)
        
        # Handle codename - allow setting to empty string to clear it
        if 'codename' in profile_update.model_fields_set:
            update_fields.append("codename = %s")
            update_values.append(profile_update.codename if profile_update.codename else None)
        
        if profile_update.first_name is not None:
            update_fields.append("first_name = %s")
            update_values.append(profile_update.first_name if profile_update.first_name else None)
        
        if profile_update.last_name is not None:
            update_fields.append("last_name = %s")
            update_values.append(profile_update.last_name if profile_update.last_name else None)
        
        if profile_update.company is not None:
            update_fields.append("company = %s")
            update_values.append(profile_update.company if profile_update.company else None)
        
        if profile_update.job_role is not None:
            update_fields.append("job_role = %s")
            update_values.append(profile_update.job_role if profile_update.job_role else None)
        
        if profile_update.data_usage is not None:
            import json
            update_fields.append("data_usage = %s")
            update_values.append(json.dumps(profile_update.data_usage) if profile_update.data_usage else None)

        if profile_update.notify_list_changes is not None:
            if user.get('role') == 'premium':
                update_fields.append("notify_list_changes = %s")
                update_values.append(profile_update.notify_list_changes)
        
        if profile_update.notify_status_changes is not None:
            if user.get('role') == 'premium':
                update_fields.append("notify_status_changes = %s")
                update_values.append(profile_update.notify_status_changes)

        if not update_fields:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
        
        # Always update updated_at
        update_fields.append("updated_at = NOW()")
        update_values.append(user['user_id'])

        # Execute update
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query = f"""
                    UPDATE tbl_users
                    SET {', '.join(update_fields)}
                    WHERE user_id = %s
                """
                cur.execute(query, update_values)
                conn.commit()
        
        logger.info(f"Profile updated: {user['email']}")
        
        # Determine the new values for token refresh
        # Use updated values if provided, otherwise keep existing
        new_email = profile_update.email if profile_update.email is not None else user['email']
        new_codename = profile_update.codename if 'codename' in profile_update.model_fields_set else user.get('codename')
        
        # Create a new JWT token with updated user info
        user_role = UserRole(user['role'])
        new_access_token = create_access_token(
            user_id=str(user['user_id']),
            role=user_role,
            email=new_email,
            codename=new_codename
            )
        
        # Build response with refreshed token cookie
        response_data = {
            "message": "Profile updated successfully",
            "updated_fields": [field.split(' = ')[0] for field in update_fields if field != "updated_at = NOW()"]
            }
        
        response = JSONResponse(content=response_data)
        
        # Set new auth_token cookie with updated claims
        response.set_cookie(
            key="auth_token",
            value=new_access_token,
            httponly=True,
            max_age=int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update profile")

# ====================================================================
# API KEY ENDPOINTS
# ====================================================================

@router.post("/reset_key")
@limiter.limit("3/hour")  # Rate limit to prevent abuse
async def reset_api_key(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Reset user's API key - generates new key and emails it to user.
    Invalidates all existing tokens generated from old API key.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        
        # Generate new API key
        api_key, api_key_hash = generate_api_key_and_hash()
        
        # Update database with new API key hash
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tbl_users
                       SET api_key_hash = %s, updated_at = NOW()
                       WHERE user_id = %s""",
                    (api_key_hash, user['user_id'])
                )
                conn.commit()
        
        logger.info(f"API key reset: {user['email']}")
        
        # Email new API key to user
        send_api_key_email(user['email'], api_key)
        
        return {
            "message": "API key reset successfully. Check your email for the new key.",
            "email": user['email']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset API key error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to reset API key")

@router.post("/token", response_model=TokenResponse)
@limiter.limit(rate_max)
async def get_token(request: Request, token_req: TokenRequest):
    """Generate JWT from API key"""
    try:
        # api_key = token_req.get('api_key')
        api_key = token_req.api_key
        
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
        access_token = create_access_token(
            user_id=str(user['user_id']), 
            role=user_role,
            email=user['email'],
            codename=user.get('codename')
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=int(API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            role=user_role.value,
            redirect_url="/v1/auth/profile"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token generation error: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to generate token")