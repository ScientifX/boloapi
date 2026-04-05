"""
Email Utility Module - Extended with Billing Notification Emails
Sends emails via Microsoft Graph API (Microsoft 365)
Uses Jinja2 templates for email content
"""

import os
import requests
from typing import Optional
from datetime import datetime, timedelta, timezone
import logging
from fastapi.templating import Jinja2Templates
from config import (
    API_AZURE_CLIENT_ID,
    API_AZURE_CLIENT_SECRET,
    API_AZURE_TENANT_ID,
    API_EMAIL_FROM_ADDRESS,
    API_EMAIL_FROM_NAME,
    API_EMAIL_BCC_SUPPORT,
    API_APP_BASE_URL,
    APP_GLOBALS,
    PRICING
    )

# Configure logging 
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Jinja2 templates for emails
templates = Jinja2Templates(directory="templates")
# Inject global app variables so all email templates can access app_name,
# beta_mode, and other APP_GLOBALS values without explicit context passing.
templates.env.globals.update(APP_GLOBALS)


class EmailConfig:
    """Email configuration from environment variables"""
    
    TENANT_ID = API_AZURE_TENANT_ID
    CLIENT_ID = API_AZURE_CLIENT_ID
    CLIENT_SECRET = API_AZURE_CLIENT_SECRET
    FROM_ADDRESS = API_EMAIL_FROM_ADDRESS
    FROM_NAME = API_EMAIL_FROM_NAME
    APP_BASE_URL = API_APP_BASE_URL
    SUPPORT_EMAIL = APP_GLOBALS.get('support_email')
    BCC_SUPPORT_ENABLED = API_EMAIL_BCC_SUPPORT
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if all required configuration is present"""
        return all([
            cls.TENANT_ID,
            cls.CLIENT_ID,
            cls.CLIENT_SECRET,
            cls.FROM_ADDRESS
        ])
    
    @classmethod
    def get_missing_config(cls) -> list:
        """Get list of missing configuration variables"""
        missing = []
        if not cls.TENANT_ID:
            missing.append("API_AZURE_TENANT_ID")
        if not cls.CLIENT_ID:
            missing.append("API_AZURE_CLIENT_ID")
        if not cls.CLIENT_SECRET:
            missing.append("API_AZURE_CLIENT_SECRET")
        if not cls.FROM_ADDRESS:
            missing.append("API_EMAIL_FROM_ADDRESS")
        if not cls.FROM_NAME:
            missing.append("API_EMAIL_FROM_NAME")
        return missing


class GraphAPIEmailSender:
    """Send emails using Microsoft Graph API"""
    
    def __init__(self):
        self.token_cache = None
        self.token_expires_at = None
    
    def _get_access_token(self) -> str:
        """
        Get OAuth2 access token for Microsoft Graph API
        Uses client credentials flow (app-only authentication)
        """
        # Check cache
        if self.token_cache and self.token_expires_at:
            if datetime.now(timezone.utc) < self.token_expires_at:
                return self.token_cache
        
        # Request new token
        url = f"https://login.microsoftonline.com/{EmailConfig.TENANT_ID}/oauth2/v2.0/token"
        
        data = {
            "client_id": EmailConfig.CLIENT_ID,
            "client_secret": EmailConfig.CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        logger.info(f"Requesting Microsoft Graph API token")
        
        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self.token_cache = token_data["access_token"]
            # Cache for slightly less than expiration time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
            
            logger.info("Successfully obtained Microsoft Graph API access token")
            return self.token_cache
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get access token: {str(e)}")
            # Log the actual error response from Microsoft
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Microsoft error response: {error_detail}")
                except:
                    logger.error(f"Microsoft error response (raw): {e.response.text}")
            raise Exception(f"Failed to authenticate with Microsoft Graph API: {str(e)}")
    
    def send_email(
        self,
        to_address: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None
    ) -> bool:
        """
        Send an email via Microsoft Graph API
        
        Args:
            to_address: Recipient email address
            subject: Email subject line
            body_html: HTML body content
            body_text: Plain text body content (optional, falls back to HTML)
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not EmailConfig.is_configured():
            missing = EmailConfig.get_missing_config()
            logger.error(f"Email not configured. Missing: {', '.join(missing)}")
            return False
        
        try:
            access_token = self._get_access_token()
            
            # Build email message
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body_html
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": to_address
                            }
                        }
                    ]
                },
                "saveToSentItems": "true"
            }
            
            # BCC support address on all outgoing user notifications.
            # Skipped if disabled via API_EMAIL_BCC_SUPPORT=false, or if the
            # recipient is already the support address (e.g. feedback emails).
            if (
                EmailConfig.BCC_SUPPORT_ENABLED
                and EmailConfig.SUPPORT_EMAIL
                and to_address.lower() != EmailConfig.SUPPORT_EMAIL.lower()
            ):
                message["message"]["bccRecipients"] = [
                    {
                        "emailAddress": {
                            "address": EmailConfig.SUPPORT_EMAIL
                        }
                    }
                ]
            
            # Send email
            url = f"https://graph.microsoft.com/v1.0/users/{EmailConfig.FROM_ADDRESS}/sendMail"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=message, headers=headers, timeout=10)
            response.raise_for_status()
            
            bcc_applied = (
                EmailConfig.BCC_SUPPORT_ENABLED
                and EmailConfig.SUPPORT_EMAIL
                and to_address.lower() != EmailConfig.SUPPORT_EMAIL.lower()
            )
            bcc_info = f" (BCC: {EmailConfig.SUPPORT_EMAIL})" if bcc_applied else ""
            logger.info(f"Successfully sent email to {to_address}{bcc_info}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send email to {to_address}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {str(e)}")
            return False


