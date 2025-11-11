"""
Content Negotiation Utilities
Helps determine whether to return HTML or JSON based on request headers
"""

from fastapi import Request
from typing import Literal

def get_response_format(request: Request, default: Literal["html", "json"] = "html") -> Literal["html", "json"]:
    """
    Determine response format based on Accept header.
    
    Args:
        request: FastAPI Request object
        default: Default format if no preference specified
        
    Returns:
        "html" or "json"
        
    Logic:
        - If Accept header contains "text/html" → HTML
        - If Accept header contains "application/json" → JSON
        - If Accept header is "*/*" or missing → use default
    """
    accept_header = request.headers.get("accept", "").lower()
    
    # Explicit JSON request
    if "application/json" in accept_header and "text/html" not in accept_header:
        return "json"
    
    # Explicit HTML request
    if "text/html" in accept_header and "application/json" not in accept_header:
        return "html"
    
    # Wildcard or no preference - use default
    return default

def wants_json(request: Request) -> bool:
    """Check if request wants JSON response"""
    return get_response_format(request) == "json"

def wants_html(request: Request) -> bool:
    """Check if request wants HTML response"""
    return get_response_format(request) == "html"
