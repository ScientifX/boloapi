"""
Role-Based Access Control Tests

Tests authentication and authorization for different user roles:
- PUBLIC: No access to protected endpoints
- BASIC: Simple search only, max 25 results, returns full_data
- PREMIUM: Simple + Advanced search, max 5000 results, returns full_data_clean  
- ADMIN: All endpoints including ETL, max 5000 results, returns full_data_clean

Each test includes both positive (should succeed) and negative (should fail) scenarios.
"""
import requests
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"

# Role definitions matching auth.py
ROLES = {
    "PUBLIC": "public",
    "BASIC": "basic", 
    "PREMIUM": "premium",
    "ADMIN": "admin"
}

# Test API keys for each role (these should be set up in your database)
# Update these with actual keys from your database
TEST_KEYS = {
    "PUBLIC": None,  # No key for public
    "BASIC": "Ag6xY1pNd7i2XG2Uxbt5DGhu3UaS0Mra",   # jerry.bradenbaugh@gmail.com
    "PREMIUM": "iZjNSzftP3h4ZTUpTlouojSNeeR2GpSo", # premium.user3@example.com
    "ADMIN": "2aaonQ80N1LH2ZB89cAV8DhBqrVC4BSH"    # admin.user1@example.com 
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def capture_json_response(data: Optional[Dict]) -> str:
    """
    Capture JSON response for reporting, truncating large data.
    
    Args:
        data: Response data dictionary
        
    Returns:
        JSON string suitable for reporting
    """
    if not data:
        return "null"
    
    # Make a copy to avoid modifying original
    response_copy = data.copy() if isinstance(data, dict) else data
    
    # Truncate 'items' array if present (often huge)
    if isinstance(response_copy, dict) and 'items' in response_copy:
        item_count = len(response_copy['items']) if isinstance(response_copy['items'], list) else 0
        response_copy['items'] = f"[{item_count} items - truncated for brevity]"
    
    # Convert to JSON string
    try:
        return json.dumps(response_copy, indent=2)
    except:
        return str(response_copy)

def format_json_for_markdown(json_str: str, max_length: int = 500) -> str:
    """
    Format JSON string for markdown table display.
    
    Args:
        json_str: JSON string to format
        max_length: Maximum length before truncation
        
    Returns:
        Formatted string for markdown
    """
    if not json_str or json_str == "null":
        return "N/A"
    
    # Truncate if too long
    if len(json_str) > max_length:
        truncated = json_str[:max_length] + "..."
        return f"`{truncated}`"
    else:
        return f"`{json_str}`"

def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)

def print_response(response: requests.Response, expected_status: Optional[int] = None) -> Optional[Dict[Any, Any]]:
    """
    Print formatted response and validate expected status
    
    Args:
        response: The HTTP response object
        expected_status: Expected status code (if None, any status is acceptable)
    """
    print(f"Status: {response.status_code}", end="")
    
    if expected_status:
        if response.status_code == expected_status:
            print(" ✓ (Expected)")
        else:
            print(f" ✗ (Expected {expected_status})")
    else:
        print()
    
    try:
        data = response.json()
        
        # Don't print massive JSON responses - just summarize
        if isinstance(data, dict):
            # Show high-level keys
            keys = list(data.keys())
            print(f"Response keys: {keys}")
            
            # Show specific useful fields without the full data
            if 'resultcount' in data:
                print(f"  Result count: {data['resultcount']}")
            if 'role' in data:
                print(f"  Role: {data['role']}")
            if 'data_field' in data:
                print(f"  Data field: {data['data_field']}")
            if 'detail' in data:
                print(f"  Detail: {data['detail']}")
            if 'error' in data:
                print(f"  Error: {data['error']}")
            if 'message' in data:
                print(f"  Message: {data['message']}")
        else:
            print(f"Response: {str(data)[:200]}")  # First 200 chars only
        
        # Always return the full data for test functions to use
        return data
    except:
        print(f"Response: {response.text[:200]}")  # First 200 chars only
        # Return text as dict with 'raw_text' key if not JSON
        return {"raw_text": response.text}

def get_token_for_role(role: str) -> Optional[str]:
    """
    Get JWT token for a given role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        
    Returns:
        JWT token string or None for PUBLIC
    """
    if role == "PUBLIC":
        return None
    
    api_key = TEST_KEYS.get(role)
    if not api_key:
        print(f"⚠ Warning: No API key configured for role {role}")
        return None
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/token",
            json={"api_key": api_key}
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['access_token']
        else:
            print(f"✗ Failed to get token for {role}: {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error getting token for {role}: {str(e)}")
        return None

