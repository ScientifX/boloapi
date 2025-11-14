"""
Email Utility Module
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
    API_APP_BASE_URL
)

# Configure logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Jinja2 templates for emails
templates = Jinja2Templates(directory="templates")


class EmailConfig:
    """Email configuration from environment variables"""
    
    TENANT_ID = API_AZURE_TENANT_ID
    CLIENT_ID = API_AZURE_CLIENT_ID
    CLIENT_SECRET = API_AZURE_CLIENT_SECRET
    FROM_ADDRESS = API_EMAIL_FROM_ADDRESS
    FROM_NAME = API_EMAIL_FROM_NAME or "BoloAPI"
    APP_BASE_URL = API_APP_BASE_URL or "http://127.0.0.1:8000"
    
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
            
            # Send email
            url = f"https://graph.microsoft.com/v1.0/users/{EmailConfig.FROM_ADDRESS}/sendMail"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=message, headers=headers, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Successfully sent email to {to_address}")
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
# EMAIL TEMPLATE FUNCTIONS
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
    
    subject = f"Activate Your {EmailConfig.FROM_NAME} Account"
    
    # Render template
    try:
        # Create a mock request object for template rendering
        context = {
            "activation_link": activation_link,
            "header_title": f"Welcome to {EmailConfig.FROM_NAME}",
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
    subject = f"Your New {EmailConfig.FROM_NAME} API Key"
    
    # Render template
    try:
        context = {
            "api_key": api_key,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "header_title": "🔑 API Key Reset",
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
    subject = f"Welcome to {EmailConfig.FROM_NAME} - Your API Key"
    
    # Render template
    try:
        context = {
            "api_key": api_key,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "header_title": "✅ Account Activated!",
            "year": datetime.now().year
        }
        
        # Render the template
        html_body = templates.get_template("emails/welcome.html").render(context)
        
        sender = get_email_sender()
        return sender.send_email(to_email, subject, html_body)
        
    except Exception as e:
        logger.error(f"Error rendering welcome email template: {str(e)}")
        return False
