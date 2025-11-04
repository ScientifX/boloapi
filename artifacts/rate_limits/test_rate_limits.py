"""
Simple Rate Limit Testing Script

This script rapidly calls endpoints to trigger rate limits and verify they work correctly.
Uses synchronous requests for simplicity.
"""

import requests
import time
from typing import Dict, List
from datetime import datetime


BASE_URL = "http://localhost:8000"


def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f" {text}")
    print("=" * 70)


def print_response(response: requests.Response, request_num: int):
    """Print response details in a formatted way"""
    status_color = "✅" if response.status_code == 200 else "❌"
    
    print(f"\n{status_color} Request #{request_num}")
    print(f"   Status: {response.status_code}")
    print(f"   Limit: {response.headers.get('X-RateLimit-Limit', 'N/A')}")
    print(f"   Remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}")
    print(f"   Reset: {response.headers.get('X-RateLimit-Reset', 'N/A')}")
    
    if response.status_code == 429:
        print(f"   ⚠️  RATE LIMITED!")
        try:
            print(f"   Error: {response.json()}")
        except:
            print(f"   Error: {response.text}")


def test_endpoint(url: str, num_requests: int = 15, delay: float = 0.1, 
                 headers: Dict = None, method: str = "GET", json_data: Dict = None):
    """
    Test an endpoint by sending multiple requests rapidly
    
    Args:
        url: Full URL to test
        num_requests: Number of requests to send
        delay: Delay between requests in seconds
        headers: Optional headers to send
        method: HTTP method (GET, POST, etc.)
        json_data: JSON data for POST requests
    """
    print(f"\n🎯 Testing: {url}")
    print(f"   Sending {num_requests} requests with {delay}s delay...")
    
    success_count = 0
    rate_limited_count = 0
    error_count = 0
    
    start_time = time.time()
    
    for i in range(1, num_requests + 1):
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=5)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=5)
            else:
                print(f"❌ Unsupported method: {method}")
                return
            
            print_response(response, i)
            
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1
            else:
                error_count += 1
            
            time.sleep(delay)
            
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Request #{i} failed: {e}")
            error_count += 1
    
    elapsed_time = time.time() - start_time
    
    print(f"\n📊 Summary:")
    print(f"   Total Requests: {num_requests}")
    print(f"   Successful: {success_count}")
    print(f"   Rate Limited: {rate_limited_count}")
    print(f"   Errors: {error_count}")
    print(f"   Time Elapsed: {elapsed_time:.2f}s")
    print(f"   Avg Request Time: {elapsed_time/num_requests:.2f}s")


def test_basic_rate_limit():
    """Test basic rate limit endpoint (10/minute)"""
    print_header("TEST 1: Basic Rate Limit (10/minute)")
    test_endpoint(f"{BASE_URL}/", num_requests=15, delay=0.1)


def test_strict_rate_limit():
    """Test strict rate limit endpoint (3/minute)"""
    print_header("TEST 2: Strict Rate Limit (3/minute)")
    test_endpoint(f"{BASE_URL}/strict", num_requests=8, delay=0.1)


def test_multiple_limits():
    """Test endpoint with multiple rate limits"""
    print_header("TEST 3: Multiple Limits (10/second, 50/minute)")
    print("\n🔹 Phase 1: Test per-second limit (rapid fire)")
    test_endpoint(f"{BASE_URL}/multiple-limits", num_requests=15, delay=0.05)
    
    print("\n⏳ Waiting 2 seconds before phase 2...")
    time.sleep(2)
    
    print("\n🔹 Phase 2: Test per-minute limit (slower)")
    test_endpoint(f"{BASE_URL}/multiple-limits", num_requests=10, delay=0.5)


def test_user_based_limit():
    """Test user-based rate limiting"""
    print_header("TEST 4: User-Based Rate Limiting")
    
    print("\n🔹 Testing as User 'alice':")
    headers_alice = {"X-User-ID": "alice"}
    test_endpoint(f"{BASE_URL}/user-based", num_requests=12, delay=0.1, headers=headers_alice)
    
    print("\n🔹 Testing as User 'bob' (should have separate limit):")
    headers_bob = {"X-User-ID": "bob"}
    test_endpoint(f"{BASE_URL}/user-based", num_requests=12, delay=0.1, headers=headers_bob)


