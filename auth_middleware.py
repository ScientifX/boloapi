"""
Authentication Middleware for Template Rendering
Checks JWT cookie and sets user_authenticated state for Jinja2 templates
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from jwt_utils import decode_access_token, JWTError


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
        
        if token:
            try:
                # Decode and validate the token
                payload = decode_access_token(token)
                
                # Extract user information from token
                user_id = payload.get("sub")
                role = payload.get("role")
                
                if user_id and role:
                    request.state.user_authenticated = True
                    request.state.user_id = user_id
                    request.state.user_role = role
                    # Try to extract email from user_id if it's an email format
                    request.state.user_email = user_id if '@' in user_id else None
                    
            except JWTError:
                # Token is invalid or expired - remain unauthenticated
                pass
        
        response = await call_next(request)
        return response
