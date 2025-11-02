"""
Example API endpoints demonstrating subscription-based authentication.

This file shows various ways to protect endpoints based on subscription status.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging

# Import authentication dependencies
from auth import (
    get_current_user,
    get_current_active_subscriber,
    require_plan,
    verify_api_key,
    verify_license_key,
    authenticate_user,
    create_user_session,
    User,
    rate_limiter
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Protected Endpoints"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class SubscriptionInfo(BaseModel):
    status: str
    plan: str
    renews_at: Optional[str]
    ends_at: Optional[str]


# ============================================================================
# PUBLIC ENDPOINTS (No Authentication)
# ============================================================================

@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """
    Login endpoint - returns JWT token if user has valid subscription.
    
    This is typically called after a successful checkout from Lemon Squeezy.
    """
    # Authenticate user
    user = await authenticate_user(credentials.email, credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # TODO: Get user's subscription_id from database
    # subscription_id = await get_user_subscription_id(user.user_id)
    subscription_id = "123456"  # Mock
    
    # Create session token
    session = await create_user_session(user, subscription_id)
    
    return LoginResponse(
        access_token=session["access_token"],
        token_type=session["token_type"],
        expires_in=session["expires_in"],
        user={
            "user_id": user.user_id,
            "email": user.email
        }
    )


@router.get("/health")
async def health_check():
    """Public health check endpoint"""
    return {"status": "healthy"}


# ============================================================================
# BASIC AUTHENTICATED ENDPOINTS (Any logged-in user)
# ============================================================================

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    """
    Get user profile - requires authentication but not necessarily a subscription.
    Use this for endpoints that logged-in users can access regardless of subscription.
    """
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "message": "This endpoint requires authentication but not a subscription"
    }


@router.get("/account")
async def get_account(current_user: User = Depends(get_current_user)):
    """Get account information - available to any authenticated user"""
    # TODO: Fetch actual account data from database
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "created_at": "2025-01-01T00:00:00Z",
        "has_subscription": False  # Check actual subscription status
    }


# ============================================================================
# SUBSCRIPTION REQUIRED ENDPOINTS
# ============================================================================

@router.get("/premium-content")
async def get_premium_content(
    current_user: User = Depends(get_current_active_subscriber)
):
    """
    Premium content - requires active subscription.
    This is the main pattern for protecting content behind a subscription.
    """
    return {
        "message": "Welcome to premium content!",
        "user": current_user.user_id,
        "subscription_status": current_user.subscription.status if current_user.subscription else None,
        "content": "This is exclusive content for subscribers only"
    }


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_active_subscriber)
):
    """User dashboard - requires active subscription"""
    return {
        "user": {
            "user_id": current_user.user_id,
            "email": current_user.email
        },
        "subscription": {
            "status": current_user.subscription.status,
            "product_id": current_user.subscription.product_id,
            "renews_at": current_user.subscription.renews_at,
            "ends_at": current_user.subscription.ends_at
        } if current_user.subscription else None,
        "stats": {
            "api_calls_today": 1523,
            "storage_used": "45.2 GB",
            "bandwidth_used": "120.5 GB"
        }
    }


@router.get("/subscription")
async def get_subscription_info(
    current_user: User = Depends(get_current_active_subscriber)
):
    """
    Get detailed subscription information.
    """
    if not current_user.subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found"
        )
    
    return {
        "subscription_id": current_user.subscription.subscription_id,
        "status": current_user.subscription.status,
        "product_id": current_user.subscription.product_id,
        "variant_id": current_user.subscription.variant_id,
        "customer_id": current_user.subscription.customer_id,
        "renews_at": current_user.subscription.renews_at,
        "ends_at": current_user.subscription.ends_at
    }


@router.post("/data/upload")
async def upload_data(
    current_user: User = Depends(get_current_active_subscriber)
):
    """Upload data - requires active subscription"""
    return {
        "message": "Data uploaded successfully",
        "uploaded_by": current_user.user_id
    }


@router.get("/reports")
async def get_reports(
    current_user: User = Depends(get_current_active_subscriber)
):
    """Generate reports - requires active subscription"""
    return {
        "reports": [
            {"id": 1, "name": "Monthly Report", "date": "2025-10-31"},
            {"id": 2, "name": "Annual Report", "date": "2025-01-01"}
        ],
        "user": current_user.user_id
    }


# ============================================================================
# PLAN-SPECIFIC ENDPOINTS (Require specific subscription tiers)
# ============================================================================

@router.get("/pro-feature")
async def pro_feature(
    current_user: User = Depends(get_current_active_subscriber),
    _: None = Depends(require_plan(["pro-variant-id", "enterprise-variant-id"]))
):
    """
    Pro feature - requires Pro or Enterprise subscription.
    
    To use this:
    1. Get your variant IDs from Lemon Squeezy dashboard
    2. Replace "pro-variant-id" and "enterprise-variant-id" with actual IDs
    """
    return {
        "message": "This is a Pro feature!",
        "user": current_user.user_id,
        "plan": current_user.subscription.variant_id if current_user.subscription else None
    }


@router.get("/enterprise-feature")
async def enterprise_feature(
    current_user: User = Depends(get_current_active_subscriber),
    _: None = Depends(require_plan(["enterprise-variant-id"]))
):
    """
    Enterprise feature - requires Enterprise subscription only.
    """
    return {
        "message": "Welcome to Enterprise features!",
        "user": current_user.user_id,
        "advanced_analytics": True,
        "priority_support": True,
        "custom_integrations": True
    }


@router.get("/analytics")
async def get_analytics(
    current_user: User = Depends(get_current_active_subscriber),
    _: None = Depends(require_plan(["pro-variant-id", "enterprise-variant-id"]))
):
    """Advanced analytics - Pro and Enterprise only"""
    return {
        "analytics": {
            "total_users": 1250,
            "active_users": 890,
            "revenue": 45000,
            "growth_rate": 15.3
        },
        "plan": current_user.subscription.variant_id if current_user.subscription else None
    }


# ============================================================================
# RATE LIMITED ENDPOINTS
# ============================================================================

@router.get("/api-calls")
async def make_api_call(
    current_user: User = Depends(rate_limiter.check_limit)
):
    """
    Rate limited endpoint based on subscription tier.
    
    Rate limits:
    - Basic: 10 requests/minute
    - Pro: 100 requests/minute
    - Enterprise: 1000 requests/minute
    """
    return {
        "message": "API call successful",
        "user": current_user.user_id,
        "plan": current_user.subscription.variant_id if current_user.subscription else None,
        "data": "Your requested data..."
    }


# ============================================================================
# API KEY AUTHENTICATION (Alternative)
# ============================================================================

@router.get("/api-key-protected")
async def api_key_protected(
    current_user: User = Depends(verify_api_key)
):
    """
    Protected by API key instead of JWT token.
    Useful for server-to-server communication.
    
    Usage:
        curl -H "X-API-Key: your-api-key" https://api.example.com/api/api-key-protected
    """
    return {
        "message": "Authenticated with API key",
        "user": current_user.user_id
    }


# ============================================================================
# LICENSE KEY AUTHENTICATION (For software products)
# ============================================================================

@router.get("/license-protected")
async def license_protected(
    license_info: dict = Depends(verify_license_key)
):
    """
    Protected by license key - useful for desktop/mobile apps.
    
    Usage:
        curl -H "X-License-Key: XXXX-XXXX-XXXX-XXXX" https://api.example.com/api/license-protected
    """
    return {
        "message": "Authenticated with license key",
        "license": license_info.get("license_key", {}),
        "valid": license_info.get("valid", False),
        "data": "Your licensed content..."
    }


# ============================================================================
# WEBHOOK INTEGRATION (Update subscription status)
# ============================================================================

@router.post("/webhooks/subscription-updated")
async def handle_subscription_update():
    """
    Example webhook handler that would update subscription in database.
    This would be called from your Lemon Squeezy webhook handler.
    
    When subscription status changes:
    1. Webhook arrives at /api/sqzy/webhooks
    2. Webhook handler updates database
    3. Next API call automatically reflects new subscription status
    """
    # This is handled in lemon_squeezy_router.py
    # Just showing the flow here
    return {"message": "See lemon_squeezy_router.py for webhook implementation"}


# ============================================================================
# ERROR HANDLING EXAMPLES
# ============================================================================

@router.get("/subscription-required-demo")
async def subscription_demo(
    current_user: User = Depends(get_current_active_subscriber)
):
    """
    This endpoint will return different errors based on user state:
    
    1. No token -> 401 Unauthorized
    2. Invalid token -> 401 Unauthorized  
    3. Valid token but no subscription -> 403 Forbidden
    4. Valid token but expired subscription -> 403 Forbidden
    5. Valid token and active subscription -> 200 OK
    """
    return {
        "message": "You have successfully authenticated with an active subscription!",
        "user": current_user.user_id,
        "subscription": current_user.subscription.status if current_user.subscription else None
    }


# ============================================================================
# USAGE EXAMPLES IN CLIENT CODE
# ============================================================================

"""
JAVASCRIPT/TYPESCRIPT CLIENT EXAMPLES:

