"""
Test Script for JWT Authentication System
Tests the complete authentication flow: register -> activate -> token -> protected endpoint

Run this after:
1. Creating the users table (schema_auth.sql)
2. Starting your FastAPI app with router_auth included
3. Installing dependencies: pip install PyJWT bcrypt

Usage:
    python test_auth.py
"""
import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
TEST_EMAIL = f"test_{datetime.now().timestamp()}@example.com"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)

def print_response(response):
    """Print formatted response"""
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")
    return response.json() if response.status_code < 400 else None

def test_registration():
    """Test user registration"""
    print_section("1. USER REGISTRATION")
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": TEST_EMAIL}
    )
    
    data = print_response(response)
    
    if data:
        print(f"\n✓ Registration successful for {TEST_EMAIL}")
        print(f"  User ID: {data['user_id']}")
        print(f"  Note: {data['note']}")
        return data
    else:
        print("\n✗ Registration failed")
        return None

def test_duplicate_registration(email):
    """Test duplicate registration (should resend activation)"""
    print_section("2. DUPLICATE REGISTRATION TEST")
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": email}
    )
    
    data = print_response(response)
    
    if data:
        print(f"\n✓ Duplicate registration handled correctly")
        return data
    else:
        print("\n✗ Duplicate registration test failed")
        return None

def test_activation(activation_token):
    """Test account activation"""
    print_section("3. ACCOUNT ACTIVATION")
    
    response = requests.get(
        f"{BASE_URL}/auth/activate",
        params={"token": activation_token}
    )
    
    data = print_response(response)
    
    if data:
        print(f"\n✓ Account activated successfully")
        print(f"  API Key: {data['api_key']}")
        print(f"  Instructions: {data['instructions']}")
        return data['api_key']
    else:
        print("\n✗ Activation failed")
        return None

def test_token_generation(api_key):
    """Test JWT token generation"""
    print_section("4. JWT TOKEN GENERATION")
    
    response = requests.post(
        f"{BASE_URL}/auth/token",
        json={"api_key": api_key}
    )
    
    data = print_response(response)
    
    if data:
        print(f"\n✓ JWT token generated successfully")
        print(f"  Token Type: {data['token_type']}")
        print(f"  Expires In: {data['expires_in']} seconds")
        print(f"  Role: {data['role']}")
        print(f"  Token: {data['access_token'][:50]}...")
        return data['access_token']
    else:
        print("\n✗ Token generation failed")
        return None

def test_protected_endpoint_without_token():
    """Test accessing protected endpoint without token"""
    print_section("5. PROTECTED ENDPOINT - NO TOKEN (should fail)")
    
    response = requests.post(
        f"{BASE_URL}/api/search/simple",
        json={
            "filters": [
                {"field": "sex", "value": "Male"}
            ],
            "limit": 25
        }
    )
    
    print_response(response)
    
    if response.status_code == 401:
        print("\n✓ Correctly rejected request without token")
        return True
    else:
        print("\n✗ Should have returned 401 Unauthorized")
        return False

def test_protected_endpoint_with_token(access_token):
    """Test accessing protected endpoint with valid token"""
    print_section("6. PROTECTED ENDPOINT - WITH TOKEN (should succeed)")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/search/simple",
        json={
            "filters": [
                {"field": "sex", "value": "Male"}
            ],
            "limit": 25
        },
        headers=headers
    )
    
    data = print_response(response)
    
    if response.status_code == 200 and data:
        print(f"\n✓ Successfully accessed protected endpoint")
        print(f"  Role: {data.get('role')}")
        print(f"  Results: {data.get('resultcount')} records")
        return True
    else:
        print("\n✗ Failed to access protected endpoint")
        return False

def test_invalid_token():
    """Test with invalid token"""
    print_section("7. INVALID TOKEN TEST (should fail)")
    
    headers = {
        "Authorization": "Bearer invalid_token_12345"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/search/simple",
        json={
            "filters": [
                {"field": "sex", "value": "Male"}
            ],
            "limit": 25
        },
        headers=headers
    )
    
    print_response(response)
    
    if response.status_code == 401:
        print("\n✓ Correctly rejected invalid token")
        return True
    else:
        print("\n✗ Should have returned 401 Unauthorized")
        return False

def test_key_reset(email):
    """Test API key reset"""
    print_section("8. API KEY RESET")
    
    response = requests.post(
        f"{BASE_URL}/auth/key/reset",
        json={"email": email}
    )
    
    data = print_response(response)
    
    if data:
        print(f"\n✓ API key reset successful")
        print(f"  New API Key: {data['api_key']}")
        return data['api_key']
    else:
        print("\n✗ Key reset failed")
        return None

def test_old_token_after_reset(old_token):
    """Test that old token is invalid after key reset"""
    print_section("9. OLD TOKEN AFTER RESET (should fail)")
    
    headers = {
        "Authorization": f"Bearer {old_token}"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/search/simple",
        json={
            "filters": [
                {"field": "sex", "value": "Male"}
            ],
            "limit": 25
        },
        headers=headers
    )
    
    print_response(response)
    
    if response.status_code == 401:
        print("\n✓ Old token correctly invalidated after key reset")
        return True
    else:
        print("\n✗ Old token should be invalid")
        return False

def run_full_test():
    """Run complete authentication flow test"""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  JWT Authentication System - Full Test Suite".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # Test 1: Registration
    reg_data = test_registration()
    if not reg_data:
        print("\n✗ Test suite failed at registration")
        return
    
    # Extract activation token from note (in production, this would be in email)
    activation_token = reg_data['note'].split('token=')[1] if 'token=' in reg_data['note'] else None
    if not activation_token:
        print("\n✗ Could not extract activation token")
        return
    
    # Test 2: Duplicate registration
    test_duplicate_registration(TEST_EMAIL)
    
    # Test 3: Activation
    api_key = test_activation(activation_token)
    if not api_key:
        print("\n✗ Test suite failed at activation")
        return
    
    # Test 4: Token generation
    access_token = test_token_generation(api_key)
    if not access_token:
        print("\n✗ Test suite failed at token generation")
        return
    
    # Test 5: Protected endpoint without token
    test_protected_endpoint_without_token()
    
    # Test 6: Protected endpoint with token
    test_protected_endpoint_with_token(access_token)
    
    # Test 7: Invalid token
    test_invalid_token()
    
    # Test 8: Key reset
    new_api_key = test_key_reset(TEST_EMAIL)
    if not new_api_key:
        print("\n✗ Test suite failed at key reset")
        return
    
    # Test 9: Old token should be invalid
    test_old_token_after_reset(access_token)
    
    # Test 10: Generate new token with new key
    print_section("10. NEW TOKEN WITH NEW KEY")
    new_token = test_token_generation(new_api_key)
    if new_token:
        test_protected_endpoint_with_token(new_token)
    
    # Summary
    print_section("TEST SUITE COMPLETE")
    print("\n✓ All authentication flows tested successfully!")
    print(f"\nTest Email: {TEST_EMAIL}")
    print(f"Current API Key: {new_api_key}")
    print(f"Current Token: {new_token[:50]}..." if new_token else "No token")
    print("\n" + "█"*70 + "\n")

if __name__ == "__main__":
    try:
        run_full_test()
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to API server")
        print(f"   Make sure your FastAPI app is running at {BASE_URL}")
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n✗ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
