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
# logging.basicConfig(level=logging.INFO)
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


def get_date_range(time_range: TimeRange, timezone_offset_minutes: int = 0) -> tuple:
    """
    Convert TimeRange enum to start and end datetime objects in UTC.
    
    Args:
        time_range: The time range enum value
        timezone_offset_minutes: User's timezone offset in minutes from UTC (negative for west, positive for east)
                                JavaScript's getTimezoneOffset() returns positive for west, negative for east,
                                so we negate it here to match standard UTC offset convention
    
    Returns:
        (start_date, end_date) tuple in UTC timezone
    """
    from datetime import timezone as dt_timezone
    
    # Convert timezone offset to timedelta (negate because JS returns opposite sign)
    user_tz = dt_timezone(timedelta(minutes=-timezone_offset_minutes))
    
    # Get current time in user's timezone
    now_user = datetime.now(user_tz)
    
    # Get start of today in user's timezone
    today_start_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if time_range == TimeRange.TODAY:
        start_user = today_start_user
        end_user = now_user
    
    elif time_range == TimeRange.YESTERDAY:
        yesterday_user = today_start_user - timedelta(days=1)
        start_user = yesterday_user
        end_user = today_start_user
    
    elif time_range == TimeRange.LAST_7_DAYS:
        start_user = today_start_user - timedelta(days=7)
        end_user = now_user
    
    elif time_range == TimeRange.LAST_30_DAYS:
        start_user = today_start_user - timedelta(days=30)
        end_user = now_user
    
    elif time_range == TimeRange.LAST_90_DAYS:
        start_user = today_start_user - timedelta(days=90)
        end_user = now_user
    
    elif time_range == TimeRange.THIS_MONTH:
        month_start_user = today_start_user.replace(day=1)
        start_user = month_start_user
        end_user = now_user
    
    elif time_range == TimeRange.LAST_MONTH:
        first_of_this_month_user = today_start_user.replace(day=1)
        last_month_end_user = first_of_this_month_user - timedelta(days=1)
        last_month_start_user = last_month_end_user.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_user = last_month_start_user
        end_user = first_of_this_month_user
    
    else:  # ALL_TIME
        start_user = datetime(2020, 1, 1, tzinfo=user_tz)
        end_user = now_user
    
    # Convert to UTC for database queries
    start_utc = start_user.astimezone(dt_timezone.utc).replace(tzinfo=None)
    end_utc = end_user.astimezone(dt_timezone.utc).replace(tzinfo=None)
    
    return start_utc, end_utc


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
    
    Returns up to 500 most recent searches with timestamps, endpoints used, and results counts.
    Timezone filtering is based on user's local timezone for accurate date range filtering.
    """
)
@limiter.limit(rate_max)
async def get_my_searches(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC (from JavaScript's getTimezoneOffset())"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get the authenticated user's search history (up to 500 most recent).
    
    Returns:
    - List of searches with timestamps, endpoints, parameters, and results
    - Summary statistics
    """
    user_id = current_user["user_id"]
    start_date, end_date = get_date_range(time_range, timezone_offset)
    limit = 500  # Fixed cap at 500 searches
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get results (limited to 500)
                cur.execute("""
                    SELECT 
                        analytics_id,
                        endpoint,
                        http_method,
                        query_params,
                        search_fields,
                        filters_applied,
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
                    LIMIT %s
                """, (user_id, start_date, end_date, limit))
                
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
    Timezone filtering is based on user's local timezone for accurate date range filtering.
    """
)
@limiter.limit(rate_max)
async def get_my_stats(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for statistics"),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC (from JavaScript's getTimezoneOffset())"),
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
    start_date, end_date = get_date_range(time_range, timezone_offset)
    
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
                # Convert UTC timestamps to user's timezone for accurate date grouping
                chart_start = max(start_date, end_date - timedelta(days=30))
                
                # Calculate timezone offset as minutes
                # JavaScript's getTimezoneOffset() is positive for west (behind UTC), negative for east
                # We need to subtract this offset from UTC to get local time
                # For PST (UTC-8), getTimezoneOffset() returns 480, so we subtract 480 minutes to get local time
                offset_minutes = -timezone_offset
                
                cur.execute("""
                    SELECT 
                        DATE(request_timestamp + (%s || ' minutes')::INTERVAL) as date,
                        COUNT(*) as searches,
                        SUM(results_count) as results
                    FROM base.tbl_search_analytics
                    WHERE user_id = %s
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY DATE(request_timestamp + (%s || ' minutes')::INTERVAL)
                    ORDER BY date DESC
                """, (offset_minutes, user_id, chart_start, end_date, offset_minutes))
                
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
    Timezone filtering is based on user's local timezone for accurate date range filtering.
    """
)
@limiter.limit(rate_max)
async def get_admin_overview(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_30_DAYS, description="Time range for analytics"),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC (from JavaScript's getTimezoneOffset())"),
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
    start_date, end_date = get_date_range(time_range, timezone_offset)
    
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
                
                # Activity trends with dynamic grouping based on time range
                # Convert UTC timestamps to user's timezone for accurate date grouping
                # JavaScript's getTimezoneOffset() is positive for west, negative for east
                # We subtract the offset to get local time
                offset_minutes = -timezone_offset
                
                # Determine grouping based on time range
                if time_range in [TimeRange.TODAY, TimeRange.LAST_7_DAYS]:
                    # Daily grouping
                    group_by_clause = "DATE(request_timestamp + (%s || ' minutes')::INTERVAL)"
                    date_label = "date"
                elif time_range in [TimeRange.LAST_30_DAYS]:
                    # Weekly grouping
                    group_by_clause = "DATE_TRUNC('week', request_timestamp + (%s || ' minutes')::INTERVAL)::DATE"
                    date_label = "week"
                elif time_range in [TimeRange.LAST_90_DAYS, TimeRange.THIS_MONTH, TimeRange.LAST_MONTH]:
                    # Monthly grouping
                    group_by_clause = "DATE_TRUNC('month', request_timestamp + (%s || ' minutes')::INTERVAL)::DATE"
                    date_label = "month"
                else:  # ALL_TIME
                    # Quarterly grouping
                    group_by_clause = "DATE_TRUNC('quarter', request_timestamp + (%s || ' minutes')::INTERVAL)::DATE"
                    date_label = "quarter"
                
                query = f"""
                    SELECT 
                        {group_by_clause} as date,
                        COUNT(*) as searches,
                        COUNT(DISTINCT user_id) as active_users,
                        SUM(results_count) as results
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY {group_by_clause}
                    ORDER BY date DESC
                """
                
                # Parameters: offset_minutes (SELECT), start_date, end_date, offset_minutes (GROUP BY)
                cur.execute(query, (offset_minutes, start_date, end_date, offset_minutes))
                
                activity_trends = cur.fetchall()
                
                return {
                    "overall": {
                        "total_searches": overall["total_searches"] or 0,
                        "active_users": overall["active_users"] or 0,
                        "total_results": overall["total_results"] or 0,
                        "avg_response_time_ms": round(overall["avg_response_time"], 2) if overall["avg_response_time"] else 0,
                        "active_days": overall["active_days"] or 0
                    },
                    "by_role": by_role,
                    "top_endpoints": top_endpoints,
                    "search_types": search_types,
                    "activity_trends": activity_trends,
                    "grouping": date_label,
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
    "/admin/top_users",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] Top Users by Search Count",
    description="""
    Get top users ranked by search count for site analytics.
    
    **Access:** ADMIN only
    """
)
@limiter.limit(rate_max)
async def get_top_users_admin(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    limit: int = Query(10, ge=1, le=50),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get top users by search count with user details.
    """
    start_date, end_date = get_date_range(time_range, timezone_offset)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        a.user_id,
                        COALESCE(u.codename, u.email) as user_name,
                        u.role as user_role,
                        COUNT(*) as search_count,
                        SUM(a.results_count) as total_results,
                        AVG(a.response_time_ms) as avg_response_time
                    FROM base.tbl_search_analytics a
                    LEFT JOIN base.tbl_users u ON a.user_id = u.user_id
                    WHERE a.request_timestamp >= %s
                        AND a.request_timestamp <= %s
                    GROUP BY a.user_id, u.codename, u.email, u.role
                    ORDER BY search_count DESC
                    LIMIT %s
                """, (start_date, end_date, limit))
                
                top_users = cur.fetchall()
                
                return {
                    "top_users": top_users,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching top users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving top users: {str(e)}"
        )


