"""
Quick Rate Limit Test - Rapid Fire! 🔥

This is the simplest possible test - just hammers an endpoint as fast as possible
to quickly verify rate limiting works.
"""

import requests
import time
from datetime import datetime


def rapid_fire_test(url: str, num_requests: int = 20):
    """
    Hammer an endpoint as fast as possible to trigger rate limits
    """
    print(f"\n🔥 RAPID FIRE TEST")
    print(f"   Target: {url}")
    print(f"   Requests: {num_requests}")
    print(f"   Strategy: NO DELAY - As fast as possible!")
    print("\n" + "=" * 70)
    
    success_count = 0
    limited_count = 0
    start = time.time()
    
    for i in range(1, num_requests + 1):
        try:
            response = requests.get(url, timeout=5)
            
            # Get rate limit info
            limit = response.headers.get('X-RateLimit-Limit', '?')
            remaining = response.headers.get('X-RateLimit-Remaining', '?')
            
            if response.status_code == 200:
                print(f"✅ #{i:2d} | SUCCESS | Remaining: {remaining}/{limit}")
                success_count += 1
            elif response.status_code == 429:
                print(f"❌ #{i:2d} | RATE LIMITED! | Remaining: {remaining}/{limit}")
                try:
                    error = response.json()
                    print(f"        Error: {error}")
                except:
                    pass
                limited_count += 1
            else:
                print(f"⚠️  #{i:2d} | Status: {response.status_code}")
                
        except Exception as e:
            print(f"💥 #{i:2d} | ERROR: {e}")
    
    elapsed = time.time() - start
    
    print("\n" + "=" * 70)
    print(f"📊 RESULTS:")
    print(f"   ✅ Successful:     {success_count}/{num_requests}")
    print(f"   ❌ Rate Limited:   {limited_count}/{num_requests}")
    print(f"   ⏱️  Total Time:     {elapsed:.3f}s")
    print(f"   📈 Speed:          {num_requests/elapsed:.1f} requests/second")
    
    if limited_count > 0:
        print(f"\n   🎯 SUCCESS! Rate limiting is working!")
        print(f"   First {success_count} requests succeeded, then got limited.")
    else:
        print(f"\n   ⚠️  WARNING! No rate limits hit.")
        print(f"   Either limit is too high or not configured properly.")
    
    print("=" * 70 + "\n")


def test_all_endpoints():
    """Quick test of all main endpoints"""
    base_url = "http://localhost:8005"
    
    print("\n" + "=" * 70)
    print(" QUICK RATE LIMIT TEST SUITE")
    print("=" * 70)
    
    # Check if server is running
    try:
        response = requests.get(base_url, timeout=2)
        print(f"\n✅ Server is running at {base_url}\n")
    except:
        print(f"\n❌ ERROR: Server not running at {base_url}")
        print("   Start the server with: python fastapi_rate_limiting_example.py\n")
        return
    
    # Test different endpoints
    tests = [
        (f"{base_url}/", "Root endpoint (10/minute)", 15),
        (f"{base_url}/strict", "Strict endpoint (3/minute)", 8),
        (f"{base_url}/multiple-limits", "Multiple limits (10/second, 50/minute)", 20),
    ]
    
    for url, description, num_requests in tests:
        print(f"\n{'='*70}")
        print(f"Testing: {description}")
        print(f"{'='*70}")
        rapid_fire_test(url, num_requests)
        
        # Small delay between tests
        if url != tests[-1][0]:
            print("⏳ Waiting 2 seconds before next test...\n")
            time.sleep(2)
    
    print("\n" + "🎉 " * 20)
    print("ALL TESTS COMPLETE!")
    print("🎉 " * 20 + "\n")


def super_simple_test():
    """The absolute simplest test possible"""
    print("\n" + "🔥" * 35)
    print("SUPER SIMPLE TEST - Just hammer the endpoint!")
    print("🔥" * 35 + "\n")
    
    url = "http://localhost:8000/health/"
    
    print("Sending 20 requests as fast as possible...\n")
    
    for i in range(1, 300):
        r = requests.get(url)
        status = "✅ OK" if r.status_code == 200 else f"❌ {r.status_code}"
        remaining = r.headers.get('X-RateLimit-Remaining', '?')
        print(f"Request {i:2d}: {status} (Remaining: {remaining})")
    
    print("\n" + "🔥" * 35 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--simple":
        # Super simple mode
        super_simple_test()
    else:
        # Full test suite
        test_all_endpoints()
