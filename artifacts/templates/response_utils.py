"""
Response Utilities
Helpers for content negotiation (HTML vs JSON) and template rendering
"""
from typing import Any, Dict, Union
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")


def wants_json(request: Request) -> bool:
    """
    Determine if client wants JSON response based on Accept header.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        bool: True if client prefers JSON, False otherwise
    
    Logic:
        - If Accept header contains 'application/json': return JSON
        - If Accept header contains 'text/html': return HTML  
        - Default: return HTML (web browsers)
    """
    accept = request.headers.get('accept', '')
    
    # Check if JSON is explicitly requested
    if 'application/json' in accept:
        # If both HTML and JSON are accepted, check which comes first
        if 'text/html' in accept:
            json_pos = accept.index('application/json')
            html_pos = accept.index('text/html')
            return json_pos < html_pos
        return True
    
    # Default to HTML for browsers and unknown clients
    return False


def render_or_json(
    request: Request,
    template_name: str,
    context: Dict[str, Any],
    json_data: Dict[str, Any],
    status_code: int = 200
) -> Union[HTMLResponse, JSONResponse]:
    """
    Return either HTML template or JSON based on Accept header.
    
    Args:
        request: FastAPI Request object
        template_name: Path to Jinja2 template (e.g., "auth/activate_success.html")
        context: Context dict for template rendering
        json_data: Data dict for JSON response
        status_code: HTTP status code (default: 200)
    
    Returns:
        HTMLResponse or JSONResponse based on content negotiation
    
    Example:
        return render_or_json(
            request=request,
            template_name="auth/activate_success.html",
            context={"request": request, "api_key": api_key},
            json_data={"message": "Success", "api_key": api_key}
        )
    """
    if wants_json(request):
        return JSONResponse(content=json_data, status_code=status_code)
    else:
        # Ensure request is in context for Jinja2
        if 'request' not in context:
            context['request'] = request
        return templates.TemplateResponse(template_name, context, status_code=status_code)


def render_error(
    request: Request,
    template_name: str,
    error_message: str,
    error_type: str = "Error",
    context: Dict[str, Any] = None,
    status_code: int = 400
) -> Union[HTMLResponse, JSONResponse]:
    """
    Return error response as either HTML template or JSON based on Accept header.
    
    Args:
        request: FastAPI Request object
        template_name: Path to error template (e.g., "auth/activate_error.html")
        error_message: Error message to display
        error_type: Error type/title for the error page
        context: Additional context for template (optional)
        status_code: HTTP status code (default: 400)
    
    Returns:
        HTMLResponse or JSONResponse based on content negotiation
    
    Example:
        return render_error(
            request=request,
            template_name="auth/activate_error.html",
            error_message="Token has expired",
            error_type="Invalid or expired activation token",
            status_code=404
        )
    """
    # Build JSON response
    json_data = {
        "error": error_type,
        "detail": error_message,
        "status_code": status_code
    }
    
    # Build template context
    template_context = {
        "request": request,
        "error_message": error_message,
        "error_type": error_type,
        **(context or {})
    }
    
    if wants_json(request):
        return JSONResponse(content=json_data, status_code=status_code)
    else:
        return templates.TemplateResponse(template_name, template_context, status_code=status_code)
