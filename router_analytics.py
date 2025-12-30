"""
Analytics Router
Provides endpoints for users and admins to view search analytics
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Request, Depends, Query, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from auth import UserRole
from auth_jwt import require_jwt_role

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rate_max = "100/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# FastAPI Router
router = APIRouter(prefix="/v1/analytics")

# Tags for Swagger UI organization
TAG_ANALYTICS = "Analytics"

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


class TimeRange(str, Enum):
    """Time range options for analytics queries"""
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    ALL_TIME = "all_time"


def get_date_range(time_range: TimeRange) -> tuple:
    """
    Convert TimeRange enum to start and end datetime objects.
    Returns (start_date, end_date) tuple.
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if time_range == TimeRange.TODAY:
        return today_start, now
    
    elif time_range == TimeRange.YESTERDAY:
        yesterday = today_start - timedelta(days=1)
        return yesterday, today_start
    
    elif time_range == TimeRange.LAST_7_DAYS:
        return today_start - timedelta(days=7), now
    
    elif time_range == TimeRange.LAST_30_DAYS:
        return today_start - timedelta(days=30), now
    
    elif time_range == TimeRange.LAST_90_DAYS:
        return today_start - timedelta(days=90), now
    
    elif time_range == TimeRange.THIS_MONTH:
        month_start = today_start.replace(day=1)
        return month_start, now
    
    elif time_range == TimeRange.LAST_MONTH:
        first_of_this_month = today_start.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return last_month_start, first_of_this_month
    
    else:  # ALL_TIME
        return datetime(2020, 1, 1), now


# ============================================================================
# USER ANALYTICS ENDPOINTS
# ============================================================================

@router.get(
    "/my_searches",
    tags=[TAG_ANALYTICS],
    summary="My Search History",
    description="""
    View your own search history with details about each request.
    
    **Access:** BASIC, PREMIUM, ADMIN
    
    Returns recent searches with timestamps, endpoints used, and results counts.
    """
)
@limiter.limit(rate_max)
async def get_my_searches(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of records to return"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get the authenticated user's search history.
    
    Returns:
    - List of searches with timestamps, endpoints, parameters, and results
    - Pagination info
    - Summary statistics
    """
    user_id = current_user["user_id"]
    start_date, end_date = get_date_range(time_range)
    offset = (page - 1) * limit
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get total count
                cur.execute("""
                    SELECT COUNT(*) as total
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                """, (user_id, start_date, end_date))
                
                total = cur.fetchone()["total"]
                
                # Get paginated results
                cur.execute("""
                    SELECT 
                        analytics_id,
                        endpoint,
                        http_method,
                        query_params,
                        search_type,
                        results_count,
                        response_format,
                        response_time_ms,
                        status_code,
                        request_timestamp
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    ORDER BY request_timestamp DESC
                    LIMIT %s OFFSET %s
                """, (user_id, start_date, end_date, limit, offset))
                
                searches = cur.fetchall()
                
                # Get summary statistics
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        SUM(results_count) as total_results,
                        AVG(response_time_ms) as avg_response_time,
                        COUNT(DISTINCT DATE(request_timestamp)) as active_days,
                        COUNT(DISTINCT search_type) as search_types_used
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                """, (user_id, start_date, end_date))
                
                summary = cur.fetchone()
                
                return {
                    "searches": searches,
                    "pagination": {
                        "total": total,
                        "page": page,
                        "limit": limit,
                        "pages": (total + limit - 1) // limit
                    },
                    "summary": {
                        "total_searches": summary["total_searches"],
                        "total_results": summary["total_results"],
                        "avg_response_time_ms": round(summary["avg_response_time"], 2) if summary["avg_response_time"] else 0,
                        "active_days": summary["active_days"],
                        "search_types_used": summary["search_types_used"]
                    },
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching user analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving analytics: {str(e)}"
        )


@router.get(
    "/my_stats",
    tags=[TAG_ANALYTICS],
    summary="My Usage Statistics",
    description="""
    Get summarized statistics about your API usage.
    
    **Access:** BASIC, PREMIUM, ADMIN
    
    Returns aggregated statistics including most used endpoints, popular search types, and usage trends.
    """
)
@limiter.limit(rate_max)
async def get_my_stats(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_30_DAYS, description="Time range for statistics"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get aggregated statistics for the authenticated user.
    
    Returns:
    - Total searches and results
    - Most used endpoints
    - Popular search types
    - Format preferences
    - Daily activity patterns
    - Performance metrics
    """
    user_id = current_user["user_id"]
    start_date, end_date = get_date_range(time_range)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Overall stats
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        SUM(results_count) as total_results,
                        AVG(response_time_ms) as avg_response_time,
                        MIN(response_time_ms) as min_response_time,
                        MAX(response_time_ms) as max_response_time,
                        COUNT(DISTINCT DATE(request_timestamp)) as active_days
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                """, (user_id, start_date, end_date))
                
                overall = cur.fetchone()
                
                # Top endpoints
                cur.execute("""
                    SELECT 
                        endpoint,
                        COUNT(*) as count,
                        AVG(response_time_ms) as avg_response_time
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY endpoint
                    ORDER BY count DESC
                    LIMIT 10
                """, (user_id, start_date, end_date))
                
                top_endpoints = cur.fetchall()
                
                # Search types breakdown
                cur.execute("""
                    SELECT 
                        search_type,
                        COUNT(*) as count,
                        SUM(results_count) as total_results
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY search_type
                    ORDER BY count DESC
                """, (user_id, start_date, end_date))
                
                search_types = cur.fetchall()
                
                # Format preferences
                cur.execute("""
                    SELECT 
                        response_format,
                        COUNT(*) as count
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY response_format
                    ORDER BY count DESC
                """, (user_id, start_date, end_date))
                
                formats = cur.fetchall()
                
                # Daily activity (last 30 days max for chart)
                chart_start = max(start_date, end_date - timedelta(days=30))
                cur.execute("""
                    SELECT 
                        DATE(request_timestamp) as date,
                        COUNT(*) as searches,
                        SUM(results_count) as results
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY DATE(request_timestamp)
                    ORDER BY date DESC
                """, (user_id, chart_start, end_date))
                
                daily_activity = cur.fetchall()
                
                return {
                    "overall": {
                        "total_searches": overall["total_searches"],
                        "total_results": overall["total_results"],
                        "avg_response_time_ms": round(overall["avg_response_time"], 2) if overall["avg_response_time"] else 0,
                        "min_response_time_ms": overall["min_response_time"],
                        "max_response_time_ms": overall["max_response_time"],
                        "active_days": overall["active_days"]
                    },
                    "top_endpoints": top_endpoints,
                    "search_types": search_types,
                    "format_preferences": formats,
                    "daily_activity": daily_activity,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching user stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving statistics: {str(e)}"
        )