1. Login and get token:
```javascript
const response = await fetch('https://api.example.com/api/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'password123'
  })
});

const { access_token } = await response.json();
localStorage.setItem('token', access_token);
```

2. Call protected endpoint:
```javascript
const token = localStorage.getItem('token');

const response = await fetch('https://api.example.com/api/premium-content', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

if (response.status === 401) {
  // Token expired or invalid - redirect to login
  window.location.href = '/login';
} else if (response.status === 403) {
  // No active subscription - redirect to pricing
  window.location.href = '/pricing';
} else {
  const data = await response.json();
  console.log(data);
}
```

3. Handle subscription required:
```javascript
async function callProtectedAPI(endpoint) {
  const token = localStorage.getItem('token');
  
  const response = await fetch(`https://api.example.com/api/${endpoint}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  if (response.status === 403) {
    const error = await response.json();
    if (error.detail.includes('subscription')) {
      // Show upgrade modal
      showUpgradeModal();
    }
  }
  
  return response.json();
}
```

PYTHON CLIENT EXAMPLES:

```python
import httpx

class APIClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
    
    async def get_premium_content(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/premium-content",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 403:
                raise Exception("Subscription required")
            
            response.raise_for_status()
            return response.json()

# Usage
client = APIClient("https://api.example.com", "your-token")
content = await client.get_premium_content()
```
"""
