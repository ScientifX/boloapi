"""
Async Concurrent Rate Limit Testing

This script uses asyncio and aiohttp to send many concurrent requests
to aggressively test rate limiting under high load.
"""

import asyncio
import aiohttp
import time
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime


BASE_URL = "http://localhost:8000"


@dataclass
class RequestResult:
    """Store result of a single request"""
    request_num: int
    status_code: int
    timestamp: float
    rate_limit_remaining: str
    rate_limit_limit: str
    error: str = None


def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f" {text}")
    print("=" * 80)


def print_summary(results: List[RequestResult], start_time: float):
    """Print summary of test results"""
    elapsed = time.time() - start_time
    total = len(results)
    successful = sum(1 for r in results if r.status_code == 200)
    rate_limited = sum(1 for r in results if r.status_code == 429)
    errors = sum(1 for r in results if r.error)
    
    print(f"\n{'='*80}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*80}")
    print(f"Total Requests:      {total}")
    print(f"✅ Successful:       {successful} ({successful/total*100:.1f}%)")
    print(f"❌ Rate Limited:     {rate_limited} ({rate_limited/total*100:.1f}%)")
    print(f"⚠️  Errors:           {errors}")
    print(f"⏱️  Time Elapsed:     {elapsed:.2f}s")
    print(f"📈 Requests/Second:  {total/elapsed:.2f}")
    print(f"{'='*80}")


async def make_request(
    session: aiohttp.ClientSession,
    url: str,
    request_num: int,
    method: str = "GET",
    headers: Dict = None,
    json_data: Dict = None
) -> RequestResult:
    """Make a single HTTP request and return the result"""
    timestamp = time.time()
    
    try:
        if method.upper() == "GET":
            async with session.get(url, headers=headers) as response:
                status = response.status
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
                rate_limit_limit = response.headers.get('X-RateLimit-Limit', 'N/A')
                
                return RequestResult(
                    request_num=request_num,
                    status_code=status,
                    timestamp=timestamp,
                    rate_limit_remaining=rate_limit_remaining,
                    rate_limit_limit=rate_limit_limit
                )
        elif method.upper() == "POST":
            async with session.post(url, headers=headers, json=json_data) as response:
                status = response.status
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
                rate_limit_limit = response.headers.get('X-RateLimit-Limit', 'N/A')
                
                return RequestResult(
                    request_num=request_num,
                    status_code=status,
                    timestamp=timestamp,
                    rate_limit_remaining=rate_limit_remaining,
                    rate_limit_limit=rate_limit_limit
                )
    except Exception as e:
        return RequestResult(
            request_num=request_num,
            status_code=0,
            timestamp=timestamp,
            rate_limit_remaining='N/A',
            rate_limit_limit='N/A',
            error=str(e)
        )


async def concurrent_test(
    url: str,
    num_requests: int,
    concurrent_limit: int = 10,
    method: str = "GET",
    headers: Dict = None,
    json_data: Dict = None
):
    """
    Send many concurrent requests to test rate limiting
    
    Args:
        url: Endpoint to test
        num_requests: Total number of requests
        concurrent_limit: Max concurrent requests
        method: HTTP method
        headers: Optional headers
        json_data: Optional JSON data for POST
    """
    print(f"\n🚀 Concurrent Test: {url}")
    print(f"   Requests: {num_requests} | Concurrency: {concurrent_limit}")
    
    start_time = time.time()
    results = []
    
    connector = aiohttp.TCPConnector(limit=concurrent_limit)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        for i in range(1, num_requests + 1):
            task = make_request(session, url, i, method, headers, json_data)
            tasks.append(task)
        
        # Execute all requests concurrently
        results = await asyncio.gather(*tasks)
    
    # Print results in real-time style
    print("\n📝 Results:")
    for result in results:
        if result.error:
            print(f"   #{result.request_num:3d}: ⚠️  ERROR - {result.error}")
        elif result.status_code == 200:
            print(f"   #{result.request_num:3d}: ✅ OK      (Remaining: {result.rate_limit_remaining})")
        elif result.status_code == 429:
            print(f"   #{result.request_num:3d}: ❌ LIMITED (Remaining: {result.rate_limit_remaining})")
        else:
            print(f"   #{result.request_num:3d}: ⚠️  Status {result.status_code}")
    
    print_summary(results, start_time)


async def test_basic_endpoint_concurrent():
    """Test basic endpoint with concurrent requests"""
    print_header("TEST 1: Basic Endpoint - Concurrent Load (10/minute limit)")
    await concurrent_test(
        f"{BASE_URL}/",
        num_requests=30,
        concurrent_limit=15
    )


async def test_strict_endpoint_concurrent():
    """Test strict endpoint with concurrent requests"""
    print_header("TEST 2: Strict Endpoint - Concurrent Load (3/minute limit)")
    await concurrent_test(
        f"{BASE_URL}/strict",
        num_requests=15,
        concurrent_limit=10
    )