# Global email sender instance
_email_sender = None

def get_email_sender() -> GraphAPIEmailSender:
    """Get or create email sender instance"""
    global _email_sender
    if _email_sender is None:
        _email_sender = GraphAPIEmailSender()
    return _email_sender


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_date(dt: datetime) -> str:
    """Format datetime for display in emails"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    return dt.strftime("%B %d, %Y")

def format_datetime(dt: datetime) -> str:
    """Format datetime with time for display in emails"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    return dt.strftime("%B %d, %Y at %I:%M %p UTC")

def get_price_for_cycle(billing_cycle: str) -> float:
    """Get price for a billing cycle from config"""
    cycle_info = PRICING.get(billing_cycle, PRICING.get('monthly'))
    return cycle_info.get('price', 9.99)


# ============================================================================
# ACCOUNT EMAIL TEMPLATE FUNCTIONS
# ============================================================================

def send_activation_email(to_email: str, activation_token: str) -> bool:
    """
    Send account activation email with activation link using Jinja2 template
    
    Args:
        to_email: Recipient email address
        activation_token: Unique activation token
    
    Returns:
        bool: True if email sent successfully
    """
    activation_link = f"{EmailConfig.APP_BASE_URL}/v1/auth/activate?token={activation_token}"
    
    subject = f"Activate Your {APP_GLOBALS.get('app_name')} Account"
    
    # Render template
    try:
        # Create a mock request object for template rendering
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "activation_link": activation_link,
            "header_title": f"Welcome to {APP_GLOBALS.get('app_name')}",
            "year": datetime.now().year
        }
        
        # Render the template
        html_body = templates.get_template("emails/activation.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering activation email template: {str(e)}")
        return False


