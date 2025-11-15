"""
Billing Router
Handles LemonSqueezy checkout, webhooks, and subscription management
"""
import os
import hmac
import hashlib
import requests
import logging
from datetime import datetime, timezone
from typing import Literal, Optional, Dict, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Request, status, Depends, Header
from fastapi.responses import JSONResponse
from fastapi import BackgroundTasks
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import (
    DB_CONFIG,
    API_LEMONSQUEEZY_API_KEY,
    API_LEMONSQUEEZY_STORE_ID,
    API_LEMONSQUEEZY_WEBHOOK_SECRET,
    PRICING
)
from auth import UserRole
from jwt_auth import require_jwt_role

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# Router
router = APIRouter(prefix="/billing", tags=["Billing"])

# ============================================================================
# DATABASE HELPERS
# ============================================================================

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

def get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by user_id"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM tbl_users WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateCheckoutRequest(BaseModel):
    """Request to create LemonSqueezy checkout session"""
    billing_cycle: Literal["monthly", "quarterly", "annual"] = Field(
        ...,
        description="Billing cycle for subscription"
    )

class CheckoutResponse(BaseModel):
    """Response containing checkout URL"""
    checkout_url: str
    billing_cycle: str
    price: float
    currency: str

class SubscriptionStatus(BaseModel):
    """Current subscription status"""
    plan: str  # 'basic' or 'premium'
    status: str  # 'active', 'cancelled', 'expired', etc.
    billing_cycle: Optional[str]
    renews_at: Optional[str]
    ends_at: Optional[str]
    cancelled_at: Optional[str]

class PaymentHistoryItem(BaseModel):
    """Single payment history item"""
    payment_id: str
    amount: float
    currency: str
    status: str
    billing_cycle: Optional[str]
    payment_date: str
    invoice_url: Optional[str]

class BillingInfo(BaseModel):
    """Complete billing information"""
    subscription: SubscriptionStatus
    payment_history: list[PaymentHistoryItem]
    portal_url: str

# ============================================================================
# LEMONSQUEEZY API HELPERS
# ============================================================================

def create_lemonsqueezy_checkout(
    user_email: str,
    user_id: str,
    variant_id: str,
    billing_cycle: str
) -> str:
    """
    Create a checkout session in LemonSqueezy.
    
    Args:
        user_email: User's email address
        user_id: User's UUID
        variant_id: LemonSqueezy variant ID for the product
        billing_cycle: 'monthly', 'quarterly', or 'annual'
        
    Returns:
        Checkout URL for the user to complete payment
    """
    url = "https://api.lemonsqueezy.com/v1/checkouts"
    
    headers = {
        "Authorization": f"Bearer {API_LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }
    
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user_email,
                    "custom": {
                        "user_id": user_id,
                        "billing_cycle": billing_cycle
                    }
                }
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": API_LEMONSQUEEZY_STORE_ID
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": variant_id
                    }
                }
            }
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        checkout_url = data["data"]["attributes"]["url"]
        
        logger.info(f"Created checkout for user {user_id}: {checkout_url}")
        return checkout_url
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create LemonSqueezy checkout: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify LemonSqueezy webhook signature.
    
    Args:
        payload: Raw request body as bytes
        signature: X-Signature header value
        
    Returns:
        True if signature is valid
    """
    if not API_LEMONSQUEEZY_WEBHOOK_SECRET:
        logger.warning("Webhook secret not configured - signature verification skipped")
        return True  # For development only
    
    expected_signature = hmac.new(
        API_LEMONSQUEEZY_WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

# ============================================================================
# WEBHOOK HANDLERS
# ============================================================================

def handle_subscription_created(data: Dict[str, Any]) -> None:
    """
    Handle subscription_created webhook event.
    Upgrade user to PREMIUM role.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        
        subscription_id = data['id']
        customer_id = attributes.get('customer_id')
        renews_at = attributes.get('renews_at')
        
        if not user_id:
            logger.error("No user_id in subscription_created webhook")
            return
        
        # Parse renews_at datetime
        renews_at_dt = datetime.fromisoformat(renews_at.replace('Z', '+00:00')) if renews_at else None
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET role = %s,
                        subscription_id = %s,
                        subscription_status = 'active',
                        subscription_plan = 'premium',
                        subscription_renews_at = %s,
                        billing_cycle = %s,
                        lemonsqueezy_customer_id = %s,
                        lemonsqueezy_subscription_id = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (
                        UserRole.PREMIUM.value,
                        subscription_id,
                        renews_at_dt,
                        billing_cycle,
                        customer_id,
                        subscription_id,
                        user_id
                    )
                )
                conn.commit()
        
        logger.info(f"Subscription created: user={user_id}, subscription={subscription_id}, cycle={billing_cycle}")
        
    except Exception as e:
        logger.error(f"Error handling subscription_created: {str(e)}")

