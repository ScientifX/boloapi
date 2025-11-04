"""
FastAPI Rate Limiting Example using SlowAPI

This example demonstrates various rate limiting strategies:
- Global rate limits
- Per-endpoint rate limits
- Different limits for authenticated vs unauthenticated users
- Custom key functions (IP-based, user-based, etc.)
"""

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional
import uvicorn


# Custom key function for authenticated users
def get_user_identifier(request: Request) -> str:
    """
    Get identifier for rate limiting.
    Uses user ID if authenticated, otherwise falls back to IP address.
    """
    # Check if user is authenticated (you'd implement this based on your auth system)
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return f"user:{user_id}"
    return get_remote_address(request)


# Initialize the limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(title="Rate Limiting Example")

# Add the limiter to the app state
app.state.limiter = limiter

# Add exception handler for rate limit exceeded
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================================
# ENDPOINTS WITH DIFFERENT RATE LIMITING STRATEGIES
# ============================================================================

@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    """
    Basic endpoint with rate limit: 10 requests per minute per IP
    """
    return {"message": "Welcome! This endpoint allows 10 requests per minute."}


@app.get("/strict")
@limiter.limit("3/minute")
async def strict_endpoint(request: Request):
    """
    Stricter rate limit: only 3 requests per minute
    """
    return {"message": "This is a strictly rate-limited endpoint (3/minute)."}


@app.get("/generous")
@limiter.limit("100/minute")
async def generous_endpoint(request: Request):
    """
    More generous rate limit: 100 requests per minute
    """
    return {"message": "This endpoint is more generous (100/minute)."}


@app.get("/multiple-limits")
@limiter.limit("10/second")
@limiter.limit("50/minute")
@limiter.limit("200/hour")
async def multiple_limits(request: Request):
    """
    Multiple rate limits applied to the same endpoint.
    Whichever limit is hit first will trigger the rate limit.
    """
    return {
        "message": "This endpoint has multiple rate limits",
        "limits": ["10/second", "50/minute", "200/hour"]
    }


@app.get("/user-based")
@limiter.limit("20/minute", key_func=get_user_identifier)
async def user_based_limit(request: Request):
    """
    Rate limit based on user ID if authenticated, otherwise by IP.
    Authenticated users get their own rate limit bucket.
    """
    user_id = request.headers.get("X-User-ID", "anonymous")
    return {
        "message": "User-based rate limiting",
        "user": user_id,
        "limit": "20/minute per user"
    }


@app.post("/api/data")
@limiter.limit("5/minute")
async def create_data(request: Request, data: dict):
    """
    POST endpoint with rate limiting.
    Useful for write operations that you want to limit more strictly.
    """
    return {
        "message": "Data created successfully",
        "data": data,
        "limit": "5 POST requests per minute"
    }


@app.get("/no-limit")
async def no_limit(request: Request):
    """
    Endpoint without rate limiting.
    Use this for health checks or other endpoints that shouldn't be limited.
    """
    return {"message": "This endpoint has no rate limit."}


# ============================================================================
# EXEMPT CERTAIN ENDPOINTS (Alternative approach)
# ============================================================================

@app.get("/health")
@limiter.exempt
async def health_check(request: Request):
    """
    Health check endpoint - explicitly exempted from rate limiting.
    """
    return {"status": "healthy"}


# ============================================================================
# CUSTOM ERROR HANDLING
# ============================================================================

@app.get("/custom-error")
@limiter.limit("2/minute")
async def custom_error_handling(request: Request):
    """
    Endpoint demonstrating custom error handling.
    The global handler will catch RateLimitExceeded errors.
    """
    return {"message": "Try hitting this endpoint more than 2 times per minute!"}


# ============================================================================
# DYNAMIC RATE LIMITING
# ============================================================================

def get_dynamic_limit(request: Request) -> str:
    """
    Dynamic rate limit based on request properties.
    Premium users get higher limits.
    """
    user_tier = request.headers.get("X-User-Tier", "free")
    
    limits = {
        "free": "5/minute",
        "premium": "50/minute",
        "enterprise": "500/minute"
    }
    
    return limits.get(user_tier, "5/minute")


@app.get("/dynamic")
async def dynamic_limit(request: Request):
    """
    Dynamic rate limiting based on user tier.
    Send X-User-Tier header with 'free', 'premium', or 'enterprise'.
    """
    # Apply limit dynamically
    limit_string = get_dynamic_limit(request)
    
    # You'd need to implement dynamic limiting differently
    # This is a simplified example
    user_tier = request.headers.get("X-User-Tier", "free")
    
    return {
        "message": "Dynamic rate limiting based on user tier",
        "tier": user_tier,
        "limit": limit_string
    }


# ============================================================================
# RATE LIMIT INFO ENDPOINT
# ============================================================================

@app.get("/rate-limit-info")
async def rate_limit_info(request: Request):
    """
    Informational endpoint showing rate limit headers.
    SlowAPI adds rate limit info to response headers.
    """
    return {
        "message": "Check the response headers for rate limit information",
        "headers_to_check": [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ]
    }


# ============================================================================
# SHARED RATE LIMIT ACROSS ENDPOINTS
# ============================================================================

# Define a shared limit
shared_limit = "10/minute"

@app.get("/shared/endpoint1")
@limiter.shared_limit(shared_limit, scope="shared")
async def shared_endpoint_1(request: Request):
    """Shares rate limit with endpoint2"""
    return {"message": "Shared limit endpoint 1"}

@app.get("/shared/endpoint2")
@limiter.shared_limit(shared_limit, scope="shared")
async def shared_endpoint_2(request: Request):
    """Shares rate limit with endpoint1"""
    return {"message": "Shared limit endpoint 2"}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("Starting FastAPI app with SlowAPI rate limiting...")
    print("Example usage:")
    print("  - Visit http://localhost:8000/docs for API documentation")
    print("  - Try hitting endpoints multiple times to trigger rate limits")
    print("  - Add 'X-User-ID' header to test user-based limiting")
    print("  - Add 'X-User-Tier' header (free/premium/enterprise) for dynamic limits")
    
    uvicorn.run(app, host="127.0.0.1", port=8005)
