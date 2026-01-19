"""
Billing Router
Handles LemonSqueezy checkout, webhooks, and subscription management
"""
import os
import hmac
import hashlib
import requests
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional, Dict, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Request, status, Depends, Header
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi import BackgroundTasks
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import (
    APP_GLOBALS,
    DB_CONFIG,
    API_LEMONSQUEEZY_API_KEY,
    API_LEMONSQUEEZY_STORE_ID,
    API_LEMONSQUEEZY_WEBHOOK_SECRET,
    PRICING,
    BILLING_TEST_MODE
)
from auth import UserRole
from auth_jwt import require_jwt_role, require_browser_auth
from utils_email import (
    send_subscription_welcome_email,
    send_payment_receipt_email,
    send_payment_failed_email,
    send_subscription_cancelled_email,
    send_subscription_expired_email,
    send_payment_recovered_email,
    send_refund_confirmation_email
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log test mode status at startup
if BILLING_TEST_MODE and 1 == 2:
    logger.warning("=" * 60)
    logger.warning("BILLING TEST MODE ENABLED - Test endpoints are active")
    logger.warning("Set BILLING_TEST_MODE=false in production!")
    logger.warning("=" * 60)

# Rate limiter
rate_max = "3000/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# Router
router = APIRouter(prefix="/v1/billing", tags=["Billing"])

# Test router - only created if test mode enabled (prevents duplicate tags in docs)
test_router = None
if BILLING_TEST_MODE:
    test_router = APIRouter(prefix="/v1/billing", tags=["Testing"])

# Templates
templates = Jinja2Templates(directory="templates")
templates.env.globals.update(APP_GLOBALS)

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

def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM tbl_users WHERE email = %s",
                (email.lower(),)
            )
            return cur.fetchone()