def make_request(
    method: str,
    endpoint: str, 
    token: Optional[str] = None,
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None
) -> requests.Response:
    """
    Make an HTTP request with optional JWT token
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        token: Optional JWT token
        json_data: Optional JSON payload
        params: Optional query parameters
        
    Returns:
        Response object
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    url = f"{BASE_URL}{endpoint}"
    
    if method.upper() == "GET":
        return requests.get(url, headers=headers, params=params)
    elif method.upper() == "POST":
        return requests.post(url, headers=headers, json=json_data, params=params)
    else:
        raise ValueError(f"Unsupported method: {method}")

# ============================================================================
# SIMPLE SEARCH TESTS
# ============================================================================

def test_simple_search_access(role: str, should_succeed: bool = True) -> Dict[str, Any]:
    """
    Test simple search access for a given role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        should_succeed: Whether the request should succeed (True) or fail (False)
        
    Returns:
        Dict with test results
    """
    print_section(f"Simple Search Access - {role} (should {'succeed' if should_succeed else 'fail'})")
    
    token = get_token_for_role(role)
    
    if role == "PUBLIC" and not token:
        print("Testing as PUBLIC user (no token)")
    elif token:
        print(f"Testing as {role} user with token: {token[:50]}...")
    else:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    # Simple search request
    search_payload = {
        "filters": [
            {"field": "sex", "value": "Male"}
        ],
        "limit": 25
    }
    
    response = make_request("POST", "/api/search/simple", token=token, json_data=search_payload)
    
    expected_status = 200 if should_succeed else 401
    data = print_response(response, expected_status=expected_status)
    
    # Capture JSON for reporting
    json_request = json.dumps(search_payload, indent=2)
    json_response = capture_json_response(data)
    
    # Validate result
    if should_succeed:
        if response.status_code == 200 and data:
            print(f"\n✓ {role} successfully accessed simple search")
            print(f"  Role in response: {data.get('role')}")
            print(f"  Data field: {data.get('data_field')}")
            print(f"  Results: {data.get('resultcount')}")
            return {
                "success": True,
                "status_code": response.status_code,
                "role": data.get('role'),
                "data_field": data.get('data_field'),
                "resultcount": data.get('resultcount'),
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have succeeded but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        if response.status_code in [401, 403]:
            print(f"\n✓ {role} correctly denied access (status {response.status_code})")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "correctly_denied": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have been denied but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }

def test_simple_search_limits(role: str, test_limit: int, should_succeed: bool = True) -> Dict[str, Any]:
    """
    Test result limit enforcement for simple search
    
    Args:
        role: Role name (BASIC, PREMIUM, ADMIN)
        test_limit: Limit to test (25, 50, 100, 5000)
        should_succeed: Whether the limit should be accepted
        
    Returns:
        Dict with test results
    """
    print_section(f"Simple Search Limit Test - {role} requesting {test_limit} (should {'succeed' if should_succeed else 'fail'})")
    
    token = get_token_for_role(role)
    
    if not token:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    # Search with specified limit
    search_payload = {
        "filters": [
            {"field": "sex", "value": "Male"}
        ],
        "limit": test_limit
    }
    
    response = make_request("POST", "/api/search/simple", token=token, json_data=search_payload)
    
    expected_status = 200 if should_succeed else 403
    data = print_response(response, expected_status=expected_status)
    
    # Capture JSON for reporting
    json_request = json.dumps(search_payload, indent=2)
    json_response = capture_json_response(data)
    
    if should_succeed:
        if response.status_code == 200:
            print(f"\n✓ {role} successfully requested limit of {test_limit}")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "limit_accepted": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have succeeded with limit {test_limit}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        if response.status_code == 403:
            print(f"\n✓ {role} correctly denied limit of {test_limit}")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "correctly_denied": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have been denied limit {test_limit}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }

def test_simple_search_data_field(role: str, expected_field: str) -> Dict[str, Any]:
    """
    Test which data field is returned for a given role
    
    Args:
        role: Role name (BASIC, PREMIUM, ADMIN)
        expected_field: Expected data field (full_data or full_data_clean)
        
    Returns:
        Dict with test results
    """
    print_section(f"Simple Search Data Field Test - {role} (expecting {expected_field})")
    
    token = get_token_for_role(role)
    
    if not token:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    search_payload = {
        "filters": [
            {"field": "sex", "value": "Male"}
        ],
        "limit": 25
    }
    
    response = make_request("POST", "/api/search/simple", token=token, json_data=search_payload)
    data = print_response(response, expected_status=200)
    
    # Capture JSON for reporting
    json_request = json.dumps(search_payload, indent=2)
    json_response = capture_json_response(data)
    
    if response.status_code == 200 and data:
        actual_field = data.get('data_field')
        if actual_field == expected_field:
            print(f"\n✓ {role} correctly receives {expected_field}")
            return {
                "success": True, 
                "data_field": actual_field, 
                "matches_expected": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} expected {expected_field} but got {actual_field}")
            return {
                "success": False, 
                "data_field": actual_field, 
                "expected": expected_field,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        print(f"\n✗ Request failed with status {response.status_code}")
        return {
            "success": False, 
            "status_code": response.status_code,
            "json_request": json_request,
            "json_response": json_response
        }

# ============================================================================
# ADVANCED SEARCH TESTS
# ============================================================================

def test_advanced_search_access(role: str, should_succeed: bool = True) -> Dict[str, Any]:
    """
    Test advanced search access for a given role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        should_succeed: Whether the request should succeed
        
    Returns:
        Dict with test results
    """
    print_section(f"Advanced Search Access - {role} (should {'succeed' if should_succeed else 'fail'})")
    
    token = get_token_for_role(role)
    
    print(f"Role: {role}")
    print(f"Token: {token}")

    if role == "PUBLIC" and not token:
        print("Testing as PUBLIC user (no token)")
    elif token:
        print(f"Testing as {role} user")
    else:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    # Advanced search request with grouped conditions
    search_payload = {
        "groups": [
            {
                "condition": "AND",
                "rules": [
                    {"field": "sex", "operator": "equals", "value": "Male"},
                    {"field": "age_min", "operator": "gte", "value": 25}
                ]
            }
        ],
        "group_logic": "AND",
        "limit": 25
    }
    
    response = make_request("POST", "/api/search/advanced", token=token, json_data=search_payload)
    
    expected_status = 200 if should_succeed else (401 if role == "PUBLIC" else 403)
    data = print_response(response, expected_status=expected_status)
    
    # Capture JSON for reporting
    json_request = json.dumps(search_payload, indent=2)
    json_response = capture_json_response(data)
    
    # Check for the "Extra inputs" bug
    if response.status_code == 422 and data and isinstance(data, dict):
        if 'detail' in data:
            detail_str = str(data['detail'])
            if 'Extra inputs are not allowed' in detail_str or 'extra fields not permitted' in detail_str:
                print(f"\n⚠️  BUG DETECTED: Advanced search endpoint has wrong request type")
                print(f"    router_search.py line 1171 should use AdvancedSearchRequest, not SimpleSearchRequest")
                print(f"    This causes Pydantic validation to reject 'groups' and 'group_logic' fields")
                # Treat as a special test failure with bug note
                return {
                    "success": False, 
                    "status_code": response.status_code,
                    "reason": "endpoint_bug",
                    "bug_note": "Wrong request model in endpoint definition",
                    "json_request": json_request,
                    "json_response": json_response
                }
    
    if should_succeed:
        if response.status_code == 200 and data:
            print(f"\n✓ {role} successfully accessed advanced search")
            print(f"  Results: {data.get('resultcount')}")
            return {
                "success": True, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have succeeded but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        if response.status_code in [401, 403]:
            print(f"\n✓ {role} correctly denied access to advanced search")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "correctly_denied": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have been denied but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }

# ============================================================================
# ETL ENDPOINT TESTS
# ============================================================================

def test_etl_extract_access(role: str, should_succeed: bool = True) -> Dict[str, Any]:
    """
    Test ETL extract endpoint access for a given role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        should_succeed: Whether the request should succeed
        
    Returns:
        Dict with test results
    """
    print_section(f"ETL Extract Access - {role} (should {'succeed' if should_succeed else 'fail'})")
    
    token = get_token_for_role(role)
    
    if role == "PUBLIC" and not token:
        print("Testing as PUBLIC user (no token)")
    elif token:
        print(f"Testing as {role} user")
    else:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    # ETL extract request
    params = {"format": "json", "size": "default"}
    
    response = make_request("GET", "/api/etl/extract", token=token, params=params)
    
    expected_status = 200 if should_succeed else (401 if role == "PUBLIC" else 403)
    data = print_response(response, expected_status=expected_status)
    
    # Capture JSON for reporting (GET requests have params, not body)
    json_request = f"GET params: {json.dumps(params, indent=2)}"
    json_response = capture_json_response(data)
    
    if should_succeed:
        if response.status_code == 200:
            print(f"\n✓ {role} successfully accessed ETL extract")
            return {
                "success": True, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have succeeded but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        if response.status_code in [401, 403]:
            print(f"\n✓ {role} correctly denied access to ETL extract")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "correctly_denied": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have been denied but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }

def test_etl_load_access(role: str, should_succeed: bool = True) -> Dict[str, Any]:
    """
    Test ETL load endpoint access for a given role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        should_succeed: Whether the request should succeed
        
    Returns:
        Dict with test results
    """
    print_section(f"ETL Load Access - {role} (should {'succeed' if should_succeed else 'fail'})")
    
    token = get_token_for_role(role)
    
    if role == "PUBLIC" and not token:
        print("Testing as PUBLIC user (no token)")
    elif token:
        print(f"Testing as {role} user")
    else:
        print(f"✗ Could not get token for {role}")
        return {"success": False, "reason": "no_token"}
    
    response = make_request("GET", "/api/etl/load", token=token)
    
    expected_status = 200 if should_succeed else (401 if role == "PUBLIC" else 403)
    data = print_response(response, expected_status=expected_status)
    
    # Capture JSON for reporting (GET request, no body/params)
    json_request = "GET /api/etl/load (no params)"
    json_response = capture_json_response(data)
    
    if should_succeed:
        if response.status_code == 200:
            print(f"\n✓ {role} successfully accessed ETL load")
            return {
                "success": True, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have succeeded but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }
    else:
        if response.status_code in [401, 403]:
            print(f"\n✓ {role} correctly denied access to ETL load")
            return {
                "success": True, 
                "status_code": response.status_code, 
                "correctly_denied": True,
                "json_request": json_request,
                "json_response": json_response
            }
        else:
            print(f"\n✗ {role} should have been denied but got status {response.status_code}")
            return {
                "success": False, 
                "status_code": response.status_code,
                "json_request": json_request,
                "json_response": json_response
            }

# ============================================================================
# MARKDOWN REPORT GENERATION
# ============================================================================

def generate_markdown_report(
    all_results: Dict[str, Any],
    all_passed_tests: List[Dict],
    all_failed_tests: List[Dict],
    total_passed: int,
    total_tests: int
) -> str:
    """
    Generate a clean, attractive markdown report of test results
    
    Args:
        all_results: Dict with all role test results
        all_passed_tests: List of all passed tests with details
        all_failed_tests: List of all failed tests with details
        total_passed: Total number of passed tests
        total_tests: Total number of tests run
        
    Returns:
        Filename of the generated report
    """
    from datetime import datetime
    import os
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Cross-platform path handling
    output_dir = "/mnt/user-data/outputs" if os.path.exists("/mnt/user-data/outputs") else "."
    filename = os.path.join(output_dir, f"logs/test_report_{timestamp}.md")
    
    overall_percentage = (total_passed / total_tests * 100) if total_tests > 0 else 0
    failed_count = total_tests - total_passed
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Header
        f.write("# Role-Based Access Control Test Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        
        # Executive Summary
        f.write("## Executive Summary\n\n")
        
        if overall_percentage == 100:
            f.write("### ✅ All Tests Passed\n\n")
            f.write(f"**{total_passed}/{total_tests}** tests passed successfully (**{overall_percentage:.1f}%**)\n\n")
            f.write("🎉 The role-based access control system is functioning correctly. All roles have appropriate access levels and restrictions.\n\n")
        else:
            f.write("### ⚠️ Some Tests Failed\n\n")
            f.write(f"**{total_passed}/{total_tests}** tests passed (**{overall_percentage:.1f}%**)\n\n")
            f.write(f"**{failed_count}** test(s) failed and require attention.\n\n")
        
        # Quick Stats Table
        f.write("### Test Statistics\n\n")
        f.write("| Metric | Count | Percentage |\n")
        f.write("|--------|-------|------------|\n")
        f.write(f"| **Total Tests** | {total_tests} | 100% |\n")
        f.write(f"| **Passed** | {total_passed} | {overall_percentage:.1f}% |\n")
        f.write(f"| **Failed** | {failed_count} | {100-overall_percentage:.1f}% |\n\n")
        
        # Role Breakdown Table
        f.write("### Role Performance\n\n")
        f.write("| Role | Passed | Failed | Total | Success Rate |\n")
        f.write("|------|--------|--------|-------|-------------|\n")
        
        for role, result in all_results.items():
            passed = result.get("passed", 0)
            total = result.get("total", 0)
            failed = total - passed
            percentage = (passed / total * 100) if total > 0 else 0
            status_icon = "✅" if passed == total else "⚠️"
            f.write(f"| {status_icon} **{role}** | {passed} | {failed} | {total} | {percentage:.1f}% |\n")
        
        f.write("\n---\n\n")
        
        # Detailed Results by Role
        f.write("## Detailed Results by Role\n\n")
        
        for role, result in all_results.items():
            passed = result.get("passed", 0)
            total = result.get("total", 0)
            percentage = (passed / total * 100) if total > 0 else 0
            
            status_icon = "✅" if passed == total else "⚠️"
            
            f.write(f"### {status_icon} {role} Role\n\n")
            f.write(f"**Result:** {passed}/{total} tests passed ({percentage:.1f}%)\n\n")
            
            # Role description
            if role == "PUBLIC":
                f.write("**Expected Behavior:** Should be denied all protected endpoints (401 Unauthorized)\n\n")
            elif role == "BASIC":
                f.write("**Expected Behavior:** Simple search only, max 25 results, returns `full_data`\n\n")
            elif role == "PREMIUM":
                f.write("**Expected Behavior:** Simple + Advanced search, max 5000 results, returns `full_data_clean`\n\n")
            elif role == "ADMIN":
                f.write("**Expected Behavior:** All endpoints including ETL, max 5000 results, returns `full_data_clean`\n\n")
            
            # Passed tests for this role
            role_passed = [(name, res) for name, res in result.get("results", []) if res.get("success")]
            role_failed = [(name, res) for name, res in result.get("results", []) if not res.get("success")]
            
            if role_passed:
                f.write("#### ✅ Passed Tests\n\n")
                f.write("| Test | Details |\n")
                f.write("|------|----------|\n")
                
                for test_name, test_result in role_passed:
                    reason_parts = []
                    if "status_code" in test_result:
                        reason_parts.append(f"Status: {test_result['status_code']}")
                    if test_result.get('correctly_denied'):
                        reason_parts.append("✓ Correctly denied")
                    if test_result.get('matches_expected'):
                        reason_parts.append(f"✓ Field: `{test_result.get('data_field')}`")
                    if test_result.get('limit_accepted'):
                        reason_parts.append("✓ Limit accepted")
                    if "resultcount" in test_result:
                        reason_parts.append(f"Results: {test_result['resultcount']}")
                    
                    reason = "<br>".join(reason_parts) if reason_parts else "Passed"
                    f.write(f"| `{test_name}` | {reason} |\n")
                f.write("\n")
            
            if role_failed:
                f.write("#### ❌ Failed Tests\n\n")
                f.write("| Test | Issue | Details | JSON Request | JSON Response |\n")
                f.write("|------|-------|---------|--------------|---------------|\n")
                
                for test_name, test_result in role_failed:
                    # Determine issue type
                    issue_type = "Unknown"
                    details = []
                    
                    if test_result.get('reason') == 'no_token':
                        issue_type = "Authentication"
                        details.append("⚠️ Failed to get token")
                    elif "status_code" in test_result:
                        status = test_result['status_code']
                        details.append(f"Status: {status}")
                        
                        if status == 200 and not test_result.get('success'):
                            issue_type = "Authorization"
                            details.append("❌ Succeeded when should have failed")
                        elif status == 401:
                            issue_type = "Authentication"
                            details.append("❌ Unauthorized - token issue")
                        elif status == 403:
                            issue_type = "Authorization"
                            details.append("❌ Forbidden - role insufficient")
                        elif status == 500:
                            issue_type = "Server Error"
                            details.append("❌ Internal server error")
                        else:
                            issue_type = "Unexpected"
                            details.append(f"❌ Unexpected status")
                    
                    if "data_field" in test_result and "expected" in test_result:
                        issue_type = "Data Field"
                        details.append(f"❌ Got `{test_result['data_field']}`, expected `{test_result['expected']}`")
                    
                    detail_text = "<br>".join(details) if details else "See logs"
                    
                    # Get JSON request and response
                    json_req = test_result.get('json_request', 'N/A')
                    json_req_display = format_json_for_markdown(json_req, max_length=300)
                    
                    json_resp = test_result.get('json_response', 'N/A')
                    json_resp_display = format_json_for_markdown(json_resp, max_length=500)
                    
                    f.write(f"| `{test_name}` | {issue_type} | {detail_text} | {json_req_display} | {json_resp_display} |\n")
                f.write("\n")
            
            f.write("---\n\n")
        
        # All Passed Tests Section
        if all_passed_tests:
            f.write("## ✅ All Passed Tests\n\n")
            f.write("Complete list of all successful tests across all roles.\n\n")
            f.write("| Role | Test | Details |\n")
            f.write("|------|------|----------|\n")
            
            for item in all_passed_tests:
                role = item["role"]
                test = item["test"]
                result = item["result"]
                
                reason_parts = []
                if "status_code" in result:
                    reason_parts.append(f"Status: {result['status_code']}")
                if result.get('correctly_denied'):
                    reason_parts.append("Correctly denied")
                if result.get('data_field'):
                    reason_parts.append(f"Field: `{result['data_field']}`")
                if result.get('resultcount'):
                    reason_parts.append(f"{result['resultcount']} results")
                
                reason = "<br>".join(reason_parts) if reason_parts else "Passed"
                f.write(f"| **{role}** | `{test}` | {reason} |\n")
            
            f.write("\n---\n\n")
        
        # All Failed Tests Section
        if all_failed_tests:
            f.write("## ❌ All Failed Tests\n\n")
            f.write("Complete list of all failed tests that require attention.\n\n")
            f.write("| Priority | Role | Test | Issue | Action | JSON Request | JSON Response |\n")
            f.write("|----------|------|------|-------|--------|--------------|---------------|\n")
            
            for item in all_failed_tests:
                role = item["role"]
                test = item["test"]
                result = item["result"]
                
                # Determine priority
                if result.get('reason') == 'no_token':
                    priority = "🔴 High"
                    issue = "Authentication failure"
                    action = "Check TEST_KEYS config and database"
                elif result.get('status_code') == 500:
                    priority = "🔴 High"
                    issue = "Server error"
                    action = "Check API logs and database"
                elif result.get('status_code') == 200 and not result.get('success'):
                    priority = "🟠 Medium"
                    issue = "Access control broken"
                    action = "Review role requirements in endpoint"
                elif "expected" in result:
                    priority = "🟡 Low"
                    issue = "Wrong data field"
                    action = "Check get_data_field_for_role()"
                else:
                    priority = "🟠 Medium"
                    issue = f"Status: {result.get('status_code', 'N/A')}"
                    action = "Review endpoint logic"
                
                # Get JSON request and response
                json_req = result.get('json_request', 'N/A')
                json_req_display = format_json_for_markdown(json_req, max_length=250)
                
                json_resp = result.get('json_response', 'N/A')
                json_resp_display = format_json_for_markdown(json_resp, max_length=400)
                
                f.write(f"| {priority} | **{role}** | `{test}` | {issue} | {action} | {json_req_display} | {json_resp_display} |\n")
            
            f.write("\n---\n\n")
        
        # Recommendations Section
        f.write("## 🔍 Recommendations\n\n")
        
        if overall_percentage == 100:
            f.write("### System Status: Healthy ✅\n\n")
            f.write("All tests passed successfully. The role-based access control system is working as expected.\n\n")
            f.write("**Suggested Actions:**\n")
            f.write("- ✅ Deploy to production with confidence\n")
            f.write("- ✅ Run tests regularly to catch regressions\n")
            f.write("- ✅ Keep test API keys secure and rotated\n\n")
        else:
            f.write("### System Status: Needs Attention ⚠️\n\n")
            f.write(f"**{failed_count}** test(s) failed. Please address the following issues:\n\n")
            
            # Categorize failures
            auth_failures = [f for f in all_failed_tests if f["result"].get("reason") == "no_token"]
            authz_failures = [f for f in all_failed_tests if f["result"].get("status_code") in [200, 403] and not f["result"].get("success")]
            server_failures = [f for f in all_failed_tests if f["result"].get("status_code") == 500]
            
            if auth_failures:
                f.write(f"#### 🔴 Authentication Issues ({len(auth_failures)})\n\n")
                f.write("**Problem:** Cannot generate tokens for some roles.\n\n")
                f.write("**Action Items:**\n")
                f.write("1. Verify TEST_KEYS in `test_roles.py` contains valid API keys\n")
                f.write("2. Check that test users exist in database and are active\n")
                f.write("3. Ensure API key hashes match in database\n")
                f.write("4. Test token generation endpoint directly\n\n")
            
            if authz_failures:
                f.write(f"#### 🟠 Authorization Issues ({len(authz_failures)})\n\n")
                f.write("**Problem:** Role-based access control not working correctly.\n\n")
                f.write("**Action Items:**\n")
                f.write("1. Review `require_jwt_role()` calls in affected endpoints\n")
                f.write("2. Verify role requirements match documentation\n")
                f.write("3. Check `has_role()` hierarchy logic\n")
                f.write("4. Test affected endpoints manually with different roles\n\n")
            
            if server_failures:
                f.write(f"#### 🔴 Server Errors ({len(server_failures)})\n\n")
                f.write("**Problem:** API returning 500 errors.\n\n")
                f.write("**Action Items:**\n")
                f.write("1. Check FastAPI application logs\n")
                f.write("2. Verify database connection\n")
                f.write("3. Review error traces for exceptions\n")
                f.write("4. Ensure data exists for test queries\n\n")
        
        # Test Configuration Section
        f.write("---\n\n")
        f.write("## 📋 Test Configuration\n\n")
        f.write("### Test Environment\n\n")
        f.write(f"- **API Base URL:** `{BASE_URL}`\n")
        f.write(f"- **Test Framework:** Role-Based Access Control Tests v1.0\n")
        f.write(f"- **Roles Tested:** {', '.join(all_results.keys())}\n")
        f.write(f"- **Total Test Cases:** {total_tests}\n\n")
        
        f.write("### Role Specifications\n\n")
        f.write("| Role | Search Access | Result Limit | Data Field | ETL Access |\n")
        f.write("|------|--------------|--------------|------------|------------|\n")
        f.write("| PUBLIC | ❌ None | - | - | ❌ |\n")
        f.write("| BASIC | ✅ Simple | 25 | `full_data` | ❌ |\n")
        f.write("| PREMIUM | ✅ Simple + Advanced | 5000 | `full_data_clean` | ❌ |\n")
        f.write("| ADMIN | ✅ All | 5000 | `full_data_clean` | ✅ |\n\n")
        
        # Footer
        f.write("---\n\n")
        f.write("## 📚 Additional Resources\n\n")
        f.write("- **Setup Guide:** `README_TESTING.md`\n")
        f.write("- **Quick Reference:** `QUICK_REFERENCE.md`\n")
        f.write("- **Example Output:** `EXAMPLE_OUTPUT.md`\n")
        f.write("- **Test Source:** `test_roles.py`\n\n")
        f.write("---\n\n")
        f.write(f"*Report generated by Role-Based Access Control Test Suite*\n")
        f.write(f"*Timestamp: {datetime.now().isoformat()}*\n")
    
    return filename

# ============================================================================
# COMPREHENSIVE ROLE TEST SUITES
# ============================================================================

def test_public_role() -> Dict[str, Any]:
    """
    Test PUBLIC role - should be denied all protected endpoints
    
    Returns:
        Dict with test results summary
    """
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  PUBLIC ROLE TEST SUITE".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    results = []
    
    # PUBLIC should be denied all search endpoints
    results.append(("simple_search", test_simple_search_access("PUBLIC", should_succeed=False)))
    results.append(("advanced_search", test_advanced_search_access("PUBLIC", should_succeed=False)))
    results.append(("etl_extract", test_etl_extract_access("PUBLIC", should_succeed=False)))
    results.append(("etl_load", test_etl_load_access("PUBLIC", should_succeed=False)))
    
    # Summary
    passed = sum(1 for _, r in results if r.get("success"))
    total = len(results)
    
    print("\n" + "="*70)
    print(f" PUBLIC ROLE SUMMARY: {passed}/{total} tests passed")
    print("="*70)
    
    # Detailed results
    passed_tests = []
    failed_tests = []
    
    for test_name, result in results:
        if result.get("success"):
            passed_tests.append((test_name, result))
        else:
            failed_tests.append((test_name, result))
    
    # Show passed tests
    if passed_tests:
        print("\n  PASSED:")
        for test_name, result in passed_tests:
            reason = f"status={result.get('status_code')}, correctly denied" if result.get('correctly_denied') else f"status={result.get('status_code')}"
            print(f"    ✓ {test_name:30s} ({reason})")
    
    # Show failed tests
    if failed_tests:
        print("\n  FAILED:")
        for test_name, result in failed_tests:
            status = result.get('status_code', 'N/A')
            reason = result.get('reason', 'unknown')
            if reason == 'no_token':
                detail = "failed to get token"
            elif status not in [401, 403]:
                detail = f"expected 401/403, got {status}"
            else:
                detail = f"status={status}"
            print(f"    ✗ {test_name:30s} ({detail})")
    
    return {"role": "PUBLIC", "passed": passed, "total": total, "results": results}

def test_basic_role() -> Dict[str, Any]:
    """
    Test BASIC role - simple search only, max 25 results, full_data
    
    Returns:
        Dict with test results summary
    """
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  BASIC ROLE TEST SUITE".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    results = []
    
    # BASIC should have access to simple search
    results.append(("simple_search_access", test_simple_search_access("BASIC", should_succeed=True)))
    
    # BASIC should get full_data field
    results.append(("data_field_full_data", test_simple_search_data_field("BASIC", "full_data")))
    
    # BASIC should be limited to 25 results
    results.append(("limit_25_allowed", test_simple_search_limits("BASIC", 25, should_succeed=True)))
    results.append(("limit_50_denied", test_simple_search_limits("BASIC", 50, should_succeed=False)))
    results.append(("limit_5000_denied", test_simple_search_limits("BASIC", 5000, should_succeed=False)))
    
    # BASIC should be denied advanced search
    results.append(("advanced_search_denied", test_advanced_search_access("BASIC", should_succeed=False)))
    
    # BASIC should be denied ETL endpoints
    results.append(("etl_extract_denied", test_etl_extract_access("BASIC", should_succeed=False)))
    results.append(("etl_load_denied", test_etl_load_access("BASIC", should_succeed=False)))
    
    # Summary
    passed = sum(1 for _, r in results if r.get("success"))
    total = len(results)
    
    print("\n" + "="*70)
    print(f" BASIC ROLE SUMMARY: {passed}/{total} tests passed")
    print("="*70)
    
    # Detailed results
    passed_tests = []
    failed_tests = []
    
    for test_name, result in results:
        if result.get("success"):
            passed_tests.append((test_name, result))
        else:
            failed_tests.append((test_name, result))
    
    # Show passed tests
    if passed_tests:
        print("\n  PASSED:")
        for test_name, result in passed_tests:
            reason_parts = []
            if "status_code" in result:
                reason_parts.append(f"status={result['status_code']}")
            if result.get('correctly_denied'):
                reason_parts.append("correctly denied")
            if result.get('matches_expected'):
                reason_parts.append(f"field={result.get('data_field')}")
            if result.get('limit_accepted'):
                reason_parts.append("limit accepted")
            reason = ", ".join(reason_parts) if reason_parts else "passed"
            print(f"    ✓ {test_name:30s} ({reason})")
    
    # Show failed tests
    if failed_tests:
        print("\n  FAILED:")
        for test_name, result in failed_tests:
            reason_parts = []
            if result.get('reason') == 'no_token':
                reason_parts.append("failed to get token")
            if "status_code" in result:
                status = result['status_code']
                reason_parts.append(f"status={status}")
                if status == 200 and not result.get('success'):
                    reason_parts.append("should have been denied")
                elif status not in [200, 403]:
                    reason_parts.append(f"unexpected")
            if "data_field" in result and "expected" in result:
                reason_parts.append(f"got {result['data_field']}, expected {result['expected']}")
            reason = ", ".join(reason_parts) if reason_parts else "unknown failure"
            print(f"    ✗ {test_name:30s} ({reason})")
    
    return {"role": "BASIC", "passed": passed, "total": total, "results": results}

def test_premium_role() -> Dict[str, Any]:
    """
    Test PREMIUM role - simple + advanced search, max 5000 results, full_data_clean
    
    Returns:
        Dict with test results summary
    """
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  PREMIUM ROLE TEST SUITE".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    results = []
    
    # PREMIUM should have access to simple search
    results.append(("simple_search_access", test_simple_search_access("PREMIUM", should_succeed=True)))
    
    # PREMIUM should have access to advanced search
    results.append(("advanced_search_access", test_advanced_search_access("PREMIUM", should_succeed=True)))
    
    # PREMIUM should get full_data_clean field
    results.append(("data_field_full_data_clean", test_simple_search_data_field("PREMIUM", "full_data_clean")))
    
    # PREMIUM should allow up to 5000 results
    results.append(("limit_25_allowed", test_simple_search_limits("PREMIUM", 25, should_succeed=True)))
    results.append(("limit_500_allowed", test_simple_search_limits("PREMIUM", 500, should_succeed=True)))
    results.append(("limit_5000_allowed", test_simple_search_limits("PREMIUM", 5000, should_succeed=True)))
    
    # PREMIUM should be denied ETL endpoints
    results.append(("etl_extract_denied", test_etl_extract_access("PREMIUM", should_succeed=False)))
    results.append(("etl_load_denied", test_etl_load_access("PREMIUM", should_succeed=False)))
    
    # Summary
    passed = sum(1 for _, r in results if r.get("success"))
    total = len(results)
    
    print("\n" + "="*70)
    print(f" PREMIUM ROLE SUMMARY: {passed}/{total} tests passed")
    print("="*70)
    
    # Detailed results
    passed_tests = []
    failed_tests = []
    
    for test_name, result in results:
        if result.get("success"):
            passed_tests.append((test_name, result))
        else:
            failed_tests.append((test_name, result))
    
    # Show passed tests
    if passed_tests:
        print("\n  PASSED:")
        for test_name, result in passed_tests:
            reason_parts = []
            if "status_code" in result:
                reason_parts.append(f"status={result['status_code']}")
            if result.get('correctly_denied'):
                reason_parts.append("correctly denied")
            if result.get('matches_expected'):
                reason_parts.append(f"field={result.get('data_field')}")
            if result.get('limit_accepted'):
                reason_parts.append("limit accepted")
            reason = ", ".join(reason_parts) if reason_parts else "passed"
            print(f"    ✓ {test_name:30s} ({reason})")
    
    # Show failed tests
    if failed_tests:
        print("\n  FAILED:")
        for test_name, result in failed_tests:
            reason_parts = []
            if result.get('reason') == 'no_token':
                reason_parts.append("failed to get token")
            if "status_code" in result:
                status = result['status_code']
                reason_parts.append(f"status={status}")
                if status == 200 and not result.get('success'):
                    reason_parts.append("should have been denied")
                elif status not in [200, 403]:
                    reason_parts.append(f"unexpected")
            if "data_field" in result and "expected" in result:
                reason_parts.append(f"got {result['data_field']}, expected {result['expected']}")
            reason = ", ".join(reason_parts) if reason_parts else "unknown failure"
            print(f"    ✗ {test_name:30s} ({reason})")
    
    return {"role": "PREMIUM", "passed": passed, "total": total, "results": results}

def test_admin_role() -> Dict[str, Any]:
    """
    Test ADMIN role - all endpoints, max 5000 results, full_data_clean
    
    Returns:
        Dict with test results summary
    """
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  ADMIN ROLE TEST SUITE".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    results = []
    
    # ADMIN should have access to all search endpoints
    results.append(("simple_search_access", test_simple_search_access("ADMIN", should_succeed=True)))
    results.append(("advanced_search_access", test_advanced_search_access("ADMIN", should_succeed=True)))
    
    # ADMIN should get full_data_clean field
    results.append(("data_field_full_data_clean", test_simple_search_data_field("ADMIN", "full_data_clean")))
    
    # ADMIN should allow up to 5000 results
    results.append(("limit_5000_allowed", test_simple_search_limits("ADMIN", 5000, should_succeed=True)))
    
    # ADMIN should have access to ETL endpoints
    results.append(("etl_extract_access", test_etl_extract_access("ADMIN", should_succeed=True)))
    results.append(("etl_load_access", test_etl_load_access("ADMIN", should_succeed=True)))
    
    # Summary
    passed = sum(1 for _, r in results if r.get("success"))
    total = len(results)
    
    print("\n" + "="*70)
    print(f" ADMIN ROLE SUMMARY: {passed}/{total} tests passed")
    print("="*70)
    
    # Detailed results
    passed_tests = []
    failed_tests = []
    
    for test_name, result in results:
        if result.get("success"):
            passed_tests.append((test_name, result))
        else:
            failed_tests.append((test_name, result))
    
    # Show passed tests
    if passed_tests:
        print("\n  PASSED:")
        for test_name, result in passed_tests:
            reason_parts = []
            if "status_code" in result:
                reason_parts.append(f"status={result['status_code']}")
            if result.get('correctly_denied'):
                reason_parts.append("correctly denied")
            if result.get('matches_expected'):
                reason_parts.append(f"field={result.get('data_field')}")
            if result.get('limit_accepted'):
                reason_parts.append("limit accepted")
            reason = ", ".join(reason_parts) if reason_parts else "passed"
            print(f"    ✓ {test_name:30s} ({reason})")
    
    # Show failed tests
    if failed_tests:
        print("\n  FAILED:")
        for test_name, result in failed_tests:
            reason_parts = []
            if result.get('reason') == 'no_token':
                reason_parts.append("failed to get token")
            if "status_code" in result:
                status = result['status_code']
                reason_parts.append(f"status={status}")
                if status == 200 and not result.get('success'):
                    reason_parts.append("should have been denied")
                elif status not in [200]:
                    reason_parts.append(f"unexpected, should be 200")
            if "data_field" in result and "expected" in result:
                reason_parts.append(f"got {result['data_field']}, expected {result['expected']}")
            reason = ", ".join(reason_parts) if reason_parts else "unknown failure"
            print(f"    ✗ {test_name:30s} ({reason})")
    
    return {"role": "ADMIN", "passed": passed, "total": total, "results": results}

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_role_test(role: str) -> Dict[str, Any]:
    """
    Run comprehensive test suite for a specific role
    
    Args:
        role: Role name (PUBLIC, BASIC, PREMIUM, ADMIN)
        
    Returns:
        Dict with test results
    """
    role_upper = role.upper()
    
    if role_upper == "PUBLIC":
        return test_public_role()
    elif role_upper == "BASIC":
        return test_basic_role()
    elif role_upper == "PREMIUM":
        return test_premium_role()
    elif role_upper == "ADMIN":
        return test_admin_role()
    else:
        print(f"✗ Unknown role: {role}")
        print(f"Available roles: PUBLIC, BASIC, PREMIUM, ADMIN")
        return {"success": False, "error": "unknown_role"}

def run_all_role_tests() -> Dict[str, Any]:
    """
    Run comprehensive test suites for all roles
    
    Returns:
        Dict with all test results
    """
    print("\n" + "▓"*70)
    print("▓" + " "*68 + "▓")
    print("▓" + "  COMPREHENSIVE ROLE-BASED ACCESS CONTROL TESTS".center(68) + "▓")
    print("▓" + " "*68 + "▓")
    print("▓"*70)
    
    all_results = {}
    
    # Test each role
    all_results["PUBLIC"] = test_public_role()
    all_results["BASIC"] = test_basic_role()
    all_results["PREMIUM"] = test_premium_role()
    all_results["ADMIN"] = test_admin_role()
    
    # Grand summary
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  GRAND SUMMARY - ALL ROLES".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    total_passed = 0
    total_tests = 0
    all_passed_tests = []
    all_failed_tests = []
    
    for role, result in all_results.items():
        passed = result.get("passed", 0)
        total = result.get("total", 0)
        total_passed += passed
        total_tests += total
        
        percentage = (passed / total * 100) if total > 0 else 0
        status = "✓" if passed == total else "⚠"
        
        print(f"\n{status} {role}: {passed}/{total} tests passed ({percentage:.1f}%)")
        
        # Collect passed and failed tests
        for test_name, test_result in result.get("results", []):
            if test_result.get("success"):
                all_passed_tests.append({
                    "role": role,
                    "test": test_name,
                    "result": test_result
                })
            else:
                all_failed_tests.append({
                    "role": role,
                    "test": test_name,
                    "result": test_result
                })
    
    overall_percentage = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print("\n" + "="*70)
    print(f"OVERALL: {total_passed}/{total_tests} tests passed ({overall_percentage:.1f}%)")
    print("="*70)
    
    # Detailed breakdown - Passed tests
    if all_passed_tests:
        print("\n" + "="*70)
        print(" PASSED TESTS SUMMARY")
        print("="*70)
        for item in all_passed_tests:
            role = item["role"]
            test = item["test"]
            result = item["result"]
            
            # Build reason string
            reason_parts = []
            if "status_code" in result:
                reason_parts.append(f"status={result['status_code']}")
            if "correctly_denied" in result and result["correctly_denied"]:
                reason_parts.append("correctly denied")
            if "data_field" in result:
                reason_parts.append(f"field={result['data_field']}")
            if "resultcount" in result:
                reason_parts.append(f"results={result['resultcount']}")
            if "matches_expected" in result and result["matches_expected"]:
                reason_parts.append("matches expected")
            if "limit_accepted" in result and result["limit_accepted"]:
                reason_parts.append("limit accepted")
            
            reason = ", ".join(reason_parts) if reason_parts else "passed"
            print(f"  ✓ {role:8s} - {test:30s} ({reason})")
    
    # Detailed breakdown - Failed tests
    if all_failed_tests:
        print("\n" + "="*70)
        print(" FAILED TESTS SUMMARY")
        print("="*70)
        for item in all_failed_tests:
            role = item["role"]
            test = item["test"]
            result = item["result"]
            
            # Build detailed failure reason
            reason_parts = []
            
            # Check for missing token
            if result.get("reason") == "no_token":
                reason_parts.append("FAILED TO GET TOKEN")
            
            # Check for wrong status code
            if "status_code" in result:
                status = result["status_code"]
                reason_parts.append(f"status={status}")
                
                # Try to explain what went wrong
                if status == 401:
                    reason_parts.append("(unauthorized - token issue)")
                elif status == 403:
                    reason_parts.append("(forbidden - role insufficient)")
                elif status == 200 and not result.get("success"):
                    reason_parts.append("(succeeded when should have failed)")
                elif status not in [200, 401, 403]:
                    reason_parts.append("(unexpected status)")
            
            # Check for field mismatches
            if "data_field" in result and "expected" in result:
                actual = result["data_field"]
                expected = result["expected"]
                reason_parts.append(f"got {actual}, expected {expected}")
            
            # Check if it should have been denied
            if not result.get("correctly_denied") and "correctly_denied" in result:
                reason_parts.append("should have been denied but wasn't")
            
            reason = ", ".join(reason_parts) if reason_parts else "unknown failure"
            print(f"  ✗ {role:8s} - {test:30s} ({reason})")
    
    # Summary statistics
    print("\n" + "="*70)
    print(" STATISTICS")
    print("="*70)
    print(f"  Total Tests Run:    {total_tests}")
    print(f"  Passed:             {total_passed} ({overall_percentage:.1f}%)")
    print(f"  Failed:             {len(all_failed_tests)} ({100-overall_percentage:.1f}%)")
    
    # Role-specific breakdown
    print("\n  Breakdown by Role:")
    for role, result in all_results.items():
        passed = result.get("passed", 0)
        total = result.get("total", 0)
        failed = total - passed
        print(f"    {role:8s}: {passed} passed, {failed} failed out of {total} total")
    
    print("\n" + "="*70 + "\n")
    
    # Generate markdown report
    report_filename = generate_markdown_report(all_results, all_passed_tests, all_failed_tests, total_passed, total_tests)
    print(f"📄 Detailed report saved to: {report_filename}")
    print(f"   View it at: computer:///{report_filename}\n")
    
    return all_results

if __name__ == "__main__":
    print("Import this module and use run_role_test() to test individual roles")
    print("Example: from test_roles import run_role_test, run_all_role_tests")
    print("         run_role_test('BASIC')")
    print("         run_all_role_tests()")
