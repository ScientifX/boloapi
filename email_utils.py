"""
Email Utility Module
Sends emails via Microsoft Graph API (Microsoft 365)

Required environment variables:
    - MICROSOFT_TENANT_ID: Your Azure AD tenant ID
    - MICROSOFT_CLIENT_ID: App registration client ID
    - MICROSOFT_CLIENT_SECRET: App registration client secret
    - EMAIL_FROM_ADDRESS: The email address to send from (must be in your M365)
    - APP_BASE_URL: Your API's base URL (for activation links)

Setup Instructions:
1. Register an application in Azure AD (https://portal.azure.com)
2. Add API permissions: Mail.Send (Application permission)
3. Grant admin consent for the permissions
4. Create a client secret
5. Set environment variables with the values
"""

import os
import requests
from typing import Optional
from datetime import datetime, timedelta, timezone
import logging

# Configure logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailConfig:
    """Email configuration from environment variables"""
    TENANT_ID     = os.getenv("API_AZURE_TENANT_ID")
    CLIENT_ID     = os.getenv("API_AZURE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("API_AZURE_CLIENT_SECRET")
    FROM_ADDRESS  = os.getenv("API_EMAIL_FROM_ADDRESS")
    FROM_NAME     = os.getenv("API_EMAIL_FROM_NAME")
    APP_BASE_URL  = os.getenv("API_APP_BASE_URL")
    
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
    Send account activation email with activation link
    
    Args:
        to_email: Recipient email address
        activation_token: Unique activation token
    
    Returns:
        bool: True if email sent successfully
    """
    activation_link = f"{EmailConfig.APP_BASE_URL}/auth/activate?token={activation_token}"
    
    subject = f"Activate Your {EmailConfig.FROM_NAME} Account"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #0066cc;
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 30px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .button {{
                display: inline-block;
                padding: 12px 30px;
                background-color: #0066cc;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
            }}
            .warning {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                padding: 10px;
                border-radius: 3px;
                margin: 15px 0;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Welcome to {EmailConfig.FROM_NAME}</h1>
        </div>
        <div class="content">
            <h2>Activate Your Account</h2>
            <p>Thank you for registering with {EmailConfig.FROM_NAME}. To complete your registration and receive your API key, please activate your account by clicking the button below:</p>
            
            <div style="text-align: center;">
                <a href="{activation_link}" class="button">Activate Account</a>
            </div>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; background-color: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 3px;">
                {activation_link}
            </p>
            
            <div class="warning">
                <strong>⚠️ Important:</strong> This activation link will expire in 1 hour. After activation, you'll receive your API key - save it securely as you won't be able to retrieve it again.
            </div>
            
            <p><strong>What happens next?</strong></p>
            <ol>
                <li>Click the activation link</li>
                <li>Receive your API key</li>
                <li>Use your API key to get access tokens</li>
                <li>Start making API requests</li>
            </ol>
            
            <div class="footer">
                <p>If you didn't register for this account, you can safely ignore this email.</p>
                <p>This is an automated message, please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    sender = get_email_sender()
    return sender.send_email(to_email, subject, html_body)


def send_api_key_email(to_email: str, api_key: str) -> bool:
    """
    Send API key reset email with new key
    
    Args:
        to_email: Recipient email address
        api_key: New API key
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Your New {EmailConfig.FROM_NAME} Key"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #dc3545;
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 30px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .api-key {{
                background-color: #fff;
                border: 2px solid #0066cc;
                padding: 15px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 14px;
                word-break: break-all;
                margin: 20px 0;
                text-align: center;
            }}
            .warning {{
                background-color: #f8d7da;
                border: 1px solid #dc3545;
                padding: 15px;
                border-radius: 3px;
                margin: 15px 0;
                color: #721c24;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔑 {EmailConfig.FROM_NAME} Key Reset</h1>
        </div>
        <div class="content">
            <h2>Your New API Key</h2>
            <p>Your API key has been successfully reset. Here is your new key:</p>
            
            <div class="api-key">
                <strong>{api_key}</strong>
            </div>
            
            <div class="warning">
                <strong>⚠️ Security Notice:</strong><br>
                • Your old API key and all tokens generated from it are now invalid<br>
                • Save this key securely - you won't be able to retrieve it again<br>
                • Never share your API key or commit it to version control<br>
                • If compromised, reset your key immediately
            </div>
            
            <p><strong>How to use your API key:</strong></p>
            <ol>
                <li>Exchange your API key for an access token: <code>POST /auth/token</code></li>
                <li>Use the access token in your requests: <code>Authorization: Bearer {{token}}</code></li>
                <li>Tokens expire after 1 hour - request new ones as needed</li>
            </ol>
            
            <p><strong>Example request:</strong></p>
            <pre style="background-color: #f4f4f4; padding: 10px; border-radius: 3px; overflow-x: auto;">
curl -X POST "{EmailConfig.APP_BASE_URL}/auth/token" \\
  -H "Content-Type: application/json" \\
  -d '{{"api_key": "{api_key}"}}'
            </pre>
            
            <div class="footer">
                <p>If you didn't request this API key reset, please contact support immediately.</p>
                <p>This is an automated message, please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    sender = get_email_sender()
    return sender.send_email(to_email, subject, html_body)


def send_welcome_email(to_email: str, api_key: str) -> bool:
    """
    Send welcome email after successful activation with API key
    
    Args:
        to_email: Recipient email address
        api_key: User's API key
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Welcome to {EmailConfig.FROM_NAME} - Your API Key"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #28a745;
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 30px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .api-key {{
                background-color: #fff;
                border: 2px solid #28a745;
                padding: 15px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 14px;
                word-break: break-all;
                margin: 20px 0;
                text-align: center;
            }}
            .info-box {{
                background-color: #d1ecf1;
                border: 1px solid #0c5460;
                padding: 15px;
                border-radius: 3px;
                margin: 15px 0;
                color: #0c5460;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>✅ Account Activated!</h1>
        </div>
        <div class="content">
            <h2>Welcome to {EmailConfig.FROM_NAME}</h2>
            <p>Your account has been successfully activated! Here is your API key:</p>
            
            <div class="api-key">
                <strong>{api_key}</strong>
            </div>
            
            <div class="info-box">
                <strong>💡 Getting Started:</strong><br>
                1. Save your API key in a secure location<br>
                2. Exchange it for access tokens using <code>/auth/token</code><br>
                3. Use tokens to access FBI Wanted API data<br>
                4. Your role: <strong>BASIC</strong> (25 records per request)
            </div>
            
            <p><strong>Quick Start Guide:</strong></p>
            
            <p>1. Get an access token:</p>
            <pre style="background-color: #f4f4f4; padding: 10px; border-radius: 3px; overflow-x: auto;">
curl -X POST "{EmailConfig.APP_BASE_URL}/auth/token" \\
  -H "Content-Type: application/json" \\
  -d '{{"api_key": "{api_key}"}}'
            </pre>
            
            <p>2. Make your first search:</p>
            <pre style="background-color: #f4f4f4; padding: 10px; border-radius: 3px; overflow-x: auto;">
curl "{EmailConfig.APP_BASE_URL}/search/simple?field=sex&value=Male" \\
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
            </pre>
            
            <p><strong>Available Features (BASIC tier):</strong></p>
            <ul>
                <li>Simple search across all fields</li>
                <li>Up to 25 records per request</li>
                <li>Access to cleaned, normalized data</li>
                <li>Full field documentation</li>
            </ul>
            
            <p><strong>Documentation:</strong> Visit <a href="{EmailConfig.APP_BASE_URL}/docs">{EmailConfig.APP_BASE_URL}/docs</a> for complete API documentation.</p>
            
            <div class="footer">
                <p>Need help? Check our documentation or contact support.</p>
                <p>This is an automated message, please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    sender = get_email_sender()
    return sender.send_email(to_email, subject, html_body)
