"""
Advanced FastAPI Rate Limiting with Redis Storage

This example shows how to use Redis as a storage backend for rate limiting,
which is essential for distributed systems and production environments.
"""

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from typing import Optional
import uvicorn
import redis
import os


# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# For production, use Redis as the storage backend
# This allows rate limiting to work across multiple server instances
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    # Try to connect to Redis
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    
    # Create limiter with Redis storage
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=REDIS_URL,
        strategy="fixed-window"  # or "moving-window"
    )
    print(f"✓ Connected to Redis at {REDIS_URL}")
    
except (redis.ConnectionError, redis.TimeoutError):
    print(f"⚠ Warning: Could not connect to Redis at {REDIS_URL}")
    print("  Falling back to in-memory storage (not suitable for production)")
    
    # Fallback to in-memory storage
    limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Advanced Rate Limiting with Redis",
    description="Production-ready rate limiting with Redis backend"
)

# Add limiter to app state
app.state.limiter = limiter

# Add exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add SlowAPI middleware for automatic rate limit headers
app.add_middleware(SlowAPIMiddleware)


# ============================================================================
# CUSTOM KEY FUNCTIONS
# ============================================================================

def get_api_key_identifier(request: Request) -> str:
    """Rate limit by API key if present, otherwise by IP"""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key}"
    return f"ip:{get_remote_address(request)}"


def get_user_or_ip(request: Request) -> str:
    """Rate limit by authenticated user ID or IP address"""
    # In a real app, you'd extract this from your auth token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Parse your JWT or session token here
        user_id = auth_header.replace("Bearer ", "")[:10]  # Simplified
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def get_endpoint_specific_key(request: Request) -> str:
    """Combine endpoint path with identifier for per-endpoint-per-user limits"""
    user_key = get_user_or_ip(request)
    path = request.url.path
    return f"{path}:{user_key}"


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
@limiter.limit("20/minute")
async def root(request: Request):
    """Standard rate-limited endpoint"""
    return {
        "message": "Welcome to the rate-limited API!",
        "rate_limit": "20 requests per minute per IP",
        "storage": "Redis" if REDIS_URL else "In-Memory"
    }


@app.get("/api/public")
@limiter.limit("10/minute", key_func=get_remote_address)
async def public_endpoint(request: Request):
    """Public endpoint with IP-based rate limiting"""
    return {
        "message": "Public endpoint",
        "limit": "10/minute per IP"
    }


@app.get("/api/authenticated")
@limiter.limit("100/minute", key_func=get_user_or_ip)
async def authenticated_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Authenticated endpoint with higher limits.
    Rate limit is per user if authenticated, per IP otherwise.
    """
    is_authenticated = authorization and authorization.startswith("Bearer ")
    
    return {
        "message": "Authenticated endpoint",
        "authenticated": is_authenticated,
        "limit": "100/minute per user (or 100/minute per IP if not authenticated)"
    }


@app.get("/api/premium")
@limiter.limit("1000/hour", key_func=get_api_key_identifier)
async def premium_endpoint(
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    """
    Premium endpoint for API key holders.
    Rate limited by API key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add X-API-Key header."
        )
    
    return {
        "message": "Premium endpoint",
        "api_key": x_api_key[:8] + "...",
        "limit": "1000/hour per API key"
    }


@app.post("/api/write")
@limiter.limit("5/minute", key_func=get_user_or_ip)
async def write_operation(request: Request, data: dict):
    """
    Write endpoint with stricter rate limiting.
    Useful for POST/PUT/DELETE operations.
    """
    return {
        "message": "Data processed",
        "data": data,
        "limit": "5/minute for write operations"
    }


@app.get("/api/burst")
@limiter.limit("30/minute")
@limiter.limit("5/second")
async def burst_protection(request: Request):
    """
    Endpoint with burst protection.
    Allows 30/minute but max 5 per second to prevent bursts.
    """
    return {
        "message": "Protected against burst traffic",
        "limits": ["5/second", "30/minute"]
    }