def test_post_endpoint():
    """Test POST endpoint with rate limiting"""
    print_header("TEST 5: POST Endpoint (5/minute)")
    
    json_data = {"name": "test", "value": 123}
    test_endpoint(
        f"{BASE_URL}/api/data", 
        num_requests=8, 
        delay=0.1, 
        method="POST",
        json_data=json_data
    )


def test_shared_limits():
    """Test shared rate limits across endpoints"""
    print_header("TEST 6: Shared Rate Limits")
    
    print("\n🔹 Testing endpoint1 (uses shared limit):")
    for i in range(1, 6):
        response = requests.get(f"{BASE_URL}/shared/endpoint1")
        print_response(response, i)
        time.sleep(0.1)
    
    print("\n🔹 Testing endpoint2 (shares same limit bucket):")
    for i in range(6, 13):
        response = requests.get(f"{BASE_URL}/shared/endpoint2")
        print_response(response, i)
        time.sleep(0.1)
    
    print("\n💡 Note: Both endpoints share the same 10/minute limit")


def test_burst_traffic():
    """Simulate burst traffic"""
    print_header("TEST 7: Burst Traffic Simulation")
    
    print("\n🔹 Sending 20 requests as fast as possible (no delay):")
    
    start_time = time.time()
    responses = []
    
    for i in range(1, 21):
        try:
            response = requests.get(f"{BASE_URL}/")
            responses.append(response)
            
            status_icon = "✅" if response.status_code == 200 else "❌"
            remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
            print(f"{status_icon} Request #{i}: Status {response.status_code}, Remaining: {remaining}")
            
        except Exception as e:
            print(f"❌ Request #{i} failed: {e}")
    
    elapsed = time.time() - start_time
    successful = sum(1 for r in responses if r.status_code == 200)
    rate_limited = sum(1 for r in responses if r.status_code == 429)
    
    print(f"\n📊 Burst Summary:")
    print(f"   Total Requests: 20")
    print(f"   Successful: {successful}")
    print(f"   Rate Limited: {rate_limited}")
    print(f"   Time Elapsed: {elapsed:.2f}s")
    print(f"   Requests/Second: {20/elapsed:.2f}")


def test_recovery_after_limit():
    """Test that limits reset properly"""
    print_header("TEST 8: Recovery After Rate Limit")
    
    print("\n🔹 Phase 1: Trigger rate limit")
    test_endpoint(f"{BASE_URL}/strict", num_requests=5, delay=0.1)
    
    print("\n⏳ Waiting 65 seconds for rate limit to reset...")
    print("   (Strict endpoint has 3/minute limit)")
    
    for remaining in range(65, 0, -5):
        print(f"   ⏱️  {remaining} seconds remaining...", end="\r")
        time.sleep(5)
    
    print("\n\n🔹 Phase 2: Test after reset (should work again)")
    test_endpoint(f"{BASE_URL}/strict", num_requests=4, delay=0.1)


def run_all_tests():
    """Run all rate limit tests"""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "RATE LIMIT TEST SUITE" + " " * 32 + "║")
    print("╚" + "═" * 68 + "╝")
    
    print("\n⚠️  Make sure the FastAPI server is running on http://localhost:8000")
    print("   Start it with: python fastapi_rate_limiting_example.py\n")
    
    input("Press Enter to start tests...")
    
    try:
        # Quick connectivity test
        print("\n🔍 Checking server connectivity...")
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"✅ Server is responding (Status: {response.status_code})")
        
        # Run all tests
        test_basic_rate_limit()
        test_strict_rate_limit()
        test_multiple_limits()
        test_user_based_limit()
        test_post_endpoint()
        test_shared_limits()
        test_burst_traffic()
        
        # Optional: test recovery (takes 65 seconds)
        print("\n" + "=" * 70)
        response = input("\n⏱️  Run recovery test? (takes 65 seconds) [y/N]: ")
        if response.lower() == 'y':
            test_recovery_after_limit()
        
        print_header("🎉 ALL TESTS COMPLETED")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to server at http://localhost:8000")
        print("   Make sure the FastAPI server is running!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    run_all_tests()
