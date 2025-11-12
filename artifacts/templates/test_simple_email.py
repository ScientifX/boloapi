"""
Simple Email Test - No Templates Required
Tests email sending with inline HTML (bypasses Jinja2 templates)
"""

import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

class SimpleEmailSender:
    """Minimal email sender for testing"""
    
    def __init__(self):
        self.tenant_id = os.getenv("API_AZURE_TENANT_ID")
        self.client_id = os.getenv("API_AZURE_CLIENT_ID")
        self.client_secret = os.getenv("API_AZURE_CLIENT_SECRET")
        self.from_address = os.getenv("API_EMAIL_FROM_ADDRESS")
        self.token_cache = None
        self.token_expires_at = None
    
    def get_access_token(self):
        """Get access token"""
        if self.token_cache and self.token_expires_at:
            if datetime.now(timezone.utc) < self.token_expires_at:
                return self.token_cache
        
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        self.token_cache = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        
        return self.token_cache
    
    def send_test_email(self, to_address: str):
        """Send a simple test email"""
        access_token = self.get_access_token()
        
        # Get timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Simple inline HTML (no template required)
        # Using f-string to avoid CSS brace conflicts
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                .header {{ background-color: #3d4461; color: white; padding: 20px; border-radius: 5px; }}
                .content {{ padding: 20px; background-color: #f9f9f9; border: 1px solid #ddd; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✓ Email Test Successful!</h1>
            </div>
            <div class="content">
                <h2>Congratulations!</h2>
                <p>Your Microsoft Graph API email integration is working correctly.</p>
                <p><strong>Test Details:</strong></p>
                <ul>
                    <li>From: {self.from_address}</li>
                    <li>Sent: {timestamp}</li>
                    <li>Status: Successfully delivered</li>
                </ul>
                <p>You can now send activation emails, welcome emails, and API key reset emails through your FastAPI application.</p>
            </div>
        </body>
        </html>
        """
        
        message = {
            "message": {
                "subject": "✓ Email Test - Scientifics.io API",
                "body": {
                    "contentType": "HTML",
                    "content": html_body
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
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.from_address}/sendMail"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        print(f"\nSending test email to: {to_address}")
        print(f"From: {self.from_address}")
        print("Sending...")
        
        response = requests.post(url, json=message, headers=headers, timeout=10)
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 202:
            print("✓ EMAIL SENT SUCCESSFULLY!")
            print(f"\nCheck your inbox at: {to_address}")
            print("\nWhat to verify:")
            print("  1. Email arrived (check spam/junk if not in inbox)")
            print("  2. From address shows correctly")
            print("  3. HTML formatting looks good")
            print("  4. No winmail.dat attachment")
            return True
        else:
            print("✗ EMAIL SEND FAILED")
            print(f"Status: {response.status_code}")
            
            try:
                error = response.json()
                print(f"Error: {error}")
            except:
                print(f"Response: {response.text}")
            
            return False


def main():
    print("="*70)
    print("  SIMPLE EMAIL TEST (No Templates)")
    print("="*70)
    print()
    
    # Get test email address
    test_email = input("Enter email address to send test to: ").strip()
    
    if not test_email or '@' not in test_email:
        print("Invalid email address")
        return
    
    try:
        sender = SimpleEmailSender()
        success = sender.send_test_email(test_email)
        
        if success:
            print("\n" + "="*70)
            print("  SUCCESS - Email system is working!")
            print("="*70)
            print()
            print("Next steps:")
            print("  1. Check that the email arrived and looks good")
            print("  2. If there's a winmail.dat attachment, we'll need to fix that")
            print("  3. Create your email templates in templates/emails/")
            print("  4. Update your email_utils.py to use the templates")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