@router.get(
    "/admin/zero_result_endpoints",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] Endpoints with Most Zero Results",
    description="""
    Get endpoints that most frequently return zero results.
    
    **Access:** ADMIN only
    """
)
@limiter.limit(rate_max)
async def get_zero_result_endpoints_admin(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    limit: int = Query(10, ge=1, le=50),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get endpoints with the most zero-result searches.
    """
    start_date, end_date = get_date_range(time_range, timezone_offset)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        endpoint,
                        COUNT(*) as zero_result_count,
                        COUNT(DISTINCT user_id) as unique_users,
                        AVG(response_time_ms) as avg_response_time
                    FROM base.tbl_search_analytics
                    WHERE results_count = 0
                        AND request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY endpoint
                    ORDER BY zero_result_count DESC
                    LIMIT %s
                """, (start_date, end_date, limit))
                
                zero_result_endpoints = cur.fetchall()
                
                return {
                    "zero_result_endpoints": zero_result_endpoints,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching zero result endpoints: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving zero result endpoints: {str(e)}"
        )


@router.get(
    "/admin/endpoints_by_results",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] Top Endpoints by Results Returned",
    description="""
    Get endpoints that return the most results.
    
    **Access:** ADMIN only
    """
)
@limiter.limit(rate_max)
async def get_endpoints_by_results_admin(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    limit: int = Query(10, ge=1, le=50),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get endpoints ranked by total results returned.
    """
    start_date, end_date = get_date_range(time_range, timezone_offset)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        endpoint,
                        COUNT(*) as request_count,
                        SUM(results_count) as total_results,
                        AVG(results_count) as avg_results_per_request,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY endpoint
                    ORDER BY total_results DESC
                    LIMIT %s
                """, (start_date, end_date, limit))
                
                endpoints_by_results = cur.fetchall()
                
                return {
                    "endpoints_by_results": endpoints_by_results,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching endpoints by results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving endpoints by results: {str(e)}"
        )


