"""
Authentication Middleware for Template Rendering
Checks JWT cookie and sets user_authenticated state for Jinja2 templates
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from utils_jwt import decode_access_token, JWTError, resolve_display_name
from config import DB_CONFIG


@contextmanager
def get_db_connection():
    """Database connection context manager"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


class TemplateAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that checks for JWT in cookies and sets authentication state
    for template rendering. This allows Jinja2 templates to use server-side
    logic to show/hide content based on authentication.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check for JWT token in cookies
        token = request.cookies.get('auth_token')
        
        # Default to not authenticated
        request.state.user_authenticated = False
        request.state.user_email = None
        request.state.user_role = None
        request.state.user_id = None
        request.state.user_codename = None
        request.state.user_display_name = None  # codename > full name > email prefix
        
        if token:
            try:
                # Decode and validate the token
                payload = decode_access_token(token)
                
                # Extract user information from token
                user_id = payload.get("sub")
                role = payload.get("role")
                email = payload.get("email") 
                codename = payload.get("codename")
                first_name = payload.get("first_name")
                last_name = payload.get("last_name")
                
                if user_id and role:
                    # CRITICAL: Check database to ensure user is still active
                    # This prevents disabled users from seeing authenticated UI
                    try:
                        with get_db_connection() as conn:
                            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                                cur.execute(
                                    "SELECT is_active FROM base.tbl_users WHERE user_id = %s",
                                    (user_id,)
                                )
                                user_record = cur.fetchone()
                                
                                # Only set as authenticated if user exists and is active
                                if user_record and user_record['is_active']:
                                    request.state.user_authenticated = True
                                    request.state.user_id = user_id
                                    request.state.user_role = role
                                    request.state.user_email = email
                                    request.state.user_codename = codename
                                    # Priority: codename > first/last name > email prefix
                                    display = resolve_display_name(codename, first_name, last_name)
                                    if display:
                                        request.state.user_display_name = display
                                    elif email:
                                        request.state.user_display_name = email.split('@')[0]
                                    else:
                                        request.state.user_display_name = None
                    except Exception:
                        # Database error - treat as unauthenticated
                        pass
                    
            except JWTError:
                # Token is invalid or expired - remain unauthenticated
                pass
        
        response = await call_next(request)
        return response