def send_api_key_email(to_email: str, api_key: str) -> bool:
    """
    Send API key reset email with new key using Jinja2 template
    
    Args:
        to_email: Recipient email address
        api_key: New API key
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Your New {APP_GLOBALS.get('app_name')} API Key"
    
    # Render template
    try:
        context = {
            "api_key": api_key,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "API Key Reset",
            "year": datetime.now().year
        }
        
        # Render the template
        html_body = templates.get_template("emails/api_key_reset.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering API key reset email template: {str(e)}")
        return False


def send_welcome_email(to_email: str, api_key: str) -> bool:
    """
    Send welcome email after successful activation with API key using Jinja2 template
    
    Args:
        to_email: Recipient email address
        api_key: User's API key
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Welcome to {APP_GLOBALS.get('app_name')} - Your API Key"
    
    # Render template
    try:
        context = {
            "api_key": api_key,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Account Activated!",
            "year": datetime.now().year,
            "beta_mode": APP_GLOBALS.get('beta_mode', False)
        }
        
        # Render the template
        html_body = templates.get_template("emails/welcome.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering welcome email template: {str(e)}")
        return False


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """
    Send password reset email with reset link using Jinja2 template
    
    Args:
        to_email: Recipient email address
        reset_token: Unique password reset token
    
    Returns:
        bool: True if email sent successfully
    """
    reset_link = f"{EmailConfig.APP_BASE_URL}/v1/auth/reset_password?token={reset_token}"
    
    subject = f"Reset Your {APP_GLOBALS.get('app_name')} Password"
    
    # Render template
    try:
        context = {
            "reset_link": reset_link,
            "header_title": "Password Reset Request",
            "app_name": APP_GLOBALS.get('app_name'),
            "year": datetime.now().year,
            "expires_in": "1 hour"
        }
        
        # Render the template
        html_body = templates.get_template("emails/password_reset.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering password reset email template: {str(e)}")
        return False


def send_password_changed_email(to_email: str) -> bool:
    """
    Send notification email when password has been changed
    
    Args:
        to_email: Recipient email address
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Password Changed"
    
    # Render template
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Password Changed",
            "year": datetime.now().year,
            "changed_at": datetime.now().strftime("%B %d, %Y at %I:%M %p UTC"),
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        # Render the template
        html_body = templates.get_template("emails/password_changed.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering password changed email template: {str(e)}")
        return False


# ============================================================================
# BILLING EMAIL TEMPLATE FUNCTIONS
# ============================================================================

def send_subscription_welcome_email(
    to_email: str,
    billing_cycle: str,
    renews_at: datetime = None
) -> bool:
    """
    Send welcome email to new Premium subscribers
    
    Args:
        to_email: Recipient email address
        billing_cycle: 'monthly', 'quarterly', or 'annual'
        renews_at: Next renewal date
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Welcome to {APP_GLOBALS.get('app_name')} Premium!"
    
    try:
        amount = get_price_for_cycle(billing_cycle)
        
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Welcome to Premium!",
            "year": datetime.now().year,
            "billing_cycle": billing_cycle,
            "amount": f"{amount:.2f}",
            "renews_at": format_date(renews_at),
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/subscription_welcome.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Subscription welcome email sent to {to_email}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending subscription welcome email: {str(e)}")
        return False


def send_payment_receipt_email(
    to_email: str,
    amount: float,
    billing_cycle: str,
    order_id: str = None,
    invoice_url: str = None,
    next_billing_date: datetime = None
) -> bool:
    """
    Send payment receipt email after successful payment
    
    Args:
        to_email: Recipient email address
        amount: Payment amount in dollars
        billing_cycle: 'monthly', 'quarterly', or 'annual'
        order_id: LemonSqueezy order/invoice ID
        invoice_url: URL to view full invoice
        next_billing_date: Next billing date
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Payment Receipt"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Payment Receipt",
            "year": datetime.now().year,
            "amount": f"{amount:.2f}",
            "billing_cycle": billing_cycle,
            "payment_date": format_date(datetime.now(timezone.utc)),
            "order_id": order_id,
            "invoice_url": invoice_url,
            "next_billing_date": format_date(next_billing_date),
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/payment_receipt.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Payment receipt email sent to {to_email}, amount=${amount:.2f}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending payment receipt email: {str(e)}")
        return False


def send_payment_failed_email(
    to_email: str,
    amount: float = None,
    billing_cycle: str = None
) -> bool:
    """
    Send payment failed warning email
    
    Args:
        to_email: Recipient email address
        amount: Failed payment amount (optional)
        billing_cycle: Billing cycle (optional)
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Payment Failed - Action Required"
    
    try:
        # Get amount from pricing if not provided
        if amount is None and billing_cycle:
            amount = get_price_for_cycle(billing_cycle)
        elif amount is None:
            amount = get_price_for_cycle('monthly')
        
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Payment Failed",
            "year": datetime.now().year,
            "amount": f"{amount:.2f}",
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/payment_failed.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Payment failed email sent to {to_email}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending payment failed email: {str(e)}")
        return False