@router.get(
    "/admin/response_times",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] Response Time Trends",
    description="""
    Get response time trends over time for site analytics.
    
    **Access:** ADMIN only
    """
)
@limiter.limit(rate_max)
async def get_response_times_admin(
    request: Request,
    time_range: TimeRange = Query(TimeRange.LAST_7_DAYS, description="Time range for analytics"),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get response time trends grouped by date.
    """
    start_date, end_date = get_date_range(time_range, timezone_offset)
    offset_minutes = -timezone_offset
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        DATE(request_timestamp + (%s || ' minutes')::INTERVAL) as date,
                        AVG(response_time_ms) as avg_response_time,
                        MIN(response_time_ms) as min_response_time,
                        MAX(response_time_ms) as max_response_time,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms) as median_response_time,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_response_time,
                        COUNT(*) as request_count
                    FROM base.tbl_search_analytics
                    WHERE request_timestamp >= %s
                        AND request_timestamp <= %s
                    GROUP BY DATE(request_timestamp + (%s || ' minutes')::INTERVAL)
                    ORDER BY date ASC
                """, (offset_minutes, start_date, end_date, offset_minutes))
                
                response_times = cur.fetchall()
                
                return {
                    "response_times": response_times,
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "label": time_range.value
                    }
                }
                
    except Exception as e:
        logger.error(f"Error fetching response times: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving response times: {str(e)}"
        )


@router.get(
    "/admin/users/{user_id}/searches",
    tags=[TAG_ANALYTICS],
    summary="[ADMIN] User Search History",
    description="""
    View search history for a specific user.
    
    **Access:** ADMIN only
    
    Timezone filtering is based on user's local timezone for accurate date range filtering.
    """
)
@limiter.limit(rate_max)
async def get_user_searches_admin(
    request: Request,
    user_id: str,
    time_range: TimeRange = Query(TimeRange.LAST_30_DAYS, description="Time range for analytics"),
    limit: int = Query(50, ge=1, le=500),
    page: int = Query(1, ge=1),
    timezone_offset: int = Query(0, description="User's timezone offset in minutes from UTC (from JavaScript's getTimezoneOffset())"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
):
    """
    Get search history for a specific user (admin only).
    
    Similar to /my_searches but allows admins to view any user's history.
    """
    start_date, end_date = get_date_range(time_range, timezone_offset)
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