# ============================================================================
# TIERED RATE LIMITS
# ============================================================================

TIER_LIMITS = {
    "free": "10/minute",
    "basic": "50/minute",
    "premium": "200/minute",
    "enterprise": "1000/minute"
}

def get_tier_from_api_key(api_key: str) -> str:
    """
    In production, look up tier from database.
    This is a simplified example.
    """
    if api_key.startswith("ent_"):
        return "enterprise"
    elif api_key.startswith("pre_"):
        return "premium"
    elif api_key.startswith("bas_"):
        return "basic"
    return "free"


@app.get("/api/tiered")
async def tiered_endpoint(
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    """
    Dynamic rate limiting based on API key tier.
    Requires manual limit checking for dynamic limits.
    """
    tier = "free"
    if x_api_key:
        tier = get_tier_from_api_key(x_api_key)
    
    # For dynamic limits, you'd need to implement custom logic
    # or use the limiter programmatically
    
    return {
        "message": "Tiered endpoint",
        "tier": tier,
        "limit": TIER_LIMITS[tier],
        "note": "Use static decorators for enforcement"
    }


# ============================================================================
# MONITORING AND ADMIN ENDPOINTS
# ============================================================================

@app.get("/health")
@limiter.exempt
async def health_check(request: Request):
    """Health check - exempt from rate limiting"""
    redis_status = "connected"
    try:
        if REDIS_URL:
            redis_client.ping()
    except:
        redis_status = "disconnected"
    
    return {
        "status": "healthy",
        "redis": redis_status,
        "storage": "Redis" if REDIS_URL else "In-Memory"
    }


@app.get("/rate-limit-status")
@limiter.limit("5/minute")
async def rate_limit_status(request: Request):
    """
    Check current rate limit status.
    Response headers contain rate limit information.
    """
    return {
        "message": "Check response headers for rate limit details",
        "headers": {
            "X-RateLimit-Limit": "Total requests allowed in window",
            "X-RateLimit-Remaining": "Requests remaining in current window",
            "X-RateLimit-Reset": "Unix timestamp when the limit resets"
        }
    }


# ============================================================================
# SHARED LIMITS FOR RELATED ENDPOINTS
# ============================================================================

@app.get("/api/v1/users")
@limiter.shared_limit("50/minute", scope="user_api")
async def get_users(request: Request):
    """Part of user API with shared rate limit"""
    return {"endpoint": "get_users", "shared_limit": "50/minute"}


@app.post("/api/v1/users")
@limiter.shared_limit("50/minute", scope="user_api")
async def create_user(request: Request, data: dict):
    """Part of user API with shared rate limit"""
    return {"endpoint": "create_user", "shared_limit": "50/minute"}


@app.get("/api/v1/users/{user_id}")
@limiter.shared_limit("50/minute", scope="user_api")
async def get_user(request: Request, user_id: int):
    """Part of user API with shared rate limit"""
    return {"endpoint": "get_user", "user_id": user_id, "shared_limit": "50/minute"}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("Advanced FastAPI Rate Limiting Example")
    print("="*70)
    print(f"\nStorage Backend: {'Redis' if REDIS_URL else 'In-Memory'}")
    if REDIS_URL:
        print(f"Redis URL: {REDIS_URL}")
    print("\nStarting server on http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("\nTest commands:")
    print("  # Basic test")
    print("  curl http://localhost:8000/")
    print("\n  # With API key")
    print("  curl -H 'X-API-Key: pre_abc123' http://localhost:8000/api/premium")
    print("\n  # With authentication")
    print("  curl -H 'Authorization: Bearer token123' http://localhost:8000/api/authenticated")
    print("\n  # Trigger rate limit")
    print("  for i in {1..15}; do curl http://localhost:8000/api/public; done")
    print("\n" + "="*70 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
