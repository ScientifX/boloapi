"""
Authentication Integration Test Script
Tests the complete authentication flow with email integration

Usage:
    python test_auth_flow.py [test_email]
    
Example:
    python test_auth_flow.py jerry@example.com
"""

import sys
import os
import requests
import time
from datetime import datetime

# Configuration
BASE_URL = os.getenv('API_APP_BASE_URL', 'http://localhost:8000')
TEST_EMAIL = None

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_result(success, message):
    """Print a test result"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}  {message}")

def test_auth_info():
    """Test authentication info endpoint"""
    print_section("1. Testing Authentication Info Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/auth/")
        response.raise_for_status()
        data = response.json()
        
        print(f"Version: {data.get('version')}")
        print(f"Email configured: {data.get('email_configured')}")
        
        if data.get('email_info'):
            if data['email_configured']:
                print(f"Email provider: {data['email_info'].get('provider')}")
                print(f"From address: {data['email_info'].get('from_address')}")
            else:
                print(f"Email status: {data['email_info'].get('status')}")
        
        print_result(True, "Authentication info retrieved")
        return True, data.get('email_configured', False)
        
    except Exception as e:
        print_result(False, f"Failed to get auth info: {str(e)}")
        return False, False

def test_registration(email, email_configured):
    """Test user registration"""
    print_section("2. Testing User Registration")
    
    try:
        payload = {"email": email}
        response = requests.post(f"{BASE_URL}/auth/register", json=payload)
        
        if response.status_code == 400:
            # User already exists
            data = response.json()
            print(f"User already registered: {data.get('detail')}")
            print_result(True, "Registration endpoint working (user exists)")
            return True, None, None
        
        response.raise_for_status()
        data = response.json()
        
        user_id = data.get('user_id')
        email_sent = data.get('email_sent', False)
        note = data.get('note', '')
        
        print(f"User ID: {user_id}")
        print(f"Email sent: {email_sent}")
        print(f"Note: {note}")
        
        # Extract activation token from note if email not sent
        activation_token = None
        if not email_sent and 'token=' in note:
            activation_token = note.split('token=')[1].strip()
            print(f"Activation token: {activation_token}")
        
        if email_configured and email_sent:
            print("\n⚠️  CHECK YOUR EMAIL for activation link")
            print("    You'll need to click the link to complete the test")
        elif not email_configured and activation_token:
            print(f"\n📝 Activation token available for testing")
        
        print_result(True, "Registration successful")
        return True, user_id, activation_token
        
    except Exception as e:
        print_result(False, f"Registration failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False, None, None

def test_activation(activation_token):
    """Test account activation"""
    print_section("3. Testing Account Activation")
    
    if not activation_token:
        print("⚠️  No activation token available")
        print("    If email is configured, check your email for the activation link")
        print("    Skipping automated activation test")
        return False, None
    
    try:
        response = requests.get(f"{BASE_URL}/auth/activate", params={"token": activation_token})
        response.raise_for_status()
        data = response.json()
        
        api_key = data.get('api_key')
        email_sent = data.get('email_sent', False)
        
        print(f"API Key: {api_key}")
        print(f"Welcome email sent: {email_sent}")
        print(f"Instructions: {data.get('instructions', '')}")
        
        if email_sent:
            print("\n✅ Welcome email sent - check your inbox")
        
        print_result(True, "Account activation successful")
        return True, api_key
        
    except Exception as e:
        print_result(False, f"Activation failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False, None

def test_token_generation(api_key):
    """Test JWT token generation"""
    print_section("4. Testing Token Generation")
    
    if not api_key:
        print("⚠️  No API key available - skipping token test")
        return False, None
    
    try:
        payload = {"api_key": api_key}
        response = requests.post(f"{BASE_URL}/auth/token", json=payload)
        response.raise_for_status()
        data = response.json()
        
        access_token = data.get('access_token')
        expires_in = data.get('expires_in')
        role = data.get('role')
        
        print(f"Access token (first 40 chars): {access_token[:40]}...")
        print(f"Expires in: {expires_in} seconds")
        print(f"Role: {role}")
        
        print_result(True, "Token generation successful")
        return True, access_token
        
    except Exception as e:
        print_result(False, f"Token generation failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False, None

def test_authenticated_request(access_token):
    """Test making an authenticated request"""
    print_section("5. Testing Authenticated Request")
    
    if not access_token:
        print("⚠️  No access token available - skipping authenticated request test")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.post(
            f"{BASE_URL}/api/search/simple",
            json={
                "filters": [{"field": "sex", "value": "Male"}],
                "logic": "AND",
                "limit": 25
            },
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        result_count = data.get('resultcount', 0)
        role = data.get('role')
        
        print(f"Search executed successfully")
        print(f"Results returned: {result_count}")
        print(f"User role: {role}")
        
        print_result(True, "Authenticated request successful")
        return True
        
    except Exception as e:
        print_result(False, f"Authenticated request failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def test_key_reset(email, email_configured):
    """Test API key reset"""
    print_section("6. Testing API Key Reset")
    
    print("⚠️  This will invalidate your current API key")
    proceed = input("Proceed with key reset test? (y/n): ").strip().lower()
    
    if proceed != 'y':
        print("Skipping key reset test")
        return False, None
    
    try:
        payload = {"email": email}
        response = requests.post(f"{BASE_URL}/auth/key/reset", json=payload)
        response.raise_for_status()
        data = response.json()
        
        new_api_key = data.get('api_key')
        email_sent = data.get('email_sent', False)
        
        print(f"New API Key: {new_api_key}")
        print(f"Email sent: {email_sent}")
        
        if email_configured and email_sent:
            print("\n✅ API key reset email sent - check your inbox")
        
        print_result(True, "API key reset successful")
        return True, new_api_key
        
    except Exception as e:
        print_result(False, f"Key reset failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False, None

def run_full_test_suite(email):
    """Run the complete authentication test suite"""
    print("\n" + "█"*70)
    print("  AUTHENTICATION FLOW TEST SUITE")
    print("█"*70)
    print(f"\nTest email: {email}")
    print(f"API Base URL: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "Auth Info": False,
        "Registration": False,
        "Activation": False,
        "Token Generation": False,
        "Authenticated Request": False,
        "Key Reset": False
    }
    
    # Test 1: Auth Info
    success, email_configured = test_auth_info()
    results["Auth Info"] = success
    
    if not success:
        print("\n❌ Cannot proceed - auth endpoint not accessible")
        return results
    
    # Test 2: Registration
    success, user_id, activation_token = test_registration(email, email_configured)
    results["Registration"] = success
    
    if not success:
        print("\n❌ Cannot proceed - registration failed")
        return results
    
    # Test 3: Activation
    if email_configured and not activation_token:
        print_section("3. Manual Activation Required")
        print("⚠️  Email is configured - you need to:")
        print("    1. Check your email for the activation link")
        print("    2. Click the activation link")
        print("    3. Copy the API key from the activation response or welcome email")
        print("")
        api_key = input("Enter your API key from email (or press Enter to skip): ").strip()
        
        if api_key:
            results["Activation"] = True
        else:
            print("Skipping remaining tests")
            return results
    else:
        success, api_key = test_activation(activation_token)
        results["Activation"] = success
        
        if not success:
            print("\n❌ Cannot proceed - activation failed")
            return results
    
    # Test 4: Token Generation
    success, access_token = test_token_generation(api_key)
    results["Token Generation"] = success
    
    if not success:
        print("\n❌ Cannot proceed - token generation failed")
        return results
    
    # Test 5: Authenticated Request
    success = test_authenticated_request(access_token)
    results["Authenticated Request"] = success
    
    # Test 6: Key Reset (optional)
    success, new_api_key = test_key_reset(email, email_configured)
    results["Key Reset"] = success
    
    # Summary
    print_section("Test Summary")
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {test_name}")
    
    print("\n" + "-"*70)
    if all_passed:
        print("  ✅ ALL TESTS PASSED!")
        print("  Authentication system with email integration is working correctly.")
    else:
        failed_count = sum(1 for v in results.values() if not v)
        print(f"  ⚠️  {failed_count} TEST(S) FAILED OR SKIPPED")
        print("  Review the errors above and check:")
        print("    - API is running and accessible")
        print("    - Database is configured correctly")
        print("    - Email configuration (if applicable)")
        print("    - Network connectivity")
    print("-"*70)
    
    return results

def main():
    """Main test function"""
    global TEST_EMAIL
    
    # Get test email from command line or prompt
    if len(sys.argv) > 1:
        TEST_EMAIL = sys.argv[1]
    else:
        TEST_EMAIL = input("Enter test email address: ").strip()
    
    if not TEST_EMAIL or '@' not in TEST_EMAIL:
        print("❌ Invalid email address")
        print("\nUsage: python test_auth_flow.py [test_email_address]")
        print("Example: python test_auth_flow.py jerry@example.com")
        return 1
    
    # Check if API is accessible
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"⚠️  Warning: API health check returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to API at {BASE_URL}")
        print(f"   Error: {str(e)}")
        print("\nMake sure:")
        print("  1. Your API is running")
        print("  2. BASE_URL is correct (set API_APP_BASE_URL env var to change)")
        return 1
    
    # Run tests
    results = run_full_test_suite(TEST_EMAIL)
    
    # Exit code based on results
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
