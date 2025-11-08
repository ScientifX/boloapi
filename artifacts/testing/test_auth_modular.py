"""
Modular Test Script for JWT Authentication System
Tests individual authentication flows that can be called independently

Run individual tests from a driver script by importing and calling test functions:
    from test_auth_modular import run_test
    run_test("register", email="test@example.com")
    run_test("activation", token="abc123")

Available Tests:
- register: Test user registration
- duplicate_register: Test duplicate registration handling
- activation: Test account activation
- token_generation: Test JWT token generation
- protected_no_token: Test protected endpoint without token (should fail)
- protected_with_token: Test protected endpoint with valid token (should succeed)
- invalid_token: Test with invalid token (should fail)
- key_reset: Test API key reset
- old_token_after_reset: Test that old token is invalid after key reset
- new_token_after_reset: Test generating new token with new key
"""
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)

def print_response(response: requests.Response) -> Optional[Dict[Any, Any]]:
    """Print formatted response and return JSON data if available"""
    print(f"Status: {response.status_code}")
    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return data
    except:
        print(f"Response: {response.text}")
        return None

def generate_test_email() -> str:
    """Generate a unique test email"""
    return f"test_{datetime.now().timestamp()}@example.com"

# ============================================================================
# INDIVIDUAL TEST FUNCTIONS
# ============================================================================

