"""
Visual Rate Limit Testing Dashboard

This script creates a live visual display of rate limit testing with progress bars
and real-time status updates.
"""

import requests
import time
import sys
from datetime import datetime
from typing import Dict, List


BASE_URL = "http://localhost:8005"


def clear_line():
    """Clear the current line"""
    sys.stdout.write('\r')
    sys.stdout.write(' ' * 100)
    sys.stdout.write('\r')
    sys.stdout.flush()


def progress_bar(current: int, total: int, width: int = 40) -> str:
    """Create a progress bar string"""
    filled = int(width * current / total)
    bar = '█' * filled + '░' * (width - filled)
    percent = current / total * 100
    return f"[{bar}] {percent:.0f}%"


def rate_limit_bar(remaining: int, limit: int, width: int = 30) -> str:
    """Create a rate limit status bar"""
    if limit == 0:
        return "?" * width
    
    filled = int(width * remaining / limit)
    
    # Color coding (using ANSI if terminal supports it)
    if remaining / limit > 0.5:
        color = '\033[92m'  # Green
    elif remaining / limit > 0.2:
        color = '\033[93m'  # Yellow
    else:
        color = '\033[91m'  # Red
    
    reset = '\033[0m'
    
    bar = '█' * filled + '░' * (width - filled)
    return f"{color}[{bar}]{reset} {remaining}/{limit}"


def visual_test(endpoint: str, endpoint_name: str, num_requests: int = 20, delay: float = 0.2):
    """
    Visual test with live progress and rate limit display
    """
    url = f"{BASE_URL}{endpoint}"
    
    print("\n" + "=" * 80)
    print(f"🎯 Testing: {endpoint_name}")
    print(f"   Endpoint: {endpoint}")
    print(f"   Requests: {num_requests}")
    print("=" * 80 + "\n")
    
    results = {
        'success': 0,
        'limited': 0,
        'error': 0
    }
    
    start_time = time.time()
    
    for i in range(1, num_requests + 1):
        try:
            response = requests.get(url, timeout=5)
            
            # Get rate limit info
            limit = response.headers.get('X-RateLimit-Limit', 'N/A')
            remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
            
            # Update results
            if response.status_code == 200:
                results['success'] += 1
                status = '✅'
            elif response.status_code == 429:
                results['limited'] += 1
                status = '❌'
            else:
                results['error'] += 1
                status = '⚠️'
            
            # Calculate stats
            elapsed = time.time() - start_time
            req_per_sec = i / elapsed if elapsed > 0 else 0
            
            # Print live status
            clear_line()
            
            # Progress
            prog = progress_bar(i, num_requests, width=30)
            
            # Rate limit status
            try:
                limit_int = int(limit) if limit != 'N/A' else 0
                remaining_int = int(remaining) if remaining != 'N/A' else 0
                rate_bar = rate_limit_bar(remaining_int, limit_int, width=20)
            except:
                rate_bar = "N/A"
            
            # Build status line
            status_line = (
                f"{status} {prog} | "
                f"Rate Limit: {rate_bar} | "
                f"✅ {results['success']} ❌ {results['limited']} | "
                f"{req_per_sec:.1f} req/s"
            )
            
            sys.stdout.write(status_line)
            sys.stdout.flush()
            
            time.sleep(delay)
            
        except Exception as e:
            results['error'] += 1
            clear_line()
            print(f"💥 Request {i} failed: {e}")
    
    # Final summary
    elapsed = time.time() - start_time
    print("\n")
    print("─" * 80)
    print("📊 Final Results:")
    print(f"   ✅ Successful:       {results['success']:3d} ({results['success']/num_requests*100:5.1f}%)")
    print(f"   ❌ Rate Limited:     {results['limited']:3d} ({results['limited']/num_requests*100:5.1f}%)")
    print(f"   ⚠️  Errors:           {results['error']:3d} ({results['error']/num_requests*100:5.1f}%)")
    print(f"   ⏱️  Time:             {elapsed:.2f}s")
    print(f"   📈 Avg Speed:        {num_requests/elapsed:.2f} req/s")
    print("─" * 80)
    
    return results