def get_user_email_by_id(user_id: str) -> Optional[str]:
    """Get user email by user_id for sending notifications"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT email FROM tbl_users WHERE user_id = %s",
                    (user_id,)
                )
                result = cur.fetchone()
                return result['email'] if result else None
    except Exception as e:
        logger.error(f"Error getting user email: {str(e)}")
        return None

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
    
    # Log the payload for debugging
    logger.info(f"[checkout] Payload: {json.dumps(payload, indent=2)}")
    
    try:
        logger.info(f"Creating LemonSqueezy checkout for user {user_id}, variant {variant_id}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        checkout_url = data["data"]["attributes"]["url"]
        
        logger.info(f"Checkout created successfully: {checkout_url[:50]}...")
        return checkout_url
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create LemonSqueezy checkout: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )

def get_lemonsqueezy_customer_portal_url(subscription_id: str) -> str:
    """
    Fetch signed customer portal URL from LemonSqueezy API.
    The signed URL auto-authenticates the customer and is valid for 24 hours.
    
    Args:
        subscription_id: LemonSqueezy subscription ID
        
    Returns:
        Signed customer portal URL or None if not available
    """
    url = f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}"
    
    headers = {
        "Authorization": f"Bearer {API_LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }
    
    try:
        logger.info(f"[portal] Fetching portal URL for subscription {subscription_id}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        urls = data.get('data', {}).get('attributes', {}).get('urls', {})
        portal_url = urls.get('customer_portal')
        
        if portal_url:
            logger.info(f"[portal] Got signed portal URL for subscription {subscription_id}")
            return portal_url
        else:
            logger.warning(f"[portal] No portal URL in response for subscription {subscription_id}")
            return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[portal] Failed to fetch portal URL: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"[portal] Response status: {e.response.status_code}")
        return None
    
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
    
    if not signature:
        logger.warning("No signature provided in webhook request")
        return False
    
    expected_signature = hmac.new(
        API_LEMONSQUEEZY_WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.warning(f"Signature mismatch. Expected: {expected_signature[:16]}..., Got: {signature[:16]}...")
    
    return is_valid

def cancel_lemonsqueezy_subscription(subscription_id: str) -> dict:
    """
    Cancel a subscription via LemonSqueezy API.
    
    Args:
        subscription_id: LemonSqueezy subscription ID
        
    Returns:
        dict with cancellation details or raises HTTPException
    """
    url = f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}"
    
    headers = {
        "Authorization": f"Bearer {API_LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }
    
    try:
        logger.info(f"[cancel] Cancelling subscription {subscription_id}")
        response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        attributes = data.get('data', {}).get('attributes', {})
        
        logger.info(f"[cancel] Subscription {subscription_id} cancelled successfully")
        
        return {
            "status": attributes.get('status'),
            "cancelled": attributes.get('cancelled'),
            "ends_at": attributes.get('ends_at')
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[cancel] Failed to cancel subscription: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"[cancel] Response status: {e.response.status_code}")
            logger.error(f"[cancel] Response body: {e.response.text}")
            
            # Handle specific error cases
            if e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subscription not found"
                )
            elif e.response.status_code == 422:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subscription cannot be cancelled (may already be cancelled)"
                )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription"
        )

# ============================================================================
# WEBHOOK EVENT HANDLERS - With Email Notifications
# ============================================================================

def handle_subscription_created(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_created webhook event.
    Upgrade user to PREMIUM role and send welcome email.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        subscription_id = data.get('id')
        customer_id = attributes.get('customer_id')
        renews_at = attributes.get('renews_at')
        
        logger.info(f"[subscription_created] Processing: user_id={user_id}, subscription_id={subscription_id}")
        
        if not user_id:
            logger.error("[subscription_created] No user_id in webhook custom_data")
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[subscription_created] SUCCESS: user={user_id} upgraded to PREMIUM, cycle={billing_cycle}")
            
            # Send welcome email
            user_email = get_user_email_by_id(user_id)
            if user_email:
                try:
                    send_subscription_welcome_email(
                        to_email=user_email,
                        billing_cycle=billing_cycle,
                        renews_at=renews_at_dt
                    )
                except Exception as email_err:
                    logger.error(f"[subscription_created] Failed to send welcome email: {str(email_err)}")
        else:
            logger.warning(f"[subscription_created] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[subscription_created] Error: {str(e)}", exc_info=True)


def handle_subscription_updated(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_updated webhook event.
    Update subscription details (renewal date, status, etc.)
    Note: No email for updates - these are typically background renewals
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        subscription_id = data.get('id')
        status_name = attributes.get('status')
        renews_at = attributes.get('renews_at')
        
        logger.info(f"[subscription_updated] Processing: user_id={user_id}, status={status_name}")
        
        if not user_id:
            logger.error("[subscription_updated] No user_id in webhook custom_data")
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[subscription_updated] SUCCESS: user={user_id}, new_status={status_name}")
        else:
            logger.warning(f"[subscription_updated] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[subscription_updated] Error: {str(e)}", exc_info=True)


def handle_subscription_cancelled(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_cancelled webhook event.
    Mark as cancelled but keep PREMIUM until end of billing period.
    Send cancellation confirmation email.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        subscription_id = data.get('id')
        ends_at = attributes.get('ends_at')  # When subscription access ends
        
        logger.info(f"[subscription_cancelled] Processing: user_id={user_id}, ends_at={ends_at}")
        
        if not user_id:
            logger.error("[subscription_cancelled] No user_id in webhook custom_data")
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[subscription_cancelled] SUCCESS: user={user_id}, access until={ends_at}")
            
            # Send cancellation confirmation email
            user_email = get_user_email_by_id(user_id)
            if user_email:
                try:
                    send_subscription_cancelled_email(
                        to_email=user_email,
                        ends_at=ends_at_dt
                    )
                except Exception as email_err:
                    logger.error(f"[subscription_cancelled] Failed to send email: {str(email_err)}")
        else:
            logger.warning(f"[subscription_cancelled] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[subscription_cancelled] Error: {str(e)}", exc_info=True)


def handle_subscription_expired(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_expired webhook event.
    Downgrade user to BASIC role and send expiration notification.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        
        logger.info(f"[subscription_expired] Processing: user_id={user_id}")
        
        if not user_id:
            logger.error("[subscription_expired] No user_id in webhook custom_data")
            return
        
        # Get user email before updating (for notification)
        user_email = get_user_email_by_id(user_id)
        
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[subscription_expired] SUCCESS: user={user_id} downgraded to BASIC")
            
            # Send expiration notification email
            if user_email:
                try:
                    send_subscription_expired_email(to_email=user_email)
                except Exception as email_err:
                    logger.error(f"[subscription_expired] Failed to send email: {str(email_err)}")
        else:
            logger.warning(f"[subscription_expired] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[subscription_expired] Error: {str(e)}", exc_info=True)


def handle_subscription_payment_success(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_payment_success webhook event.
    Record payment in payment history and send receipt email.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        
        # For subscription invoices, the ID is the invoice ID, subscription_id is in attributes
        subscription_id = attributes.get('subscription_id')
        order_id = str(data.get('id'))  # Use invoice ID as the order reference
        amount = attributes.get('total')
        currency = attributes.get('currency', 'USD')
        invoice_url = attributes.get('urls', {}).get('invoice_url')
        renews_at = attributes.get('renews_at')
        
        logger.info(f"[payment_success] Processing: user_id={user_id}, invoice_id={order_id}, amount={amount}")
        
        if not user_id or not order_id:
            logger.error("[payment_success] Missing user_id or order_id in webhook")
            return
        
        # Convert amount from cents to dollars
        amount_decimal = float(amount) / 100 if amount else 0
        
        # Parse renews_at for email
        renews_at_dt = None
        if renews_at:
            try:
                renews_at_dt = datetime.fromisoformat(renews_at.replace('Z', '+00:00'))
            except:
                pass
        
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
                rows_inserted = cur.rowcount
                conn.commit()
        
        if rows_inserted > 0:
            logger.info(f"[payment_success] SUCCESS: user={user_id}, amount=${amount_decimal} {currency}")
            
            # Send payment receipt email
            user_email = get_user_email_by_id(user_id)
            if user_email:
                try:
                    send_payment_receipt_email(
                        to_email=user_email,
                        amount=amount_decimal,
                        billing_cycle=billing_cycle,
                        order_id=order_id,
                        invoice_url=invoice_url,
                        next_billing_date=renews_at_dt
                    )
                except Exception as email_err:
                    logger.error(f"[payment_success] Failed to send receipt email: {str(email_err)}")
        else:
            logger.info(f"[payment_success] Payment already recorded for order_id={order_id}")
        
    except Exception as e:
        logger.error(f"[payment_success] Error: {str(e)}", exc_info=True)


def handle_subscription_payment_failed(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_payment_failed webhook event.
    Update subscription status to past_due and send warning email.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        amount = attributes.get('total')
        
        logger.info(f"[payment_failed] Processing: user_id={user_id}")
        
        if not user_id:
            logger.error("[payment_failed] No user_id in webhook custom_data")
            return
        
        # Get user email before updating
        user_email = get_user_email_by_id(user_id)
        
        # Convert amount from cents to dollars
        amount_decimal = float(amount) / 100 if amount else None
        
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.warning(f"[payment_failed] User {user_id} marked as past_due")
            
            # Send payment failed warning email
            if user_email:
                try:
                    send_payment_failed_email(
                        to_email=user_email,
                        amount=amount_decimal,
                        billing_cycle=billing_cycle
                    )
                except Exception as email_err:
                    logger.error(f"[payment_failed] Failed to send warning email: {str(email_err)}")
        else:
            logger.warning(f"[payment_failed] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[payment_failed] Error: {str(e)}", exc_info=True)


def handle_subscription_payment_recovered(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_payment_recovered webhook event.
    Update subscription status back to active and send recovery notification.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        billing_cycle = custom_data.get('billing_cycle', 'monthly')
        amount = attributes.get('total')
        renews_at = attributes.get('renews_at')
        
        logger.info(f"[payment_recovered] Processing: user_id={user_id}")
        
        if not user_id:
            logger.error("[payment_recovered] No user_id in webhook custom_data")
            return
        
        # Get user email
        user_email = get_user_email_by_id(user_id)
        
        # Convert amount from cents to dollars
        amount_decimal = float(amount) / 100 if amount else 0
        
        # Parse renews_at
        renews_at_dt = None
        if renews_at:
            try:
                renews_at_dt = datetime.fromisoformat(renews_at.replace('Z', '+00:00'))
            except:
                pass
        
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[payment_recovered] SUCCESS: user={user_id} restored to active")
            
            # Send payment recovered notification
            if user_email:
                try:
                    send_payment_recovered_email(
                        to_email=user_email,
                        amount=amount_decimal,
                        billing_cycle=billing_cycle,
                        next_billing_date=renews_at_dt
                    )
                except Exception as email_err:
                    logger.error(f"[payment_recovered] Failed to send email: {str(email_err)}")
        else:
            logger.warning(f"[payment_recovered] No user found with user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[payment_recovered] Error: {str(e)}", exc_info=True)


def handle_subscription_payment_refunded(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle subscription_payment_refunded webhook event.
    Record refund for a recurring subscription payment and send confirmation.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        order_id = str(data.get('id'))  # Invoice ID
        refunded_amount = attributes.get('refunded_amount') or attributes.get('total')
        original_amount = attributes.get('total')
        
        logger.info(f"[subscription_payment_refunded] Processing: user_id={user_id}, order_id={order_id}")
        
        if not user_id or not order_id:
            logger.error("[subscription_payment_refunded] Missing user_id or order_id")
            return
        
        # Get user email
        user_email = get_user_email_by_id(user_id)
        
        # Convert amounts from cents to dollars
        refunded_decimal = float(refunded_amount) / 100 if refunded_amount else 0
        original_decimal = float(original_amount) / 100 if original_amount else refunded_decimal
        
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[subscription_payment_refunded] SUCCESS: order={order_id}, refund=${refunded_decimal}")
            
            # Send refund confirmation email
            if user_email:
                try:
                    send_refund_confirmation_email(
                        to_email=user_email,
                        refund_amount=refunded_decimal,
                        original_amount=original_decimal,
                        order_id=order_id,
                        subscription_cancelled=False
                    )
                except Exception as email_err:
                    logger.error(f"[subscription_payment_refunded] Failed to send email: {str(email_err)}")
        else:
            logger.warning(f"[subscription_payment_refunded] No payment found for order_id={order_id}")
        
    except Exception as e:
        logger.error(f"[subscription_payment_refunded] Error: {str(e)}", exc_info=True)


def handle_order_refunded(data: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    """
    Handle order_refunded webhook event.
    Record refund for the initial order and send confirmation.
    This typically means a full cancellation + refund scenario.
    """
    try:
        attributes = data.get('attributes', {})
        meta = meta or {}
        
        # custom_data is in meta, not attributes
        custom_data = meta.get('custom_data', {})
        
        user_id = custom_data.get('user_id')
        order_id = str(data.get('id'))
        refunded_amount = attributes.get('refunded_amount')
        total_amount = attributes.get('total')
        
        logger.info(f"[order_refunded] Processing: user_id={user_id}, order_id={order_id}")
        
        if not user_id or not order_id:
            logger.error("[order_refunded] Missing user_id or order_id")
            return
        
        # Get user email
        user_email = get_user_email_by_id(user_id)
        
        # Convert amounts from cents to dollars
        refunded_decimal = float(refunded_amount) / 100 if refunded_amount else 0
        original_decimal = float(total_amount) / 100 if total_amount else refunded_decimal
        
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
                rows_updated = cur.rowcount
                conn.commit()
        
        if rows_updated > 0:
            logger.info(f"[order_refunded] SUCCESS: order={order_id}, refund=${refunded_decimal}")
            
            # Send refund confirmation email (likely with subscription cancelled)
            if user_email:
                try:
                    send_refund_confirmation_email(
                        to_email=user_email,
                        refund_amount=refunded_decimal,
                        original_amount=original_decimal,
                        order_id=order_id,
                        subscription_cancelled=True  # Initial order refund usually means cancellation
                    )
                except Exception as email_err:
                    logger.error(f"[order_refunded] Failed to send email: {str(email_err)}")
        else:
            logger.warning(f"[order_refunded] No payment found for order_id={order_id}")
        
    except Exception as e:
        logger.error(f"[order_refunded] Error: {str(e)}", exc_info=True)

# ============================================================================
# BILLING ENDPOINTS
# ============================================================================

@router.post(
    "/create_checkout",
    response_model=CheckoutResponse,
    summary="Create Checkout Session",
    description=""
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
        
        # For active PREMIUM users, redirect to customer portal to change plan
        # Cancelled/expired PREMIUM users should create a new checkout to resubscribe
        subscription_status = user.get('subscription_status')
        is_active_premium = (
            user['role'] == UserRole.PREMIUM.value and 
            subscription_status not in ['cancelled', 'expired']
        )
        
        if is_active_premium:
            subscription_id = user.get('lemonsqueezy_subscription_id')
            
            if not subscription_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active subscription found. Please contact support."
                )
            
            # Get portal URL for plan changes
            portal_url = get_lemonsqueezy_customer_portal_url(subscription_id)
            
            if not portal_url:
                # Fallback to generic my-orders page (handles test subscriptions)
                logger.warning(f"[create_checkout] Using fallback portal URL for user {user['email']}")
                portal_url = "https://app.lemonsqueezy.com/my-orders"
            
            # Return portal URL in same format so modal opens it
            billing_cycle = checkout_req.billing_cycle
            pricing_info = PRICING[billing_cycle]
            
            logger.info(f"Premium user {user['email']} redirected to portal for plan change")
            
            return CheckoutResponse(
                checkout_url=portal_url,
                billing_cycle=billing_cycle,
                price=pricing_info['price'],
                currency=pricing_info['currency']
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
        logger.error(f"Create checkout error: {str(e)}", exc_info=True)
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
        logger.error(f"Get subscription error: {str(e)}", exc_info=True)
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
                    LIMIT 250
                    """,
                    (current_user["user_id"], 250)
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
        logger.error(f"Get payment history error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get payment history"
        )