def handle_subscription_updated(data: Dict[str, Any]) -> None:
    """
    Handle subscription_updated webhook event.
    Update subscription details (renewal date, status, etc.)
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        subscription_id = data['id']
        status_name = attributes.get('status')
        renews_at = attributes.get('renews_at')
        
        if not user_id:
            logger.error("No user_id in subscription_updated webhook")
            return
        
        # Parse renews_at datetime
        renews_at_dt = datetime.fromisoformat(renews_at.replace('Z', '+00:00')) if renews_at else None
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET subscription_status = %s,
                        subscription_renews_at = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (status_name, renews_at_dt, user_id)
                )
                conn.commit()
        
        logger.info(f"Subscription updated: user={user_id}, status={status_name}")
        
    except Exception as e:
        logger.error(f"Error handling subscription_updated: {str(e)}")

def handle_subscription_cancelled(data: Dict[str, Any]) -> None:
    """
    Handle subscription_cancelled webhook event.
    Mark as cancelled but keep PREMIUM until end of billing period.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        subscription_id = data['id']
        ends_at = attributes.get('ends_at')  # When subscription access ends
        
        if not user_id:
            logger.error("No user_id in subscription_cancelled webhook")
            return
        
        # Parse ends_at datetime
        ends_at_dt = datetime.fromisoformat(ends_at.replace('Z', '+00:00')) if ends_at else None
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET subscription_status = 'cancelled',
                        subscription_ends_at = %s,
                        subscription_cancelled_at = NOW(),
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (ends_at_dt, user_id)
                )
                # NOTE: role stays PREMIUM until subscription_expired event
                conn.commit()
        
        logger.info(f"Subscription cancelled: user={user_id}, ends_at={ends_at}")
        
    except Exception as e:
        logger.error(f"Error handling subscription_cancelled: {str(e)}")

def handle_subscription_expired(data: Dict[str, Any]) -> None:
    """
    Handle subscription_expired webhook event.
    Downgrade user to BASIC role.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in subscription_expired webhook")
            return
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET role = %s,
                        subscription_status = 'expired',
                        subscription_id = NULL,
                        subscription_plan = NULL,
                        subscription_renews_at = NULL,
                        subscription_ends_at = NULL,
                        billing_cycle = NULL,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (UserRole.BASIC.value, user_id)
                )
                conn.commit()
        
        logger.info(f"Subscription expired: user={user_id}, downgraded to BASIC")
        
    except Exception as e:
        logger.error(f"Error handling subscription_expired: {str(e)}")

def handle_subscription_payment_success(data: Dict[str, Any]) -> None:
    """
    Handle subscription_payment_success webhook event.
    Record payment in payment history.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        
        order_id = attributes.get('first_order_id') or attributes.get('order_id')
        amount = attributes.get('total')
        currency = attributes.get('currency', 'USD')
        invoice_url = attributes.get('urls', {}).get('customer_portal')
        
        if not user_id or not order_id:
            logger.error("Missing user_id or order_id in payment_success webhook")
            return
        
        # Convert amount from cents to dollars
        amount_decimal = float(amount) / 100 if amount else 0
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Insert payment record
                cur.execute(
                    """
                    INSERT INTO tbl_payment_history
                    (user_id, lemonsqueezy_order_id, amount, currency, status, 
                     billing_cycle, invoice_url, payment_date)
                    VALUES (%s, %s, %s, %s, 'paid', %s, %s, NOW())
                    ON CONFLICT (lemonsqueezy_order_id) DO NOTHING
                    """,
                    (user_id, order_id, amount_decimal, currency, billing_cycle, invoice_url)
                )
                conn.commit()
        
        logger.info(f"Payment recorded: user={user_id}, amount={amount_decimal} {currency}")
        
    except Exception as e:
        logger.error(f"Error handling subscription_payment_success: {str(e)}")