def test_register(email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Test user registration
    
    Args:
        email: Email address to register (generates unique one if not provided)
        
    Returns:
        Dict with registration data including user_id and activation token
    """
    print_section("USER REGISTRATION")
    
    if email is None:
        email = generate_test_email()
    
    print(f"Registering: {email}")
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": email}
    )
    
    data = print_response(response)
    
    if data and response.status_code < 400:
        print(f"\n✓ Registration successful for {email}")
        print(f"  User ID: {data['user_id']}")
        print(f"  Note: {data['note']}")
        
        # Extract activation token from note
        activation_token = None
        if 'token=' in data['note']:
            activation_token = data['note'].split('token=')[1]
            print(f"  Extracted Token: {activation_token}")
        
        return {
            "email": email,
            "user_id": data['user_id'],
            "activation_token": activation_token,
            "full_response": data
        }
    else:
        print("\n✗ Registration failed")
        return None

def test_duplicate_register(email: str) -> Optional[Dict[str, Any]]:
    """
    Test duplicate registration (should resend activation)
    
    Args:
        email: Email address to register again
        
    Returns:
        Dict with registration data
    """
    print_section("DUPLICATE REGISTRATION TEST")
    
    print(f"Re-registering: {email}")
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": email}
    )
    
    data = print_response(response)
    
    if data and response.status_code < 400:
        print(f"\n✓ Duplicate registration handled correctly")
        
        # Extract activation token from note
        activation_token = None
        if 'token=' in data['note']:
            activation_token = data['note'].split('token=')[1]
            print(f"  Extracted Token: {activation_token}")
        
        return {
            "email": email,
            "user_id": data['user_id'],
            "activation_token": activation_token,
            "full_response": data
        }
    else:
        print("\n✗ Duplicate registration test failed")
        return None

def test_activation(token: str) -> Optional[Dict[str, Any]]:
    """
    Test account activation
    
    Args:
        token: Activation token from registration email
        
    Returns:
        Dict with API key and activation data
    """
    print_section("ACCOUNT ACTIVATION")
    
    print(f"Activating with token: {token}")
    
    response = requests.get(
        f"{BASE_URL}/auth/activate",
        params={"token": token}
    )
    
    data = print_response(response)
    
    if data and response.status_code < 400:
        print(f"\n✓ Account activated successfully")
        print(f"  API Key: {data['api_key']}")
        print(f"  Instructions: {data['instructions']}")
        return {
            "api_key": data['api_key'],
            "full_response": data
        }
    else:
        print("\n✗ Activation failed")
        return None

def test_token_generation(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Test JWT token generation
    
    Args:
        api_key: API key from activation
        
    Returns:
        Dict with access token and token data
    """
    print_section("JWT TOKEN GENERATION")
    
    print(f"Generating token with API key: {api_key[:20]}...")
    
    response = requests.post(
        f"{BASE_URL}/auth/token",
        json={"api_key": api_key}
    )
    
    data = print_response(response)
    
    if data and response.status_code < 400:
        print(f"\n✓ JWT token generated successfully")
        print(f"  Token Type: {data['token_type']}")
        print(f"  Expires In: {data['expires_in']} seconds")
        print(f"  Role: {data['role']}")
        print(f"  Token: {data['access_token'][:50]}...")
        return {
            "access_token": data['access_token'],
            "token_type": data['token_type'],
            "expires_in": data['expires_in'],
            "role": data['role'],
            "full_response": data
        }
    else:
        print("\n✗ Token generation failed")
        return None

def test_protected_no_token() -> bool:
    """
    Test accessing protected endpoint without token (should fail with 401)
    
    Returns:
        True if correctly rejected (401), False otherwise
    """
    print_section("PROTECTED ENDPOINT - NO TOKEN (should fail)")
    
    print("Attempting to access protected endpoint without authentication...")
    
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
        print(f"\n✗ Should have returned 401 Unauthorized, got {response.status_code}")
        return False

def test_protected_with_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Test accessing protected endpoint with valid token (should succeed)
    
    Args:
        access_token: Valid JWT access token
        
    Returns:
        Dict with search results if successful
    """
    print_section("PROTECTED ENDPOINT - WITH TOKEN (should succeed)")
    
    print(f"Accessing protected endpoint with token: {access_token[:50]}...")
    
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
        print(f"  Data Field: {data.get('data_field')}")
        print(f"  Results: {data.get('resultcount')} records")
        return {
            "role": data.get('role'),
            "data_field": data.get('data_field'),
            "resultcount": data.get('resultcount'),
            "full_response": data
        }
    else:
        print(f"\n✗ Failed to access protected endpoint (status: {response.status_code})")
        return None

def test_invalid_token() -> bool:
    """
    Test with invalid token (should fail with 401)
    
    Returns:
        True if correctly rejected (401), False otherwise
    """
    print_section("INVALID TOKEN TEST (should fail)")
    
    invalid_token = "invalid_token_12345_this_is_not_a_real_jwt"
    print(f"Attempting to access with invalid token: {invalid_token[:30]}...")
    
    headers = {
        "Authorization": f"Bearer {invalid_token}"
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
        print(f"\n✗ Should have returned 401 Unauthorized, got {response.status_code}")
        return False

def test_key_reset(email: str) -> Optional[Dict[str, Any]]:
    """
    Test API key reset
    
    Args:
        email: Email address of account to reset
        
    Returns:
        Dict with new API key
    """
    print_section("API KEY RESET")
    
    print(f"Resetting API key for: {email}")
    
    response = requests.post(
        f"{BASE_URL}/auth/key/reset",
        json={"email": email}
    )
    
    data = print_response(response)
    
    if data and response.status_code < 400:
        print(f"\n✓ API key reset successful")
        print(f"  New API Key: {data['api_key']}")
        print(f"  Instructions: {data['instructions']}")
        return {
            "api_key": data['api_key'],
            "full_response": data
        }
    else:
        print("\n✗ Key reset failed")
        return None

def test_old_token_after_reset(old_token: str) -> bool:
    """
    Test that old token is invalid after key reset (should fail with 401)
    
    Args:
        old_token: JWT token generated before key reset
        
    Returns:
        True if correctly rejected (401), False otherwise
    """
    print_section("OLD TOKEN AFTER RESET (should fail)")
    
    print(f"Attempting to use old token after key reset: {old_token[:50]}...")
    
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
        print(f"\n✗ Old token should be invalid, got status {response.status_code}")
        return False

def test_new_token_after_reset(new_api_key: str) -> Optional[Dict[str, Any]]:
    """
    Test generating new token with new API key after reset
    
    Args:
        new_api_key: New API key from reset
        
    Returns:
        Dict with new token data and search results
    """
    print_section("NEW TOKEN WITH NEW KEY AFTER RESET")
    
    # Generate new token
    print(f"Generating new token with new API key: {new_api_key[:20]}...")
    token_result = test_token_generation(new_api_key)
    
    if not token_result:
        print("\n✗ Failed to generate new token with new key")
        return None
    
    new_token = token_result['access_token']
    
    # Test the new token
    print("\nTesting new token with protected endpoint...")
    search_result = test_protected_with_token(new_token)
    
    if search_result:
        print("\n✓ New token works correctly after key reset")
        return {
            "token_data": token_result,
            "search_result": search_result,
            "full_response": {
                "new_token": token_result,
                "search_test": search_result
            }
        }
    else:
        print("\n✗ New token failed to work")
        return None

# ============================================================================
# MAIN TEST RUNNER FUNCTION
# ============================================================================

def run_test(test_name: str, **kwargs) -> Any:
    """
    Run a specific test by name
    
    Args:
        test_name: Name of the test to run
        **kwargs: Parameters to pass to the test function
        
    Available tests:
        - register: kwargs: email (optional)
        - duplicate_register: kwargs: email (required)
        - activation: kwargs: token (required)
        - token_generation: kwargs: api_key (required)
        - protected_no_token: no kwargs
        - protected_with_token: kwargs: access_token (required)
        - invalid_token: no kwargs
        - key_reset: kwargs: email (required)
        - old_token_after_reset: kwargs: old_token (required)
        - new_token_after_reset: kwargs: new_api_key (required)
    
    Returns:
        Test result (varies by test)
    """
    # Test name mapping
    test_map = {
        "register": test_register,
        "duplicate_register": test_duplicate_register,
        "activation": test_activation,
        "token_generation": test_token_generation,
        "protected_no_token": test_protected_no_token,
        "protected_with_token": test_protected_with_token,
        "invalid_token": test_invalid_token,
        "key_reset": test_key_reset,
        "old_token_after_reset": test_old_token_after_reset,
        "new_token_after_reset": test_new_token_after_reset,
    }
    
    if test_name not in test_map:
        print(f"\n✗ Unknown test: {test_name}")
        print(f"Available tests: {', '.join(test_map.keys())}")
        return None
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + f"  Running Test: {test_name}".ljust(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    try:
        result = test_map[test_name](**kwargs)
        
        print("\n" + "█"*70)
        print(f"█  Test '{test_name}' completed")
        print("█"*70 + "\n")
        
        return result
        
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Error: Could not connect to API server")
        print(f"   Make sure your FastAPI app is running at {BASE_URL}")
        return None
    except TypeError as e:
        print(f"\n✗ Error: Missing or invalid parameters for test '{test_name}'")
        print(f"   {str(e)}")
        print(f"\n   Usage example:")
        print(f"   run_test('{test_name}', param='value')")
        return None
    except Exception as e:
        print(f"\n✗ Unexpected error in test '{test_name}': {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# LIST AVAILABLE TESTS
# ============================================================================

def list_tests():
    """Print all available tests and their required parameters"""
    print("\n" + "="*70)
    print(" AVAILABLE TESTS")
    print("="*70)
    
    tests_info = [
        ("register", "email (optional)", "Test user registration"),
        ("duplicate_register", "email (required)", "Test duplicate registration"),
        ("activation", "token (required)", "Test account activation"),
        ("token_generation", "api_key (required)", "Test JWT token generation"),
        ("protected_no_token", "none", "Test protected endpoint without token"),
        ("protected_with_token", "access_token (required)", "Test protected endpoint with token"),
        ("invalid_token", "none", "Test with invalid token"),
        ("key_reset", "email (required)", "Test API key reset"),
        ("old_token_after_reset", "old_token (required)", "Test old token after reset"),
        ("new_token_after_reset", "new_api_key (required)", "Test new token after reset"),
    ]
    
    for test_name, params, description in tests_info:
        print(f"\n{test_name}")
        print(f"  Params: {params}")
        print(f"  Description: {description}")
        print(f"  Usage: run_test('{test_name}', param=value)")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    print("Import this module and use run_test() to run individual tests")
    print("Example: from test_auth_modular import run_test")
    print("         run_test('register', email='test@example.com')")
    print("\nOr use list_tests() to see all available tests")
    list_tests()
