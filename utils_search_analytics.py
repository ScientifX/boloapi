"""
Search Analytics Helper
Functions to log search analytics from endpoint handlers
"""

import json
import logging, time
from typing import Dict, Any, Optional
from functools import wraps
import psycopg2
from config import DB_CONFIG
from contextlib import contextmanager
from fastapi import Request

logger = logging.getLogger(__name__)

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


def log_search_analytics(
    user_id: str,
    endpoint: str,
    http_method: str,
    query_params: dict,
    results_count: int,
    response_format: str = "json",
    response_time_ms: int = 0,
    status_code: int = 200,
    user_role: str = None,
    billing_cycle: str = None,
    search_type: str = None,
    search_fields: dict = None,
    filters_applied: dict = None,
    ip_address: str = None,
    user_agent: str = None,
    referer: str = None
):
    """
    Log search analytics directly from endpoint handler.
    
    This is an alternative to using middleware - can be called directly
    from each search endpoint for more precise control.
    
    Args:
        user_id: UUID of the user making the request
        endpoint: The API endpoint path
        http_method: HTTP method (GET, POST, etc.)
        query_params: Dictionary of query parameters
        results_count: Number of results returned
        response_format: Format of the response (json, csv, txt, xml)
        response_time_ms: Response time in milliseconds
        status_code: HTTP status code
        user_role: User's role (BASIC, PREMIUM, ADMIN)
        billing_cycle: User's billing cycle (monthly, annual)
        search_type: Type of search (simple, advanced, category, list)
        search_fields: Dictionary of fields being searched
        filters_applied: Dictionary of filters used
        ip_address: Client IP address
        user_agent: Client user agent string
        referer: Referer header
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get current UTC timestamp explicitly
                from datetime import datetime, timezone
                utc_now = datetime.now(timezone.utc)
                
                cur.execute("""
                    INSERT INTO base.tbl_search_analytics (
                        user_id,
                        endpoint,
                        http_method,
                        query_params,
                        search_type,
                        search_fields,
                        filters_applied,
                        results_count,
                        response_format,
                        response_time_ms,
                        status_code,
                        user_role,
                        billing_cycle,
                        ip_address,
                        user_agent,
                        referer,
                        request_timestamp
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    user_id,
                    endpoint,
                    http_method,
                    json.dumps(query_params) if query_params else None,
                    search_type,
                    json.dumps(search_fields) if search_fields else None,
                    json.dumps(filters_applied) if filters_applied else None,
                    results_count,
                    response_format,
                    response_time_ms,
                    status_code,
                    user_role,
                    billing_cycle,
                    ip_address,
                    user_agent[:500] if user_agent else None,
                    referer[:500] if referer else None,
                    utc_now
                ))
                conn.commit()
                
    except Exception as e:
        logger.error(f"Failed to log search analytics: {str(e)}")
        # Don't raise - we don't want to fail the request if logging fails


def extract_search_info(query_params: dict) -> tuple:
    """
    Extract search fields and filters from query parameters.
    
    Returns:
        (search_fields, filters_applied) tuple
    """
    search_fields = {}
    filters_applied = {}
    
    for key, value in query_params.items():
        if key in ["limit", "page", "format"]:
            continue  # These are pagination/format params
        elif key == "field":
            search_fields["field"] = value
        elif key == "operator":
            filters_applied["operator"] = value
        elif key == "value":
            filters_applied["value"] = value
        elif key == "criteria":
            # Advanced search criteria
            try:
                criteria = json.loads(value) if isinstance(value, str) else value
                search_fields["criteria"] = criteria
            except:
                search_fields["criteria"] = value
        else:
            # Any other param is likely a filter
            filters_applied[key] = value
    
    return search_fields, filters_applied


def determine_search_type(endpoint: str) -> str:
    """Determine the search type based on the endpoint"""
    if "/simple" in endpoint:
        return "simple"
    elif "/advanced" in endpoint:
        return "advanced"
    elif "/category_" in endpoint:
        return "category"
    elif "/list_" in endpoint:
        return "list"
    else:
        return "other"

def track_search_analytics(func):
    """Decorator to automatically log search analytics"""
    @wraps(func)
    async def wrapper(request: Request, *args, current_user: dict, **kwargs):
        start_time = time.time()
        
        # CAPTURE REQUEST BODY for POST requests
        request_body = None
        if request.method == "POST":
            try:
                # Check common parameter names for request body
                for param_name in ['body', 'data', 'search_data', 'search_request', 'criteria', 'filters']:
                    if param_name in kwargs:
                        request_body = kwargs[param_name]
                        break
                
                # Convert Pydantic model to dict if needed
                if request_body:
                    if hasattr(request_body, 'dict'):
                        request_body = request_body.dict()
                    elif hasattr(request_body, 'model_dump'):
                        request_body = request_body.model_dump()
            except Exception as e:
                logger.warning(f"Could not capture request body: {e}")
        
        # Call the original endpoint function
        response = await func(request, *args, current_user=current_user, **kwargs)
        
        # Extract results count
        results_count = 0
        if isinstance(response, dict) and 'resultcount' in response:
            results_count = response['resultcount']
        
        # CAPTURE BOTH query params AND request body separately
        query_params = dict(request.query_params)
        
        # Store request body in search_fields for better organization
        search_fields = {}
        filters_applied = {}
        
        if request_body:
            # Put the full request body in search_fields
            search_fields = request_body.copy() if isinstance(request_body, dict) else {}
        
        # Also extract from query params
        query_search_fields, query_filters = extract_search_info(query_params)
        
        # Merge them (request body takes precedence)
        search_fields.update(query_search_fields)
        filters_applied.update(query_filters)
        
        # Log analytics
        try:
            log_search_analytics(
                user_id=current_user["user_id"],
                endpoint=request.url.path,
                http_method=request.method,
                query_params=query_params,  # URL query string only
                results_count=results_count,
                response_format=query_params.get("format", "json"),
                response_time_ms=int((time.time() - start_time) * 1000),
                status_code=200,
                user_role=current_user.get("role"),
                billing_cycle=current_user.get("billing_cycle"),
                search_type=determine_search_type(request.url.path),
                search_fields=search_fields,  # Request body goes here
                filters_applied=filters_applied,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                referer=request.headers.get("referer")
            )
        except Exception as e:
            logger.error(f"Analytics logging failed: {e}")
        
        return response
    return wrapper