def handle_subscription_payment_failed(data: Dict[str, Any]) -> None:
    """
    Handle subscription_payment_failed webhook event.
    Update subscription status to past_due.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in payment_failed webhook")
            return
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET subscription_status = 'past_due',
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                conn.commit()
        
        logger.warning(f"Payment failed: user={user_id}, status=past_due")
        
    except Exception as e:
        logger.error(f"Error handling subscription_payment_failed: {str(e)}")

def handle_subscription_payment_recovered(data: Dict[str, Any]) -> None:
    """
    Handle subscription_payment_recovered webhook event.
    Update subscription status back to active after failed payment recovery.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in payment_recovered webhook")
            return
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET subscription_status = 'active',
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                conn.commit()
        
        logger.info(f"Payment recovered: user={user_id}, status=active")
        
    except Exception as e:
        logger.error(f"Error handling subscription_payment_recovered: {str(e)}")

def handle_order_refunded(data: Dict[str, Any]) -> None:
    """
    Handle order_refunded webhook event.
    Record refund in payment history.
    """
    try:
        attributes = data['attributes']
        custom_data = attributes.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        order_id = data['id']
        refunded_amount = attributes.get('refunded_amount')
        
        if not user_id or not order_id:
            logger.error("Missing user_id or order_id in order_refunded webhook")
            return
        
        # Convert amount from cents to dollars
        refunded_decimal = float(refunded_amount) / 100 if refunded_amount else 0
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Update existing payment record
                cur.execute(
                    """
                    UPDATE tbl_payment_history
                    SET status = 'refunded',
                        refunded_at = NOW(),
                        refund_amount = %s,
                        updated_at = NOW()
                    WHERE lemonsqueezy_order_id = %s
                    """,
                    (refunded_decimal, order_id)
                )
                conn.commit()
        
        logger.info(f"Refund recorded: user={user_id}, amount={refunded_decimal}")
        
    except Exception as e:
        logger.error(f"Error handling order_refunded: {str(e)}")

# ============================================================================
# BILLING ENDPOINTS
# ============================================================================

@router.post(
    "/create-checkout",
    response_model=CheckoutResponse,
    summary="Create Checkout Session",
    description="Create a LemonSqueezy checkout session to upgrade to Premium"
)
@limiter.limit(rate_max)
async def create_checkout(
    request: Request,
    checkout_req: CreateCheckoutRequest,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Create a checkout session for upgrading to Premium.
    Returns checkout URL to open in overlay modal.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if already premium
        if user['role'] == UserRole.PREMIUM.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already subscribed to Premium. Use customer portal to change plan."
            )
        
        # Get pricing info
        billing_cycle = checkout_req.billing_cycle
        pricing_info = PRICING[billing_cycle]
        variant_id = pricing_info['variant_id']
        
        if not variant_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Variant ID not configured for {billing_cycle} plan"
            )
        
        # Create checkout session
        checkout_url = create_lemonsqueezy_checkout(
            user_email=user['email'],
            user_id=str(user['user_id']),
            variant_id=variant_id,
            billing_cycle=billing_cycle
        )
        
        logger.info(f"Checkout created for user {user['email']}: {billing_cycle}")
        
        return CheckoutResponse(
            checkout_url=checkout_url,
            billing_cycle=billing_cycle,
            price=pricing_info['price'],
            currency=pricing_info['currency']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create checkout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout: {str(e)}"
        )

