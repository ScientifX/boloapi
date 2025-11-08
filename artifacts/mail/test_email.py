"""
Email Testing Script
Tests Microsoft Graph API email functionality

Usage:
    python test_email.py [test_email_address]
    
Example:
    python test_email.py jerry@example.com
"""

import sys
import os
from datetime import datetime

# Add parent directory to path if running standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_utils import (
    EmailConfig,
    send_activation_email,
    send_api_key_email,
    send_welcome_email,
    get_email_sender
)


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def check_configuration():
    """Check if email configuration is complete"""
    print_section("Checking Email Configuration")
    
    if EmailConfig.is_configured():
        print("✅ All configuration variables are set")
        print(f"\n   Tenant ID:    {EmailConfig.TENANT_ID[:8]}...")
        print(f"   Client ID:    {EmailConfig.CLIENT_ID[:8]}...")
        print(f"   Client Secret: {'*' * 32}")
        print(f"   From Address: {EmailConfig.FROM_ADDRESS}")
        print(f"   API Base URL: {EmailConfig.API_BASE_URL}")
        return True
    else:
        missing = EmailConfig.get_missing_config()
        print("❌ Missing required configuration:")
        for var in missing:
            print(f"   - {var}")
        print("\nPlease set these environment variables before testing.")
        print("See MICROSOFT_365_EMAIL_SETUP.md for instructions.")
        return False


def test_authentication():
    """Test Microsoft Graph API authentication"""
    print_section("Testing Microsoft Graph API Authentication")
    
    try:
        sender = get_email_sender()
        print("Requesting access token...")
        token = sender._get_access_token()
        
        print("✅ Successfully obtained access token")
        print(f"   Token (first 20 chars): {token[:20]}...")
        print(f"   Token cached until: {sender.token_expires_at}")
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        print("\nPossible issues:")
        print("  - Invalid tenant ID, client ID, or client secret")
        print("  - Network connectivity issues")
        print("  - Azure AD configuration problems")
        return False


def test_activation_email(test_email):
    """Test sending activation email"""
    print_section("Testing Activation Email")
    
    test_token = f"test-activation-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    print(f"Sending activation email to: {test_email}")
    print(f"Test activation token: {test_token}")
    print("Sending...")
    
    success = send_activation_email(test_email, test_token)
    
    if success:
        print("✅ Activation email sent successfully!")
        print("\nWhat to check:")
        print(f"  1. Email arrived at {test_email}")
        print("  2. Activation link is clickable")
        print("  3. HTML formatting looks correct")
        print("  4. Link contains the test token")
    else:
        print("❌ Failed to send activation email")
        print("\nCheck the logs above for error details")
    
    return success


def test_api_key_email(test_email):
    """Test sending API key reset email"""
    print_section("Testing API Key Reset Email")
    
    test_api_key = f"test_key_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_abcdef1234567890"
    
    print(f"Sending API key email to: {test_email}")
    print(f"Test API key: {test_api_key}")
    print("Sending...")
    
    success = send_api_key_email(test_email, test_api_key)
    
    if success:
        print("✅ API key email sent successfully!")
        print("\nWhat to check:")
        print(f"  1. Email arrived at {test_email}")
        print("  2. API key is displayed correctly")
        print("  3. Security warnings are visible")
        print("  4. Code examples are formatted")
    else:
        print("❌ Failed to send API key email")
        print("\nCheck the logs above for error details")
    
    return success


def test_welcome_email(test_email):
    """Test sending welcome email"""
    print_section("Testing Welcome Email")
    
    test_api_key = f"test_key_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_abcdef1234567890"
    
    print(f"Sending welcome email to: {test_email}")
    print(f"Test API key: {test_api_key}")
    print("Sending...")
    
    success = send_welcome_email(test_email, test_api_key)
    
    if success:
        print("✅ Welcome email sent successfully!")
        print("\nWhat to check:")
        print(f"  1. Email arrived at {test_email}")
        print("  2. Welcome message is clear")
        print("  3. Quick start guide is helpful")
        print("  4. Links and code examples work")
    else:
        print("❌ Failed to send welcome email")
        print("\nCheck the logs above for error details")
    
    return success


def run_all_tests(test_email):
    """Run all email tests"""
    print("\n" + "█"*70)
    print("  EMAIL FUNCTIONALITY TEST SUITE")
    print("█"*70)
    print(f"\nTest email address: {test_email}")
    print(f"Test started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Track results
    results = {
        "Configuration": False,
        "Authentication": False,
        "Activation Email": False,
        "API Key Email": False,
        "Welcome Email": False
    }
    
    # Run tests
    results["Configuration"] = check_configuration()
    
    if not results["Configuration"]:
        print("\n❌ Cannot proceed without proper configuration")
        return results
    
    results["Authentication"] = test_authentication()
    
    if not results["Authentication"]:
        print("\n❌ Cannot proceed without successful authentication")
        return results
    
    # Test all email types
    results["Activation Email"] = test_activation_email(test_email)
    results["API Key Email"] = test_api_key_email(test_email)
    results["Welcome Email"] = test_welcome_email(test_email)
    
    # Summary
    print_section("Test Summary")
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {test_name}")
    
    print("\n" + "-"*70)
    if all_passed:
        print("  ✅ ALL TESTS PASSED!")
        print("  Email functionality is working correctly.")
    else:
        failed_count = sum(1 for v in results.values() if not v)
        print(f"  ❌ {failed_count} TEST(S) FAILED")
        print("  Please review the errors above and check:")
        print("    - Azure AD configuration")
        print("    - Environment variables")
        print("    - Network connectivity")
        print("    - Microsoft 365 admin settings")
    print("-"*70)
    
    return results


def main():
    """Main test function"""
    # Get test email from command line or use default
    if len(sys.argv) > 1:
        test_email = sys.argv[1]
    else:
        test_email = input("Enter test email address: ").strip()
    
    if not test_email or '@' not in test_email:
        print("❌ Invalid email address")
        print("\nUsage: python test_email.py [test_email_address]")
        print("Example: python test_email.py jerry@example.com")
        return
    
    # Run tests
    results = run_all_tests(test_email)
    
    # Exit code based on results
    exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