# ============================================================================
# ADMIN ANALYTICS ENDPOINTS
# ============================================================================

@router.get(
    "/admin/overview",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] System Analytics Overview",
    description="""
    Get system-wide analytics overview.
    
    **Access:** ADMIN only
    
    Returns aggregated statistics across all users.
    """
)
@limiter.limit(rate_max)
async def get_admin_overview(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_30_DAYS, description="Time range for analytics"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get system-wide analytics overview (admin only).
    
    Returns:
    - Total searches and results
    - Active users
    - Most popular endpoints
    - Usage by role
    - Performance metrics
    """
    start_date, end_date = get_date_range(time_range)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Overall system stats
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        COUNT(DISTINCT user_id) as active_users,
                        SUM(results_count) as total_results,
                        AVG(response_time_ms) as avg_response_time,
                        COUNT(DISTINCT DATE(request_timestamp)) as active_days
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                """, (start_date, end_date))
                
                overall = cur.fetchone()
                
                # Usage by role
                cur.execute("""
                    SELECT 
                        user_role,
                        COUNT(*) as searches,
                        COUNT(DISTINCT user_id) as users,
                        AVG(response_time_ms) as avg_response_time
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY user_role
                    ORDER BY searches DESC
                """, (start_date, end_date))
                
                by_role = cur.fetchall()
                
                # Top endpoints
                cur.execute("""
                    SELECT 
                        endpoint,
                        COUNT(*) as count,
                        COUNT(DISTINCT user_id) as unique_users,
                        AVG(response_time_ms) as avg_response_time
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY endpoint
                    ORDER BY count DESC
                    LIMIT 15
                """, (start_date, end_date))
                
                top_endpoints = cur.fetchall()
                
                # Search types
                cur.execute("""
                    SELECT 
                        search_type,
                        COUNT(*) as count,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY search_type
                    ORDER BY count DESC
                """, (start_date, end_date))
                
                search_types = cur.fetchall()
                
                # Daily trends
                cur.execute("""
                    SELECT 
                        DATE(request_timestamp) as date,
                        COUNT(*) as searches,
                        COUNT(DISTINCT user_id) as active_users,
                        SUM(results_count) as results
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY DATE(request_timestamp)
                    ORDER BY date DESC
                """, (start_date, end_date))
                
                daily_trends = cur.fetchall()
                
                return {
                    "overall": {
                        "total_searches": overall["total_searches"],
                        "active_users": overall["active_users"],
                        "total_results": overall["total_results"],
                        "avg_response_time_ms": round(overall["avg_response_time"], 2) if overall["avg_response_time"] else 0,
                        "active_days": overall["active_days"]
                    },
                    "by_role": by_role,
                    "top_endpoints": top_endpoints,
                    "search_types": search_types,
                    "daily_trends": daily_trends,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching admin analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving admin analytics: {str(e)}"
        )


@router.get(
    "/admin/users/{user_id}/searches",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] User Search History",
    description="""
    View search history for a specific user.
    
    **Access:** ADMIN only
    """
)
@limiter.limit(rate_max)
async def get_user_searches_admin(
    request: Request,
    user_id: str,
    time_range: TimeRange = Query(TimeRange.LAST_30_DAYS, description="Time range for analytics"),
    limit: int = Query(50, ge=1, le=500),
    page: int = Query(1, ge=1),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get search history for a specific user (admin only).
    
    Similar to /my_searches but allows admins to view any user's history.
    """
    start_date, end_date = get_date_range(time_range)
    offset = (page - 1) * limit
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Verify user exists
                cur.execute("SELECT email FROM base.tbl_users WHERE user_id = %s", (user_id,))
                user = cur.fetchone()
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User {user_id} not found"
                    )
                
                # Get total count
                cur.execute("""
                    SELECT COUNT(*) as total
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                """, (user_id, start_date, end_date))
                
                total = cur.fetchone()["total"]
                
                # Get paginated results
                cur.execute("""
                    SELECT 
                        analytics_id,
                        endpoint,
                        http_method,
                        query_params,
                        search_type,
                        results_count,
                        response_format,
                        response_time_ms,
                        status_code,
                        ip_address,
                        request_timestamp
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    ORDER BY request_timestamp DESC
                    LIMIT %s OFFSET %s
                """, (user_id, start_date, end_date, limit, offset))
                
                searches = cur.fetchall()
                
                return {
                    "user_email": user["email"],
                    "user_id": user_id,
                    "searches": searches,
                    "pagination": {
                        "total": total,
                        "page": page,
                        "limit": limit,
                        "pages": (total + limit - 1) // limit
                    },
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user searches (admin): {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user searches: {str(e)}"
        )