def live_dashboard():
    """
    Interactive dashboard showing multiple endpoints being tested
    """
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "LIVE RATE LIMIT TESTING DASHBOARD" + " " * 25 + "║")
    print("╚" + "═" * 78 + "╝")
    
    # Check server
    try:
        response = requests.get(BASE_URL, timeout=2)
        print(f"\n✅ Server is online at {BASE_URL}\n")
    except:
        print(f"\n❌ Server is offline at {BASE_URL}")
        print("   Start with: python fastapi_rate_limiting_example.py\n")
        return
    
    # Test suite
    tests = [
        ("/", "Root Endpoint (10/minute)", 15, 0.2),
        ("/strict", "Strict Endpoint (3/minute)", 8, 0.2),
        ("/multiple-limits", "Multi-Limit Endpoint (10/sec, 50/min)", 25, 0.15),
        ("/generous", "Generous Endpoint (100/minute)", 30, 0.1),
    ]
    
    all_results = []
    
    for endpoint, name, num_requests, delay in tests:
        result = visual_test(endpoint, name, num_requests, delay)
        all_results.append((name, result))
        
        # Pause between tests
        if endpoint != tests[-1][0]:
            print("\n⏳ Cooling down for 3 seconds...\n")
            for i in range(3, 0, -1):
                sys.stdout.write(f'\r   {i}...')
                sys.stdout.flush()
                time.sleep(1)
            print("\r" + " " * 20 + "\r")
    
    # Overall summary
    print("\n" + "=" * 80)
    print("🏆 OVERALL SUMMARY")
    print("=" * 80)
    
    for name, result in all_results:
        total = result['success'] + result['limited'] + result['error']
        limited_pct = result['limited'] / total * 100 if total > 0 else 0
        
        # Status indicator
        if result['limited'] > 0:
            status = "✅ Working"
        else:
            status = "⚠️  No limits hit"
        
        print(f"\n{status} | {name}")
        print(f"   Success: {result['success']:3d} | Limited: {result['limited']:3d} ({limited_pct:.0f}%)")
    
    print("\n" + "=" * 80)
    print("🎉 All tests complete!")
    print("=" * 80 + "\n")


def stress_test_visual():
    """Visual stress test - rapid fire requests"""
    print("\n" + "⚡" * 40)
    print(" STRESS TEST - RAPID FIRE MODE")
    print("⚡" * 40 + "\n")
    
    url = f"{BASE_URL}/"
    num_requests = 50
    
    print(f"Sending {num_requests} requests as fast as possible...\n")
    
    success = 0
    limited = 0
    start = time.time()
    
    for i in range(1, num_requests + 1):
        response = requests.get(url)
        
        if response.status_code == 200:
            success += 1
            icon = "✅"
        elif response.status_code == 429:
            limited += 1
            icon = "❌"
        else:
            icon = "⚠️"
        
        remaining = response.headers.get('X-RateLimit-Remaining', '?')
        
        # Live display every 5 requests
        if i % 5 == 0:
            elapsed = time.time() - start
            speed = i / elapsed
            
            clear_line()
            status = (
                f"{progress_bar(i, num_requests, 25)} | "
                f"✅ {success} ❌ {limited} | "
                f"Remaining: {remaining} | "
                f"{speed:.1f} req/s"
            )
            sys.stdout.write(status)
            sys.stdout.flush()
    
    elapsed = time.time() - start
    
    print("\n\n" + "─" * 80)
    print(f"📊 Stress Test Results:")
    print(f"   Total Requests:    {num_requests}")
    print(f"   ✅ Successful:     {success} ({success/num_requests*100:.1f}%)")
    print(f"   ❌ Rate Limited:   {limited} ({limited/num_requests*100:.1f}%)")
    print(f"   ⏱️  Total Time:     {elapsed:.3f}s")
    print(f"   ⚡ Speed:          {num_requests/elapsed:.1f} req/s")
    print("─" * 80 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--stress":
        stress_test_visual()
    else:
        live_dashboard()
