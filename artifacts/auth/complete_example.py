"""
Complete working example integrating Lemon Squeezy with subscription-based authentication.

This file shows a minimal but complete implementation that you can use as a starting point.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
import httpx
import jwt
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
LEMON_SQUEEZY_API_KEY = os.getenv("LEMON_SQUEEZY_API_KEY")
LEMON_SQUEEZY_API_URL = "https://api.lemonsqueezy.com/v1"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create app
app = FastAPI(
    title="Subscription API",
    description="Complete example with Lemon Squeezy subscription authentication"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ============================================================================
# MODELS
# ============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    user_id: str
    email: str
    subscription_status: Optional[str] = None


# ============================================================================
# IN-MEMORY DATABASE (Replace with real database)
# ============================================================================

# Mock users database
USERS_DB = {
    "user@example.com": {
        "user_id": "user_123",
        "email": "user@example.com",
        "password": "password123",  # In production: use hashed passwords
        "subscription_id": "sub_12345"
    }
}

# Mock subscriptions database (updated by webhooks)
SUBSCRIPTIONS_DB = {
    "sub_12345": {
        "subscription_id": "sub_12345",
        "status": "active",
        "customer_id": "cust_123",
        "product_id": "prod_123",
        "variant_id": "variant_basic_123",  # Replace with your actual variant IDs
        "renews_at": "2025-11-30T00:00:00Z",
        "ends_at": None
    }
}


# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def create_token(user_id: str, email: str, subscription_id: Optional[str] = None) -> str:
    """Create JWT token"""
    payload = {
        "user_id": user_id,
        "email": email,
        "subscription_id": subscription_id,
        "exp": datetime.utcnow() + timedelta(minutes=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Get authenticated user from token"""
    token = credentials.credentials
    payload = verify_token(token)
    
    user_id = payload.get("user_id")
    email = payload.get("email")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return User(user_id=user_id, email=email)


async def require_active_subscription(
    user: User = Depends(get_current_user)
) -> User:
    """
    Require user to have active subscription.
    This is the KEY dependency for protecting endpoints.
    """
    # Get user's subscription_id
    user_data = USERS_DB.get(user.email)
    if not user_data or not user_data.get("subscription_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No subscription found. Please subscribe at https://yoursite.com/pricing"
        )
    
    subscription_id = user_data["subscription_id"]
    
    # Get subscription details
    subscription = SUBSCRIPTIONS_DB.get(subscription_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription not found in database"
        )
    
    # Check subscription status
    status_value = subscription["status"].lower()
    if status_value not in ["active", "on_trial"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subscription is {status_value}. Please update your subscription."
        )
    
    # Check if subscription has ended
    ends_at = subscription.get("ends_at")
    if ends_at:
        end_date = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        if datetime.now(end_date.tzinfo) > end_date:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subscription has expired. Please renew your subscription."
            )
    
    user.subscription_status = status_value
    return user