@router.get(
    "/subscription",
    response_model=SubscriptionStatus,
    summary="Get Subscription Status",
    description="Get current subscription status and details"
)
@limiter.limit(rate_max)
async def get_subscription_status(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get current subscription status for authenticated user.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Determine plan based on role
        plan = "premium" if user['role'] == UserRole.PREMIUM.value else "basic"
        
        return SubscriptionStatus(
            plan=plan,
            status=user['subscription_status'] or 'none',
            billing_cycle=user['billing_cycle'],
            renews_at=user['subscription_renews_at'].isoformat() if user['subscription_renews_at'] else None,
            ends_at=user['subscription_ends_at'].isoformat() if user['subscription_ends_at'] else None,
            cancelled_at=user['subscription_cancelled_at'].isoformat() if user['subscription_cancelled_at'] else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get subscription error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get subscription status"
        )

@router.get(
    "/history",
    response_model=list[PaymentHistoryItem],
    summary="Get Payment History",
    description="Get payment history for authenticated user"
)
@limiter.limit(rate_max)
async def get_payment_history(
    request: Request,
    limit: int = 10,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get payment history for authenticated user.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        payment_id,
                        amount,
                        currency,
                        status,
                        billing_cycle,
                        payment_date,
                        invoice_url
                    FROM tbl_payment_history
                    WHERE user_id = %s
                    ORDER BY payment_date DESC
                    LIMIT %s
                    """,
                    (current_user["user_id"], limit)
                )
                payments = cur.fetchall()
        
        return [
            PaymentHistoryItem(
                payment_id=str(p['payment_id']),
                amount=float(p['amount']),
                currency=p['currency'],
                status=p['status'],
                billing_cycle=p['billing_cycle'],
                payment_date=p['payment_date'].isoformat(),
                invoice_url=p['invoice_url']
            )
            for p in payments
        ]
        
    except Exception as e:
        logger.error(f"Get payment history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get payment history"
        )

@router.get(
    "/portal",
    summary="Get Customer Portal Link",
    description="Get link to LemonSqueezy customer portal for subscription management"
)
@limiter.limit(rate_max)
async def get_customer_portal(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get link to LemonSqueezy customer portal.
    Users can manage subscriptions, update payment methods, view invoices, etc.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # LemonSqueezy customer portal URL
        portal_url = "https://app.lemonsqueezy.com/my-orders"
        
        return {
            "portal_url": portal_url,
            "message": "Visit this link to manage your subscription, update payment methods, and view invoices",
            "has_subscription": bool(user['subscription_id'])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get portal error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer portal"
        )

@router.get(
    "/info",
    summary="Get Complete Billing Info",
    description="Get subscription status, payment history, and portal link in one call"
)
@limiter.limit(rate_max)
async def get_billing_info(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """
    Get complete billing information for dashboard display.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get subscription status
        plan = "premium" if user['role'] == UserRole.PREMIUM.value else "basic"
        subscription = SubscriptionStatus(
            plan=plan,
            status=user['subscription_status'] or 'none',
            billing_cycle=user['billing_cycle'],
            renews_at=user['subscription_renews_at'].isoformat() if user['subscription_renews_at'] else None,
            ends_at=user['subscription_ends_at'].isoformat() if user['subscription_ends_at'] else None,
            cancelled_at=user['subscription_cancelled_at'].isoformat() if user['subscription_cancelled_at'] else None
        )
        
        # Get payment history
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        payment_id,
                        amount,
                        currency,
                        status,
                        billing_cycle,
                        payment_date,
                        invoice_url
                    FROM tbl_payment_history
                    WHERE user_id = %s
                    ORDER BY payment_date DESC
                    LIMIT 10
                    """,
                    (current_user["user_id"],)
                )
                payments = cur.fetchall()
        
        payment_history = [
            PaymentHistoryItem(
                payment_id=str(p['payment_id']),
                amount=float(p['amount']),
                currency=p['currency'],
                status=p['status'],
                billing_cycle=p['billing_cycle'],
                payment_date=p['payment_date'].isoformat(),
                invoice_url=p['invoice_url']
            )
            for p in payments
        ]
        
        return BillingInfo(
            subscription=subscription,
            payment_history=payment_history,
            portal_url="https://app.lemonsqueezy.com/my-orders"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get billing info error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get billing information"
        )

@router.get(
    "/pricing",
    summary="Get Pricing Information",
    description="Get current pricing for all plans"
)
async def get_pricing():
    """
    Get pricing information for all plans.
    Public endpoint - no authentication required.
    """
    return {
        "plans": {
            "basic": {
                "price": 0,
                "currency": "USD",
                "features": [
                    "25 results per request",
                    "Raw data access",
                    "Simple search",
                    "Current month data only"
                ]
            },
            "premium": {
                "monthly": {
                    "price": PRICING['monthly']['price'],
                    "currency": PRICING['monthly']['currency'],
                    "interval": "month"
                },
                "quarterly": {
                    "price": PRICING['quarterly']['price'],
                    "currency": PRICING['quarterly']['currency'],
                    "interval": "quarter",
                    "savings": PRICING['quarterly']['savings'],
                    "savings_text": f"Save ${PRICING['quarterly']['savings']} vs monthly"
                },
                "annual": {
                    "price": PRICING['annual']['price'],
                    "currency": PRICING['annual']['currency'],
                    "interval": "year",
                    "savings": PRICING['annual']['savings'],
                    "savings_text": f"Save ${PRICING['annual']['savings']} vs monthly"
                },
                "features": [
                    "5,000 results per request",
                    "Cleaned & normalized data",
                    "Advanced search with Boolean logic",
                    "6 months historical data",
                    "Priority support"
                ]
            }
        }
    }

# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@router.post(
    "/webhook",
    summary="LemonSqueezy Webhook",
    description="Handle webhook events from LemonSqueezy",
    include_in_schema=False  # Hide from public docs
)
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str = Header(None)
):
    """
    Handle incoming webhooks from LemonSqueezy.
    Verifies signature and processes subscription events.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify signature
        if not verify_webhook_signature(body, x_signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        # Parse payload
        payload = await request.json()
        
        event_name = payload.get('meta', {}).get('event_name')
        data = payload.get('data', {})
        
        if not event_name:
            logger.error("No event_name in webhook payload")
            return JSONResponse(content={"status": "error", "message": "No event_name"})
        
        logger.info(f"Received webhook: {event_name}")
        
        # Route to appropriate handler
        event_handlers = {
            'subscription_created': handle_subscription_created,
            'subscription_updated': handle_subscription_updated,
            'subscription_cancelled': handle_subscription_cancelled,
            'subscription_expired': handle_subscription_expired,
            'subscription_payment_success': handle_subscription_payment_success,
            'subscription_payment_failed': handle_subscription_payment_failed,
            'subscription_payment_recovered': handle_subscription_payment_recovered,
            'order_refunded': handle_order_refunded,
        }
        
        handler = event_handlers.get(event_name)
        
        if handler:
            # Process in background to return 200 quickly
            background_tasks.add_task(handler, data)
        else:
            logger.warning(f"No handler for webhook event: {event_name}")
        
        return JSONResponse(content={"status": "ok"})
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        # Still return 200 to prevent LemonSqueezy from retrying
        return JSONResponse(content={"status": "error", "message": str(e)})

@router.get(
    "/webhook/test",
    summary="Test Webhook Configuration",
    description="Check if webhook is configured correctly"
)
async def test_webhook():
    """
    Test endpoint to verify webhook configuration.
    """
    return {
        "webhook_endpoint": "/billing/webhook",
        "webhook_secret_configured": bool(API_LEMONSQUEEZY_WEBHOOK_SECRET),
        "supported_events": [
            "subscription_created",
            "subscription_updated",
            "subscription_cancelled",
            "subscription_expired",
            "subscription_payment_success",
            "subscription_payment_failed",
            "subscription_payment_recovered",
            "order_refunded"
        ],
        "note": "Configure this URL in your LemonSqueezy dashboard under Settings > Webhooks"
    }