@router.get(
    "/portal",
    summary="Get Customer Portal Link",
    description="Get signed link to LemonSqueezy customer portal for subscription management"
    )
@limiter.limit(rate_max)
async def get_customer_portal(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """
    Get signed link to LemonSqueezy customer portal.
    Users can manage subscriptions, update payment methods, view invoices, cancel, etc.
    
    The signed URL auto-authenticates the user and is valid for 24 hours.
    Can be opened in a LemonSqueezy overlay using LemonSqueezy.Url.Open().
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        subscription_id = user.get('lemonsqueezy_subscription_id')
        
        if not subscription_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found"
            )
        
        # Fetch signed portal URL from LemonSqueezy API
        portal_url = get_lemonsqueezy_customer_portal_url(subscription_id)
        
        if not portal_url:
            # Fallback to generic my-orders page
            logger.warning(f"[portal] Using fallback URL for user {user['email']}")
            portal_url = "https://app.lemonsqueezy.com/my-orders"
        
        return {
            "portal_url": portal_url,
            "message": "Manage your subscription, update payment methods, and view invoices",
            "has_subscription": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get portal error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer portal"
        )
    
@router.post(
    "/cancel",
    summary="Cancel Subscription",
    description="Cancel the current Premium subscription. Access continues until end of billing period."
)
@limiter.limit(rate_max)
async def cancel_subscription(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
):
    """
    Cancel the authenticated user's Premium subscription.
    
    The subscription will remain active until the end of the current billing period.
    A webhook will be received from LemonSqueezy to update the subscription status.
    """
    try:
        user = get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if user has an active subscription
        subscription_id = user.get('lemonsqueezy_subscription_id')
        subscription_status = user.get('subscription_status')
        
        if not subscription_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found"
            )
        
        if subscription_status == 'cancelled':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription is already cancelled"
            )
        
        if subscription_status == 'expired':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription has already expired"
            )
        
        # Cancel via LemonSqueezy API
        result = cancel_lemonsqueezy_subscription(subscription_id)
        
        logger.info(f"[cancel] User {user['email']} cancelled subscription {subscription_id}")
        
        # Note: The webhook handler will update the database when LemonSqueezy
        # sends the subscription_cancelled event. We don't update here to avoid
        # race conditions and ensure single source of truth.
        
        return {
            "status": "success",
            "message": "Subscription cancelled successfully",
            "ends_at": result.get('ends_at'),
            "note": "You will retain Premium access until the end of your current billing period"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cancel] Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
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
        # Determine plan based on role
        if user['role'] == UserRole.ADMIN.value:
            plan = "admin"
        elif user['role'] == UserRole.PREMIUM.value:
            plan = "premium"
        else:
            plan = "basic"
            
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
        
        # Check if user is an admin
        is_admin = user['role'] == UserRole.ADMIN.value
        
        return {
            "subscription": subscription.model_dump(),
            "payment_history": [p.model_dump() for p in payment_history],
            "portal_url": "https://app.lemonsqueezy.com/my-orders",
            "is_admin": is_admin
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get billing info error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get billing information"
        )

# ============================================================================
# BILLING DASHBOARD PAGE
# ============================================================================

@router.get(
    "",
    response_class=HTMLResponse,
    include_in_schema=False
)
@limiter.limit(rate_max)
async def billing_redirect(request: Request):
    """Redirect /v1/billing to /v1/billing/ for consistency"""
    return RedirectResponse(url="/v1/billing/", status_code=301)

@router.get(
    "/",
    response_class=HTMLResponse,
    summary="Billing Dashboard Page",
    description="Serve the billing dashboard HTML page",
    include_in_schema=False  # Hide from API docs since it's a web page
)
@limiter.limit(rate_max)
async def billing_dashboard_page(
    request: Request,
    current_user: Optional[dict] = Depends(require_browser_auth(UserRole.BASIC))
):
    """
    Billing Dashboard - View subscription and payment history.
    Requires authentication - redirects to login if not authenticated.
    """
    # If not authenticated, redirect to login page
    if not current_user:
        return RedirectResponse(url="/v1/auth/login", status_code=303)
    
    return templates.TemplateResponse(
        "billing/billing.html",
        {
            "request": request,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user_role": request.state.user_role,
            "is_admin": request.state.user_role == UserRole.ADMIN.value
        }
    )

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
        
        logger.info(f"[webhook] Received webhook, body size: {len(body)} bytes")
        
        # Verify signature
        if not verify_webhook_signature(body, x_signature):
            logger.warning("[webhook] Invalid signature - rejecting request")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        # Parse payload
        payload = await request.json()
        
        event_name = payload.get('meta', {}).get('event_name')
        data = payload.get('data', {})
        
        if not event_name:
            logger.error("[webhook] No event_name in payload")
            return JSONResponse(content={"status": "error", "message": "No event_name"})
        
        logger.info(f"[webhook] Event: {event_name}, data_id: {data.get('id', 'N/A')}")
        
        # Log full payload in test mode for debugging
        if BILLING_TEST_MODE:
            logger.info(f"[webhook] Full payload: {json.dumps(payload, indent=2)}")
        
        # Route to appropriate handler
        event_handlers = {
            'subscription_created': handle_subscription_created,
            'subscription_updated': handle_subscription_updated,
            'subscription_cancelled': handle_subscription_cancelled,
            'subscription_expired': handle_subscription_expired,
            'subscription_payment_success': handle_subscription_payment_success,
            'subscription_payment_failed': handle_subscription_payment_failed,
            'subscription_payment_recovered': handle_subscription_payment_recovered,
            'subscription_payment_refunded': handle_subscription_payment_refunded,
            'order_refunded': handle_order_refunded,
        }
        
        handler = event_handlers.get(event_name)
        
        if handler:
            # Extract meta for custom_data - LemonSqueezy puts custom_data in meta, not data.attributes
            meta = payload.get('meta', {})
            # Process in background to return 200 quickly
            background_tasks.add_task(handler, data, meta)
            logger.info(f"[webhook] Queued handler for: {event_name}")
        else:
            logger.warning(f"[webhook] No handler for event: {event_name}")
        
        return JSONResponse(content={"status": "ok"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[webhook] Error: {str(e)}", exc_info=True)
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
        "webhook_endpoint": "/v1/billing/webhook",
        "webhook_secret_configured": bool(API_LEMONSQUEEZY_WEBHOOK_SECRET),
        "test_mode_enabled": BILLING_TEST_MODE,
        "supported_events": [
            "subscription_created",
            "subscription_updated",
            "subscription_cancelled",
            "subscription_expired",
            "subscription_payment_success",
            "subscription_payment_failed",
            "subscription_payment_recovered",
            "subscription_payment_refunded",
            "order_refunded"
        ],
        "note": "Configure this URL in your LemonSqueezy dashboard under Settings > Webhooks"
    }

# ============================================================================
# TEST MODE ENDPOINTS
# Only available when BILLING_TEST_MODE=true
# ============================================================================

if BILLING_TEST_MODE:
    
    class SimulateWebhookRequest(BaseModel):
        """Request to simulate a webhook event"""
        event_name: Literal[
            "subscription_created",
            "subscription_updated",
            "subscription_cancelled",
            "subscription_expired",
            "subscription_payment_success",
            "subscription_payment_failed",
            "subscription_payment_recovered",
            "subscription_payment_refunded",
            "order_refunded"
        ] = Field(..., description="Webhook event to simulate")
        user_email: str = Field(..., description="Email of user to affect")
        billing_cycle: Literal["monthly", "quarterly", "annual"] = Field(
            default="monthly",
            description="Billing cycle for the subscription"
        )
        amount_cents: int = Field(
            default=999,
            description="Amount in cents (e.g., 999 = $9.99)"
        )
    
    @router.post(
        "/test/simulate-webhook",
        summary="[TEST] Simulate Webhook Event",
        description="Simulate a LemonSqueezy webhook event for testing. Only available in test mode.",
        tags=["Testing"]
    )
    async def simulate_webhook(
        request: Request,
        sim_req: SimulateWebhookRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Simulate a webhook event for testing purposes.
        This bypasses signature verification and creates fake webhook data.
        """
        # Find user by email
        user = get_user_by_email(sim_req.user_email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {sim_req.user_email}"
            )
        
        user_id = str(user['user_id'])
        
        # Generate fake IDs for the simulation
        fake_subscription_id = f"test_sub_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fake_order_id = f"test_order_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fake_customer_id = f"test_cust_{user_id[:8]}"
        
        # Calculate renewal date based on billing cycle
        now = datetime.now(timezone.utc)
        if sim_req.billing_cycle == "monthly":
            renews_at = now + timedelta(days=30)
        elif sim_req.billing_cycle == "quarterly":
            renews_at = now + timedelta(days=90)
        else:  # annual
            renews_at = now + timedelta(days=365)
        
        # Build simulated webhook data based on event type
        simulated_data = {
            "id": fake_subscription_id,
            "attributes": {
                "custom_data": {
                    "user_id": user_id,
                    "billing_cycle": sim_req.billing_cycle
                },
                "customer_id": fake_customer_id,
                "status": "active",
                "renews_at": renews_at.isoformat(),
                "ends_at": renews_at.isoformat(),
                "total": sim_req.amount_cents,
                "currency": "USD",
                "first_order_id": fake_order_id,
                "order_id": fake_order_id,
                "refunded_amount": sim_req.amount_cents,
                "urls": {
                    "customer_portal": "https://app.lemonsqueezy.com/my-orders"
                }
            }
        }
        
        # Route to appropriate handler
        event_handlers = {
            'subscription_created': handle_subscription_created,
            'subscription_updated': handle_subscription_updated,
            'subscription_cancelled': handle_subscription_cancelled,
            'subscription_expired': handle_subscription_expired,
            'subscription_payment_success': handle_subscription_payment_success,
            'subscription_payment_failed': handle_subscription_payment_failed,
            'subscription_payment_recovered': handle_subscription_payment_recovered,
            'subscription_payment_refunded': handle_subscription_payment_refunded,
            'order_refunded': handle_order_refunded,
        }
        
        handler = event_handlers.get(sim_req.event_name)
        
        if handler:
            # Build simulated meta (where LemonSqueezy puts custom_data)
            simulated_meta = {
                "test_mode": True,
                "event_name": sim_req.event_name,
                "custom_data": {
                    "user_id": user_id,
                    "billing_cycle": sim_req.billing_cycle
                }
            }
            
            # Execute handler directly (not in background for immediate feedback)
            handler(simulated_data, simulated_meta)
            
            logger.info(f"[TEST] Simulated {sim_req.event_name} for user {sim_req.user_email}")
            
            return {
                "status": "success",
                "message": f"Simulated {sim_req.event_name} event",
                "event_name": sim_req.event_name,
                "user_email": sim_req.user_email,
                "user_id": user_id,
                "simulated_data": {
                    "subscription_id": fake_subscription_id,
                    "order_id": fake_order_id,
                    "billing_cycle": sim_req.billing_cycle,
                    "amount": f"${sim_req.amount_cents / 100:.2f}"
                }
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown event: {sim_req.event_name}"
            )
    
    @router.get(
        "/test/user-status/{email}",
        summary="[TEST] Get User Subscription Status",
        description="Get detailed subscription status for a user by email. Only available in test mode.",
        tags=["Testing"]
    )
    async def test_get_user_status(email: str):
        """
        Get detailed subscription info for testing purposes.
        """
        user = get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {email}"
            )
        
        # Get payment history
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM tbl_payment_history
                    WHERE user_id = %s
                    ORDER BY payment_date DESC
                    LIMIT 5
                    """,
                    (str(user['user_id']),)
                )
                payments = cur.fetchall()
        
        return {
            "user": {
                "user_id": str(user['user_id']),
                "email": user['email'],
                "role": user['role'],
                "is_active": user['is_active']
            },
            "subscription": {
                "subscription_id": user['subscription_id'],
                "subscription_status": user['subscription_status'],
                "subscription_plan": user['subscription_plan'],
                "billing_cycle": user['billing_cycle'],
                "renews_at": user['subscription_renews_at'].isoformat() if user['subscription_renews_at'] else None,
                "ends_at": user['subscription_ends_at'].isoformat() if user['subscription_ends_at'] else None,
                "cancelled_at": user['subscription_cancelled_at'].isoformat() if user['subscription_cancelled_at'] else None,
                "lemonsqueezy_customer_id": user['lemonsqueezy_customer_id'],
                "lemonsqueezy_subscription_id": user['lemonsqueezy_subscription_id']
            },
            "recent_payments": [
                {
                    "payment_id": str(p['payment_id']),
                    "amount": float(p['amount']),
                    "currency": p['currency'],
                    "status": p['status'],
                    "billing_cycle": p['billing_cycle'],
                    "payment_date": p['payment_date'].isoformat() if p['payment_date'] else None,
                    "refund_amount": float(p['refund_amount']) if p['refund_amount'] else None,
                    "refunded_at": p['refunded_at'].isoformat() if p['refunded_at'] else None
                }
                for p in payments
            ]
        }
    
    @router.post(
        "/test/reset-user/{email}",
        summary="[TEST] Reset User to Basic",
        description="Reset a user's subscription back to Basic for testing. Only available in test mode.",
        tags=["Testing"]
    )
    async def test_reset_user(email: str):
        """
        Reset a user back to BASIC role with no subscription.
        Useful for re-testing the subscription flow.
        """
        user = get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {email}"
            )
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Reset user subscription fields
                cur.execute(
                    """
                    UPDATE tbl_users
                    SET role = %s,
                        subscription_id = NULL,
                        subscription_status = NULL,
                        subscription_plan = NULL,
                        subscription_renews_at = NULL,
                        subscription_ends_at = NULL,
                        subscription_cancelled_at = NULL,
                        billing_cycle = NULL,
                        lemonsqueezy_customer_id = NULL,
                        lemonsqueezy_subscription_id = NULL,
                        updated_at = NOW()
                    WHERE email = %s
                    """,
                    (UserRole.BASIC.value, email.lower())
                )
                
                # Optionally clear payment history for this user
                cur.execute(
                    """
                    DELETE FROM tbl_payment_history
                    WHERE user_id = %s
                    """,
                    (str(user['user_id']),)
                )
                deleted_payments = cur.rowcount
                
                conn.commit()
        
        logger.info(f"[TEST] Reset user {email} to BASIC, deleted {deleted_payments} payment records")
        
        return {
            "status": "success",
            "message": f"User {email} reset to BASIC",
            "payments_deleted": deleted_payments
        }
    
    class SendTestEmailRequest(BaseModel):
        """Request to send/preview a test email"""
        email_type: Literal[
            "subscription_welcome",
            "payment_receipt",
            "payment_failed",
            "subscription_cancelled",
            "subscription_expired",
            "payment_recovered",
            "refund_confirmation"
        ] = Field(..., description="Type of email to send/preview")
        user_email: str = Field(..., description="Email address to send to")
        billing_cycle: Literal["monthly", "quarterly", "annual"] = Field(
            default="monthly",
            description="Billing cycle for email content"
        )
        amount: float = Field(default=9.99, description="Amount in dollars")
        renews_at: Optional[str] = Field(default=None, description="Renewal date ISO string")
        ends_at: Optional[str] = Field(default=None, description="End date ISO string")
        order_id: Optional[str] = Field(default=None, description="Order/invoice ID")
        preview_only: bool = Field(default=False, description="If true, return HTML instead of sending")
    
    @router.post(
        "/test/send-email",
        summary="[TEST] Send or Preview Billing Email",
        description="Send a billing email or get HTML preview. Only available in test mode.",
        tags=["Testing"]
    )
    async def test_send_email(req: SendTestEmailRequest):
        """
        Send or preview a billing email for testing purposes.
        If preview_only=true, returns the rendered HTML instead of sending.
        """
        from utils_email import (
            send_subscription_welcome_email,
            send_payment_receipt_email,
            send_payment_failed_email,
            send_subscription_cancelled_email,
            send_subscription_expired_email,
            send_payment_recovered_email,
            send_refund_confirmation_email,
            templates as email_templates,
            EmailConfig
        )
        
        # Parse dates
        renews_at_dt = None
        ends_at_dt = None
        
        if req.renews_at:
            try:
                renews_at_dt = datetime.fromisoformat(req.renews_at.replace('Z', '+00:00'))
            except:
                renews_at_dt = datetime.now(timezone.utc) + timedelta(days=30)
        else:
            renews_at_dt = datetime.now(timezone.utc) + timedelta(days=30)
        
        if req.ends_at:
            try:
                ends_at_dt = datetime.fromisoformat(req.ends_at.replace('Z', '+00:00'))
            except:
                ends_at_dt = datetime.now(timezone.utc) + timedelta(days=30)
        else:
            ends_at_dt = datetime.now(timezone.utc) + timedelta(days=30)
        
        order_id = req.order_id or f"test_order_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Build context for template rendering
        def format_date(dt):
            if dt is None:
                return "N/A"
            return dt.strftime("%B %d, %Y")
        
        base_context = {
            "header_title": "",
            "year": datetime.now().year,
            "billing_cycle": req.billing_cycle,
            "amount": f"{req.amount:.2f}",
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        # Template and context mapping
        email_configs = {
            "subscription_welcome": {
                "template": "emails/subscription_welcome.html",
                "context": {
                    **base_context,
                    "header_title": "Welcome to Premium!",
                    "renews_at": format_date(renews_at_dt)
                },
                "send_func": lambda: send_subscription_welcome_email(
                    req.user_email, req.billing_cycle, renews_at_dt
                )
            },
            "payment_receipt": {
                "template": "emails/payment_receipt.html",
                "context": {
                    **base_context,
                    "header_title": "Payment Receipt",
                    "payment_date": format_date(datetime.now(timezone.utc)),
                    "order_id": order_id,
                    "invoice_url": None,
                    "next_billing_date": format_date(renews_at_dt)
                },
                "send_func": lambda: send_payment_receipt_email(
                    req.user_email, req.amount, req.billing_cycle, 
                    order_id, None, renews_at_dt
                )
            },
            "payment_failed": {
                "template": "emails/payment_failed.html",
                "context": {
                    **base_context,
                    "header_title": "Payment Failed"
                },
                "send_func": lambda: send_payment_failed_email(
                    req.user_email, req.amount, req.billing_cycle
                )
            },
            "subscription_cancelled": {
                "template": "emails/subscription_cancelled.html",
                "context": {
                    **base_context,
                    "header_title": "Subscription Cancelled",
                    "ends_at": format_date(ends_at_dt)
                },
                "send_func": lambda: send_subscription_cancelled_email(
                    req.user_email, ends_at_dt
                )
            },
            "subscription_expired": {
                "template": "emails/subscription_expired.html",
                "context": {
                    **base_context,
                    "header_title": "Subscription Ended"
                },
                "send_func": lambda: send_subscription_expired_email(req.user_email)
            },
            "payment_recovered": {
                "template": "emails/payment_recovered.html",
                "context": {
                    **base_context,
                    "header_title": "Payment Recovered",
                    "next_billing_date": format_date(renews_at_dt)
                },
                "send_func": lambda: send_payment_recovered_email(
                    req.user_email, req.amount, req.billing_cycle, renews_at_dt
                )
            },
            "refund_confirmation": {
                "template": "emails/refund_confirmation.html",
                "context": {
                    **base_context,
                    "header_title": "Refund Processed",
                    "refund_amount": f"{req.amount:.2f}",
                    "original_amount": f"{req.amount:.2f}",
                    "refund_date": format_date(datetime.now(timezone.utc)),
                    "order_id": order_id,
                    "subscription_cancelled": False
                },
                "send_func": lambda: send_refund_confirmation_email(
                    req.user_email, req.amount, req.amount, order_id, False
                )
            }
        }
        
        config = email_configs.get(req.email_type)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown email type: {req.email_type}"
            )
        
        if req.preview_only:
            # Render template and return HTML
            try:
                html_content = email_templates.get_template(config["template"]).render(config["context"])
                
                logger.info(f"[TEST] Generated email preview: {req.email_type}")
                
                return {
                    "status": "preview",
                    "email_type": req.email_type,
                    "html": html_content
                }
            except Exception as e:
                logger.error(f"[TEST] Failed to render email template: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to render template: {str(e)}"
                )
        else:
            # Actually send the email
            try:
                success = config["send_func"]()
                
                if success:
                    logger.info(f"[TEST] Sent {req.email_type} email to {req.user_email}")
                    return {
                        "status": "sent",
                        "email_type": req.email_type,
                        "to": req.user_email
                    }
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to send email"
                    )
            except Exception as e:
                logger.error(f"[TEST] Failed to send email: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to send email: {str(e)}"
                )