async def require_pro_plan(user: User = Depends(require_active_subscription)):
    """Require Pro or Enterprise plan"""
    user_data = USERS_DB.get(user.email)
    subscription_id = user_data["subscription_id"]
    subscription = SUBSCRIPTIONS_DB.get(subscription_id)
    
    variant_id = subscription["variant_id"]
    
    # Replace these with your actual variant IDs from Lemon Squeezy
    PRO_VARIANTS = ["variant_pro_123", "variant_enterprise_123"]
    
    if variant_id not in PRO_VARIANTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a Pro or Enterprise subscription"
        )


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Public root endpoint"""
    return {
        "message": "Subscription API",
        "docs": "/docs",
        "endpoints": {
            "login": "/login",
            "public": "/public",
            "protected": "/premium-content (requires subscription)",
            "pro": "/pro-feature (requires Pro plan)"
        }
    }


@app.post("/login")
async def login(credentials: LoginRequest):
    """
    Login endpoint - returns JWT token.
    
    Test credentials:
    - email: user@example.com
    - password: password123
    """
    # Verify credentials
    user = USERS_DB.get(credentials.email)
    
    if not user or user["password"] != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Create token
    token = create_token(
        user_id=user["user_id"],
        email=user["email"],
        subscription_id=user.get("subscription_id")
    )
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"]
        }
    }


@app.get("/public")
async def public_endpoint():
    """Public endpoint - no authentication required"""
    return {
        "message": "This is public content, anyone can access this",
        "data": "Public data..."
    }


# ============================================================================
# AUTHENTICATED ENDPOINTS (Any logged-in user)
# ============================================================================

@app.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    """
    User profile - requires authentication but not subscription.
    """
    return {
        "user_id": user.user_id,
        "email": user.email,
        "message": "You are logged in but may not have a subscription"
    }


# ============================================================================
# SUBSCRIPTION REQUIRED ENDPOINTS
# ============================================================================

@app.get("/premium-content")
async def get_premium_content(
    user: User = Depends(require_active_subscription)
):
    """
    Premium content - REQUIRES ACTIVE SUBSCRIPTION.
    
    This is the main pattern for protecting content.
    """
    return {
        "message": "Welcome to premium content!",
        "user": user.email,
        "subscription_status": user.subscription_status,
        "content": {
            "title": "Exclusive Content",
            "data": "This content is only available to subscribers",
            "features": [
                "Advanced analytics",
                "Priority support",
                "Unlimited API calls"
            ]
        }
    }


@app.get("/dashboard")
async def get_dashboard(
    user: User = Depends(require_active_subscription)
):
    """Dashboard - requires active subscription"""
    user_data = USERS_DB.get(user.email)
    subscription = SUBSCRIPTIONS_DB.get(user_data["subscription_id"])
    
    return {
        "user": {
            "user_id": user.user_id,
            "email": user.email
        },
        "subscription": {
            "status": subscription["status"],
            "product_id": subscription["product_id"],
            "variant_id": subscription["variant_id"],
            "renews_at": subscription["renews_at"]
        },
        "stats": {
            "api_calls_today": 1523,
            "storage_used": "45.2 GB"
        }
    }


@app.post("/api/process")
async def process_data(
    user: User = Depends(require_active_subscription)
):
    """Process data - requires subscription"""
    return {
        "message": "Data processed successfully",
        "processed_by": user.user_id,
        "result": "Your processing results..."
    }


# ============================================================================
# PRO PLAN ENDPOINTS
# ============================================================================

@app.get("/pro-feature")
async def pro_feature(
    user: User = Depends(require_active_subscription),
    _: None = Depends(require_pro_plan)
):
    """
    Pro feature - requires Pro or Enterprise subscription.
    
    To use this:
    1. Get your variant IDs from Lemon Squeezy dashboard
    2. Update PRO_VARIANTS list in require_pro_plan()
    """
    return {
        "message": "This is a Pro feature!",
        "user": user.email,
        "feature_data": "Advanced analytics and insights..."
    }


@app.get("/advanced-analytics")
async def advanced_analytics(
    user: User = Depends(require_active_subscription),
    _: None = Depends(require_pro_plan)
):
    """Advanced analytics - Pro/Enterprise only"""
    return {
        "analytics": {
            "total_revenue": 125000,
            "growth_rate": 23.5,
            "customer_lifetime_value": 1250,
            "churn_rate": 2.3
        }
    }


# ============================================================================
# WEBHOOK ENDPOINT (Updates subscription status)
# ============================================================================

from fastapi import Request, Header
import hmac
import hashlib


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Lemon Squeezy webhook signature"""
    secret = os.getenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "")
    computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@app.post("/webhooks/lemon-squeezy")