async def test_burst_attack():
    """Simulate a burst attack with many simultaneous requests"""
    print_header("TEST 3: Burst Attack Simulation")
    await concurrent_test(
        f"{BASE_URL}/multiple-limits",
        num_requests=50,
        concurrent_limit=50  # All at once!
    )


async def test_sustained_load():
    """Test sustained high load"""
    print_header("TEST 4: Sustained High Load")
    
    print("\n🔄 Sending waves of requests...")
    
    for wave in range(1, 4):
        print(f"\n🌊 Wave {wave}/3:")
        await concurrent_test(
            f"{BASE_URL}/",
            num_requests=15,
            concurrent_limit=10
        )
        
        if wave < 3:
            print("\n⏳ Waiting 5 seconds before next wave...")
            await asyncio.sleep(5)


async def test_multiple_users_concurrent():
    """Test rate limiting with multiple users hitting endpoint simultaneously"""
    print_header("TEST 5: Multiple Users - Concurrent Access")
    
    users = ["alice", "bob", "charlie", "david"]
    
    print(f"\n👥 Simulating {len(users)} users, each sending 10 requests concurrently")
    
    async with aiohttp.ClientSession() as session:
        all_tasks = []
        
        for user in users:
            headers = {"X-User-ID": user}
            
            for i in range(1, 11):
                task = make_request(
                    session,
                    f"{BASE_URL}/user-based",
                    i,
                    headers=headers
                )
                all_tasks.append((user, task))
        
        start_time = time.time()
        results = await asyncio.gather(*[task for _, task in all_tasks])
        
        # Group results by user
        print("\n📊 Results by User:")
        for user in users:
            user_results = [r for (u, _), r in zip(all_tasks, results) if u == user]
            successful = sum(1 for r in user_results if r.status_code == 200)
            limited = sum(1 for r in user_results if r.status_code == 429)
            
            print(f"\n   👤 {user}:")
            print(f"      Total: {len(user_results)} | ✅ Success: {successful} | ❌ Limited: {limited}")
        
        print_summary(results, start_time)


async def test_post_endpoint_concurrent():
    """Test POST endpoint with concurrent requests"""
    print_header("TEST 6: POST Endpoint - Concurrent Writes (5/minute limit)")
    
    json_data = {"name": "test", "value": 123}
    
    await concurrent_test(
        f"{BASE_URL}/api/data",
        num_requests=15,
        concurrent_limit=10,
        method="POST",
        json_data=json_data
    )


async def test_realistic_traffic_pattern():
    """Simulate realistic traffic with varying concurrency"""
    print_header("TEST 7: Realistic Traffic Pattern")
    
    print("\n📊 Simulating realistic traffic with varying load:")
    
    patterns = [
        (5, 2, "Low traffic"),
        (15, 5, "Medium traffic"),
        (30, 15, "High traffic"),
        (20, 10, "Cooling down"),
    ]
    
    for num_requests, concurrency, description in patterns:
        print(f"\n🔹 {description}: {num_requests} requests, {concurrency} concurrent")
        await concurrent_test(
            f"{BASE_URL}/",
            num_requests=num_requests,
            concurrent_limit=concurrency
        )
        print("\n⏳ Waiting 3 seconds...")
        await asyncio.sleep(3)


async def stress_test():
    """Aggressive stress test"""
    print_header("TEST 8: STRESS TEST ⚡")
    
    print("\n⚠️  WARNING: This will hammer the endpoint aggressively!")
    print("   Sending 100 requests with 50 concurrent connections")
    
    await asyncio.sleep(2)
    
    await concurrent_test(
        f"{BASE_URL}/",
        num_requests=100,
        concurrent_limit=50
    )


async def run_all_tests():
    """Run all async tests"""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 15 + "ASYNC CONCURRENT TEST SUITE" + " " * 36 + "║")
    print("╚" + "═" * 78 + "╝")
    
    print("\n⚠️  Make sure the FastAPI server is running on http://localhost:8000")
    print("   Start it with: python fastapi_rate_limiting_example.py\n")
    
    # Test connectivity
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/") as response:
                if response.status == 200:
                    print("✅ Server is responding!\n")
                else:
                    print(f"⚠️  Server responded with status {response.status}\n")
    except Exception as e:
        print(f"❌ ERROR: Could not connect to server: {e}")
        print("   Make sure the FastAPI server is running!")
        return
    
    # Run tests
    await test_basic_endpoint_concurrent()
    await asyncio.sleep(2)
    
    await test_strict_endpoint_concurrent()
    await asyncio.sleep(2)
    
    await test_burst_attack()
    await asyncio.sleep(2)
    
    await test_multiple_users_concurrent()
    await asyncio.sleep(2)
    
    await test_post_endpoint_concurrent()
    await asyncio.sleep(2)
    
    await test_sustained_load()
    await asyncio.sleep(2)
    
    await test_realistic_traffic_pattern()
    
    # Optional stress test
    print("\n" + "=" * 80)
    print("\n⚡ Ready for stress test? (not recommended for local development)")
    print("   This will send 100 concurrent requests")
    # Uncomment to enable stress test
    # await stress_test()
    
    print_header("🎉 ALL ASYNC TESTS COMPLETED")


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
