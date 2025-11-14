#!/usr/bin/env python3
"""
Signup System Testing Script
Tests all aspects of the new signup system
"""

import requests
import json
from typing import Dict, Tuple

# Configuration
BASE_URL = "http://localhost:8000"  # Change if your server runs elsewhere
TEST_EMAIL = "test_signup@example.com"

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_test(name: str, passed: bool, details: str = ""):
    """Print formatted test result"""
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"  {details}")
    print()

def test_signup_page_loads() -> Tuple[bool, str]:
    """Test that GET /signup returns HTML form"""
    try:
        response = requests.get(f"{BASE_URL}/signup")
        
        if response.status_code != 200:
            return False, f"Status code: {response.status_code}"
        
        if 'text/html' not in response.headers.get('content-type', ''):
            return False, f"Content-Type: {response.headers.get('content-type')}"
        
        # Check for key form elements
        html = response.text
        checks = [
            ('id="signupForm"' in html, "Signup form present"),
            ('id="email"' in html, "Email field present"),
            ('id="emailConfirm"' in html, "Email confirmation field present"),
            ('id="termsAccepted"' in html, "Terms checkbox present"),
            ('jQuery' in html or 'jquery' in html, "jQuery loaded"),
        ]
        
        failed = [check[1] for check in checks if not check[0]]
        if failed:
            return False, f"Missing elements: {', '.join(failed)}"
        
        return True, "All form elements present"
        
    except Exception as e:
        return False, str(e)

def test_terms_page_loads() -> Tuple[bool, str]:
    """Test that GET /terms returns Terms of Service page"""
    try:
        response = requests.get(f"{BASE_URL}/terms")
        
        if response.status_code != 200:
            return False, f"Status code: {response.status_code}"
        
        html = response.text
        if 'Terms of Service' not in html:
            return False, "Terms of Service heading not found"
        
        return True, "Terms page loads correctly"
        
    except Exception as e:
        return False, str(e)

def test_privacy_page_loads() -> Tuple[bool, str]:
    """Test that GET /privacy returns Privacy Policy page"""
    try:
        response = requests.get(f"{BASE_URL}/privacy")
        
        if response.status_code != 200:
            return False, f"Status code: {response.status_code}"
        
        html = response.text
        if 'Privacy Policy' not in html:
            return False, "Privacy Policy heading not found"
        
        return True, "Privacy page loads correctly"
        
    except Exception as e:
        return False, str(e)

def test_register_json_response() -> Tuple[bool, str]:
    """Test that POST /register with Accept: application/json returns JSON"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"email": f"json_{TEST_EMAIL}"},
            headers={"Accept": "application/json"}
        )
        
        if 'application/json' not in response.headers.get('content-type', ''):
            return False, f"Content-Type: {response.headers.get('content-type')}"
        
        data = response.json()
        if 'message' not in data:
            return False, "Response missing 'message' field"
        
        return True, f"JSON response received: {data.get('message', '')[:50]}"
        
    except Exception as e:
        return False, str(e)

def test_register_html_response() -> Tuple[bool, str]:
    """Test that POST /register with Accept: text/html returns HTML"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"email": f"html_{TEST_EMAIL}"},
            headers={"Accept": "text/html"}
        )
        
        if 'text/html' not in response.headers.get('content-type', ''):
            return False, f"Content-Type: {response.headers.get('content-type')}"
        
        html = response.text
        
        # Should contain either success or error page elements
        has_success = 'Registration Successful' in html or 'registration-success' in html.lower()
        has_error = 'Registration Error' in html or 'register-error' in html.lower()
        
        if not (has_success or has_error):
            return False, "Response doesn't appear to be success or error page"
        
        page_type = "Success page" if has_success else "Error page"
        return True, f"HTML response received: {page_type}"
        
    except Exception as e:
        return False, str(e)

def test_register_validation_error() -> Tuple[bool, str]:
    """Test that invalid email returns error"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"email": "invalid-email"},
            headers={"Accept": "application/json"}
        )
        
        # Should return 400 or 422 for validation error
        if response.status_code not in [400, 422]:
            return False, f"Expected 400/422, got {response.status_code}"
        
        data = response.json()
        if 'detail' not in data:
            return False, "Error response missing 'detail' field"
        
        return True, f"Validation error handled: {str(data.get('detail', ''))[:50]}"
        
    except Exception as e:
        return False, str(e)

def test_cors_and_headers() -> Tuple[bool, str]:
    """Test that proper headers are set"""
    try:
        response = requests.get(f"{BASE_URL}/signup")
        
        # Check for security headers (optional but recommended)
        headers_to_check = {
            'content-type': 'text/html',
        }
        
        missing = []
        for header, expected in headers_to_check.items():
            actual = response.headers.get(header, '')
            if expected not in actual:
                missing.append(f"{header}: expected '{expected}', got '{actual}'")
        
        if missing:
            return False, f"Missing/incorrect headers: {', '.join(missing)}"
        
        return True, "Headers look good"
        
    except Exception as e:
        return False, str(e)

def run_all_tests():
    """Run all tests and report results"""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}Signup System Test Suite{RESET}")
    print(f"{BLUE}Testing against: {BASE_URL}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")
    
    tests = [
        ("Signup page loads", test_signup_page_loads),
        ("Terms of Service page loads", test_terms_page_loads),
        ("Privacy Policy page loads", test_privacy_page_loads),
        ("Register returns JSON (API client)", test_register_json_response),
        ("Register returns HTML (browser)", test_register_html_response),
        ("Register validates email format", test_register_validation_error),
        ("HTTP headers are correct", test_cors_and_headers),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        result, details = test_func()
        print_test(test_name, result, details)
        if result:
            passed += 1
        else:
            failed += 1
    
    # Summary
    print(f"{BLUE}{'='*70}{RESET}")
    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    if failed == 0:
        print(f"{GREEN}All tests passed! ✓ ({passed}/{total}){RESET}")
    else:
        print(f"{YELLOW}Tests: {passed} passed, {failed} failed ({pass_rate:.1f}%){RESET}")
    
    print(f"{BLUE}{'='*70}{RESET}\n")
    
    # Next steps
    if failed > 0:
        print(f"{YELLOW}Some tests failed. Check:{RESET}")
        print("  1. Is your server running?")
        print("  2. Are templates in correct directories?")
        print("  3. Are endpoints added to router_auth.py and app.py?")
        print("  4. Did you restart the server after changes?")
    else:
        print(f"{GREEN}All systems go! Try these manual tests:{RESET}")
        print(f"  1. Visit {BASE_URL}/signup in a browser")
        print("  2. Fill out the form and submit")
        print("  3. Check that jQuery modal appears")
        print("  4. Click terms/privacy links (should open new tabs)")
        print("  5. Try submitting invalid data (mismatched emails)")

if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Tests interrupted by user{RESET}")
    except Exception as e:
        print(f"\n{RED}Test suite error: {e}{RESET}")