def send_subscription_cancelled_email(
    to_email: str,
    ends_at: datetime = None
) -> bool:
    """
    Send subscription cancellation confirmation email
    
    Args:
        to_email: Recipient email address
        ends_at: Date when Premium access ends
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Subscription Cancelled"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Subscription Cancelled",
            "year": datetime.now().year,
            "ends_at": format_date(ends_at),
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/subscription_cancelled.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Subscription cancelled email sent to {to_email}, ends_at={ends_at}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending subscription cancelled email: {str(e)}")
        return False


def send_subscription_expired_email(to_email: str) -> bool:
    """
    Send subscription expired notification email
    
    Args:
        to_email: Recipient email address
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Your Premium Subscription Has Ended"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Subscription Ended",
            "year": datetime.now().year,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/subscription_expired.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Subscription expired email sent to {to_email}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending subscription expired email: {str(e)}")
        return False


def send_payment_recovered_email(
    to_email: str,
    amount: float,
    billing_cycle: str = None,
    next_billing_date: datetime = None
) -> bool:
    """
    Send payment recovered notification email
    
    Args:
        to_email: Recipient email address
        amount: Recovered payment amount
        billing_cycle: Billing cycle
        next_billing_date: Next billing date
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Payment Successful - Account Restored"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Payment Recovered",
            "year": datetime.now().year,
            "amount": f"{amount:.2f}",
            "billing_cycle": billing_cycle or "monthly",
            "next_billing_date": format_date(next_billing_date),
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/payment_recovered.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Payment recovered email sent to {to_email}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending payment recovered email: {str(e)}")
        return False


def send_refund_confirmation_email(
    to_email: str,
    refund_amount: float,
    original_amount: float = None,
    order_id: str = None,
    subscription_cancelled: bool = False
) -> bool:
    """
    Send refund confirmation email
    
    Args:
        to_email: Recipient email address
        refund_amount: Refund amount in dollars
        original_amount: Original payment amount (optional)
        order_id: Order/invoice reference
        subscription_cancelled: Whether subscription was cancelled with refund
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"{APP_GLOBALS.get('app_name')} - Refund Confirmation"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": "Refund Processed",
            "year": datetime.now().year,
            "refund_amount": f"{refund_amount:.2f}",
            "original_amount": f"{original_amount:.2f}" if original_amount else f"{refund_amount:.2f}",
            "refund_date": format_date(datetime.now(timezone.utc)),
            "order_id": order_id,
            "subscription_cancelled": subscription_cancelled,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/refund_confirmation.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            logger.info(f"[email] Refund confirmation email sent to {to_email}, amount=${refund_amount:.2f}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending refund confirmation email: {str(e)}")
        return False
    