async def webhook_handler(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature")
):
    """
    Webhook handler - updates subscription status in database.
    
    This is called by Lemon Squeezy when subscription changes occur.
    """
    # Get raw body
    body = await request.body()
    
    # Verify signature
    if not x_signature or not verify_webhook_signature(body, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse webhook data
    data = await request.json()
    event_name = data.get("meta", {}).get("event_name")
    
    logger.info(f"Received webhook: {event_name}")
    
    # Handle different events
    if event_name == "subscription_created":
        sub_data = data.get("data", {}).get("attributes", {})
        subscription_id = data.get("data", {}).get("id")
        
        # Update database (in production, this would be a real database update)
        SUBSCRIPTIONS_DB[subscription_id] = {
            "subscription_id": subscription_id,
            "status": sub_data.get("status"),
            "customer_id": sub_data.get("customer_id"),
            "product_id": sub_data.get("product_id"),
            "variant_id": sub_data.get("variant_id"),
            "renews_at": sub_data.get("renews_at"),
            "ends_at": sub_data.get("ends_at")
        }
        
        logger.info(f"Subscription {subscription_id} created")
    
    elif event_name == "subscription_updated":
        sub_data = data.get("data", {}).get("attributes", {})
        subscription_id = data.get("data", {}).get("id")
        
        if subscription_id in SUBSCRIPTIONS_DB:
            SUBSCRIPTIONS_DB[subscription_id]["status"] = sub_data.get("status")
            logger.info(f"Subscription {subscription_id} updated to {sub_data.get('status')}")
    
    elif event_name == "subscription_cancelled":
        sub_data = data.get("data", {}).get("attributes", {})
        subscription_id = data.get("data", {}).get("id")
        
        if subscription_id in SUBSCRIPTIONS_DB:
            SUBSCRIPTIONS_DB[subscription_id]["status"] = "cancelled"
            SUBSCRIPTIONS_DB[subscription_id]["ends_at"] = sub_data.get("ends_at")
            logger.info(f"Subscription {subscription_id} cancelled")
    
    return {"status": "success"}


# ============================================================================
# TESTING ENDPOINTS
# ============================================================================

@app.get("/test/subscription-status")
async def test_subscription_status(user: User = Depends(get_current_user)):
    """
    Test endpoint to check subscription status without requiring active subscription.
    Useful for debugging.
    """
    user_data = USERS_DB.get(user.email)
    subscription_id = user_data.get("subscription_id") if user_data else None
    
    if not subscription_id:
        return {
            "has_subscription": False,
            "message": "No subscription found"
        }
    
    subscription = SUBSCRIPTIONS_DB.get(subscription_id)
    
    return {
        "has_subscription": True,
        "subscription_id": subscription_id,
        "status": subscription.get("status") if subscription else "not_found",
        "variant_id": subscription.get("variant_id") if subscription else None,
        "is_active": subscription.get("status") in ["active", "on_trial"] if subscription else False
    }


# ============================================================================
# HOW TO TEST THIS API
# ============================================================================

"""
TESTING INSTRUCTIONS:

1. Start the server:
   uvicorn complete_example:app --reload

2. Login to get token:
   curl -X POST http://localhost:8000/login \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"password123"}'
   
   Save the access_token from response.

3. Test public endpoint (no auth needed):
   curl http://localhost:8000/public

4. Test authenticated endpoint:
   curl http://localhost:8000/profile \
     -H "Authorization: Bearer YOUR_TOKEN"

5. Test subscription-required endpoint:
   curl http://localhost:8000/premium-content \
     -H "Authorization: Bearer YOUR_TOKEN"

6. Test without token (should fail with 401):
   curl http://localhost:8000/premium-content

7. Test Pro feature:
   curl http://localhost:8000/pro-feature \
     -H "Authorization: Bearer YOUR_TOKEN"
   
   Note: This will fail (403) because the mock user has basic plan.
   To test: Change variant_id in SUBSCRIPTIONS_DB to match PRO_VARIANTS.

EXPECTED RESPONSES:
- No token → 401 Unauthorized
- Valid token, no subscription → 403 Forbidden
- Valid token, inactive subscription → 403 Forbidden  
- Valid token, active subscription → 200 OK
- Valid token, wrong plan → 403 Forbidden (for plan-specific endpoints)
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
