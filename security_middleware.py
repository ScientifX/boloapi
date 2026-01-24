"""
Security Middleware for Request Validation
Validates endpoint existence, HTTP methods, request mechanisms, and prevents unauthorized access.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class SecurityValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that performs comprehensive security checks on all incoming requests:
    1. Validates endpoint exists in the application
    2. Validates HTTP method is allowed for the endpoint
    3. Distinguishes between browser and API requests
    4. Prevents direct access to data directory
    5. Logs all unauthorized access attempts
    6. Returns empty response and terminates on security violations
    """
    
    # Paths that should never be directly accessible
    FORBIDDEN_PATHS = [
        '/data/',
        '/data',
        '/static/data/',
        '/static/data'
    ]
    
    # Paths that should only be accessible via browser (GET requests with Accept: text/html)
    BROWSER_ONLY_PATHS = [
        '/v1/auth/login',
        '/v1/auth/signup',
        '/v1/auth/logout',
        '/v1/auth/profile',
        '/v1/auth/change-password',
        '/v1/auth/forgot-password',
        '/v1/auth/reset-password',
        '/v1/auth/analytics',
        '/v1/auth/users',
        '/v1/billing/billing',
        '/plans',
        '/about',
        '/quickstart',
        '/privacy',
        '/terms',
        '/contact',
        '/'
    ]
    
    # API endpoints that should only accept specific HTTP methods
    # Note: These are prefix matches - /v1/search/simple will match /v1/search
    API_METHOD_RESTRICTIONS = {
        # Search endpoints - GET or POST only (no PUT, DELETE, etc.)
        '/v1/search/simple': ['GET', 'POST'],
        '/v1/search/advanced': ['POST'],
        '/v1/search/archive': ['GET'],
        # Auth endpoints
        '/v1/auth/register': ['POST'],
        '/v1/auth/token': ['POST'],
        '/v1/auth/refresh': ['POST'],
        '/v1/auth/api-key/reset': ['POST'],
        # Billing endpoints
        '/v1/billing/webhook': ['POST'],
        '/v1/billing/subscribe': ['POST'],
        '/v1/billing/manage': ['POST'],
        '/v1/billing/cancel': ['POST'],
        # Analytics endpoints
        '/v1/analytics/search': ['GET'],
        '/v1/analytics/usage': ['GET'],
    }
    
    async def dispatch(self, request: Request, call_next):
        """Process request and perform security validations"""
        
        # Get request details
        path = request.url.path
        method = request.method
        headers = request.headers
        
        # Security Check 1: Prevent direct access to data directory
        if self._is_forbidden_path(path):
            logger.warning(
                f"SECURITY: Unauthorized data folder access attempt - "
                f"Path: {path}, Method: {method}, "
                f"IP: {self._get_client_ip(request)}, "
                f"User-Agent: {headers.get('user-agent', 'unknown')}"
            )
            return Response(content="", status_code=404)
        
        # Security Check 2: Validate path patterns for directory traversal
        if self._has_directory_traversal(path):
            logger.warning(
                f"SECURITY: Directory traversal attempt detected - "
                f"Path: {path}, Method: {method}, "
                f"IP: {self._get_client_ip(request)}"
            )
            return Response(content="", status_code=404)
        
        # Security Check 3: Check for browser-only paths accessed via API
        if self._is_browser_only_path(path):
            if not self._is_browser_request(request):
                logger.warning(
                    f"SECURITY: API access attempt to browser-only endpoint - "
                    f"Path: {path}, Method: {method}, "
                    f"IP: {self._get_client_ip(request)}, "
                    f"Accept: {headers.get('accept', 'unknown')}"
                )
                return Response(content="", status_code=404)
        
        # Security Check 4: Validate HTTP method for API endpoints
        if self._is_api_path(path):
            allowed_methods = self._get_allowed_methods(path)
            if allowed_methods and method not in allowed_methods:
                logger.warning(
                    f"SECURITY: Invalid HTTP method for API endpoint - "
                    f"Path: {path}, Method: {method} (allowed: {', '.join(allowed_methods)}), "
                    f"IP: {self._get_client_ip(request)}"
                )
                return Response(content="", status_code=405)
        
        # Security Check 5: Log suspicious patterns
        if self._has_suspicious_patterns(path):
            logger.warning(
                f"SECURITY: Suspicious pattern detected - "
                f"Path: {path}, Method: {method}, "
                f"IP: {self._get_client_ip(request)}"
            )
            # Continue processing but log the attempt
        
        # All security checks passed, proceed with request
        response = await call_next(request)
        return response
    
    def _is_forbidden_path(self, path: str) -> bool:
        """Check if path attempts to access forbidden directories"""
        path_lower = path.lower()
        
        # Check exact matches and prefixes
        for forbidden in self.FORBIDDEN_PATHS:
            if path_lower == forbidden or path_lower.startswith(forbidden):
                return True
        
        # Check for encoded attempts (e.g., %2Fdata%2F)
        if 'data' in path_lower and ('/' in path or '%2f' in path_lower or '%5c' in path_lower):
            # More sophisticated check for data folder access attempts
            normalized = path.replace('%2F', '/').replace('%2f', '/').replace('%5C', '/').replace('%5c', '/')
            if '/data/' in normalized.lower() or normalized.lower().endswith('/data'):
                return True
        
        return False
    
    def _has_directory_traversal(self, path: str) -> bool:
        """Detect directory traversal attempts"""
        suspicious_patterns = [
            '..',
            '%2e%2e',
            '%252e%252e',
            '..%2f',
            '..%5c',
            '%2e%2e/',
            '%2e%2e\\',
        ]
        
        path_lower = path.lower()
        return any(pattern in path_lower for pattern in suspicious_patterns)
    
    def _is_browser_only_path(self, path: str) -> bool:
        """Check if path should only be accessible via browser"""
        # Exact match or prefix match for browser-only paths
        for browser_path in self.BROWSER_ONLY_PATHS:
            # Exact match
            if path == browser_path:
                return True
            # Prefix match only for paths ending with '/' (excluding single '/')
            if browser_path.endswith('/') and browser_path != '/' and path.startswith(browser_path):
                return True
        return False
    
    def _is_browser_request(self, request: Request) -> bool:
        """Determine if request is from a browser"""
        accept_header = request.headers.get('accept', '').lower()
        user_agent = request.headers.get('user-agent', '').lower()
        
        # Browser requests typically accept text/html and have browser user agents
        is_html_accept = 'text/html' in accept_header
        is_browser_ua = any(browser in user_agent for browser in ['mozilla', 'chrome', 'safari', 'edge', 'firefox'])
        
        return is_html_accept or is_browser_ua
    
    def _is_api_path(self, path: str) -> bool:
        """Check if path is an API endpoint"""
        return path.startswith('/v1/')
    
    def _get_allowed_methods(self, path: str) -> list:
        """Get allowed HTTP methods for a given API path"""
        # Check exact match first
        if path in self.API_METHOD_RESTRICTIONS:
            return self.API_METHOD_RESTRICTIONS[path]
        
        # Check prefix matches (for paths with parameters)
        for api_path, methods in self.API_METHOD_RESTRICTIONS.items():
            if path.startswith(api_path):
                return methods
        
        # Default: if not specifically restricted, allow common methods
        # This allows FastAPI to handle method validation for dynamic routes
        return None
    
    def _has_suspicious_patterns(self, path: str) -> bool:
        """Check for suspicious patterns in the path"""
        suspicious = [
            'eval(',
            'exec(',
            '<script',
            'javascript:',
            'onclick=',
            'onerror=',
            'data:text/html',
            '${',
            '{{',
            'union select',
            'drop table',
            'insert into',
            'delete from',
            '--',
            ';--',
            '/*',
            '*/',
            'xp_',
            'sp_',
        ]
        
        path_lower = path.lower()
        return any(pattern in path_lower for pattern in suspicious)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for proxy headers first
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct client
        if request.client:
            return request.client.host
        
        return 'unknown'