def send_feedback_email(
    user_email: str,
    user_id: str,
    liked: str = None,
    disliked: str = None,
    improve: str = None,
) -> bool:
    """
    Send a formatted beta feedback notification to the support address.

    Args:
        user_email: Email address of the submitting user
        user_id: UUID of the submitting user
        liked: Response to "What did you like?"
        disliked: Response to "What did you not like / what was not working?"
        improve: Response to "What would you improve?"

    Returns:
        bool: True if email sent successfully
    """
    app_name = APP_GLOBALS.get("app_name", "BoloDoc API")
    subject = f"{app_name} [BETA] - New Feedback Submission"

    def _section(label: str, body: str) -> str:
        content = (body or "").strip()
        if not content:
            content = "<em style='color:#adb5bd;'>(no response)</em>"
        else:
            content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            content = content.replace("\n", "<br>")
        return (
            f"<tr>"
            f"<td style='padding:14px 0 6px 0;font-weight:600;color:#3d4461;"
            f"font-size:14px;border-top:1px solid #e9ecef;'>{label}</td>"
            f"</tr>"
            f"<tr>"
            f"<td style='padding:0 0 14px 0;color:#212529;font-size:14px;"
            f"line-height:1.6;'>{content}</td>"
            f"</tr>"
        )

    rows = (
        _section("What did you like?", liked)
        + _section("What did you not like, or what was not working?", disliked)
        + _section("What would you improve?", improve)
    )

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f4f4f7;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:8px;
                  box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden;">

      <!-- header -->
      <tr>
        <td style="background:#3d4461;padding:24px 32px;">
          <span style="color:#ffffff;font-size:20px;font-weight:700;">
            {app_name}
          </span>
          <span style="display:inline-block;background:#ffffff;color:#3d4461;
                       font-size:11px;font-weight:700;letter-spacing:0.06em;
                       padding:2px 8px;border-radius:4px;margin-left:10px;
                       vertical-align:middle;">BETA</span>
        </td>
      </tr>

      <!-- subheader -->
      <tr>
        <td style="padding:24px 32px 0 32px;">
          <h2 style="margin:0 0 6px 0;color:#3d4461;font-size:18px;">
            New Beta Feedback Submission
          </h2>
          <p style="margin:0;color:#6c757d;font-size:13px;">
            From: {user_email} &nbsp;|&nbsp; User ID: {user_id}
          </p>
        </td>
      </tr>

      <!-- responses -->
      <tr>
        <td style="padding:20px 32px 28px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            {rows}
          </table>
        </td>
      </tr>

      <!-- footer -->
      <tr>
        <td style="background:#f8f9fa;padding:16px 32px;
                   border-top:1px solid #e9ecef;
                   color:#adb5bd;font-size:12px;text-align:center;">
          This is an internal notification from {app_name}. Do not reply to this message.
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""

    try:
        support = EmailConfig.SUPPORT_EMAIL
        if not support:
            logger.warning("[feedback] No support_email configured; feedback email not sent")
            return False

        sender = get_email_sender()
        result = sender.send_email(support, subject, html_body)

        if result:
            logger.info(f"[email] Feedback notification sent for user {user_email}")
        return result

    except Exception as e:
        logger.error(f"Error sending feedback email: {str(e)}")
        return False


def send_bolo_notification_email(
    to_email: str,
    first_name: str,
    additions: list = None,
    removals: list = None,
    status_changes: list = None,
    most_wanted: list = None
) -> bool:
    '''
    Send BOLO change notification email to premium user
    
    Args:
        to_email: Recipient email address
        first_name: User's first name for greeting
        additions: List of newly added records
        removals: List of removed records
        status_changes: List of status change records
        most_wanted: List of new Most Wanted records
    
    Returns:
        bool: True if email sent successfully
    '''
    # Skip if no changes to report
    if not any([additions, removals, status_changes, most_wanted]):
        logger.info(f"No BOLO changes to report for {to_email}")
        return True
    
    subject = f"{APP_GLOBALS.get('app_name')} - FBI Wanted Database Update"
    
    try:
        context = {
            "app_name": APP_GLOBALS.get('app_name'),
            "header_title": APP_GLOBALS.get('app_name') + " Alert",
            "year": datetime.now().year,
            "first_name": first_name or "Premium User",
            "additions": additions or [],
            "removals": removals or [],
            "status_changes": status_changes or [],
            "most_wanted": most_wanted or [],
            "app_base_url": EmailConfig.APP_BASE_URL,
            "support_email": EmailConfig.SUPPORT_EMAIL
        }
        
        html_body = templates.get_template("emails/bolo_notification.html").render(context)
        
        sender = get_email_sender()
        result = sender.send_email(to_email, subject, html_body)
        
        if result:
            change_summary = []
            if additions:
                change_summary.append(f"{len(additions)} added")
            if removals:
                change_summary.append(f"{len(removals)} removed")
            if status_changes:
                change_summary.append(f"{len(status_changes)} status changes")
            if most_wanted:
                change_summary.append(f"{len(most_wanted)} most wanted")
            
            logger.info(f"[email] BOLO notification sent to {to_email}: {', '.join(change_summary)}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending BOLO notification email: {str(e)}")
        return False
