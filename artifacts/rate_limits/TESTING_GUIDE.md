# Rate Limit Testing Guide 🧪

Complete test suite for validating FastAPI rate limiting with SlowAPI.

## 📋 Test Scripts Overview

| Script | Purpose | Difficulty | Speed |
|--------|---------|------------|-------|
| `quick_test.py` | ⚡ Fastest way to verify rate limits work | Easiest | Very Fast |
| `visual_test.py` | 📊 Live dashboard with progress bars | Easy | Fast |
| `test_rate_limits.py` | 🔬 Comprehensive sequential tests | Medium | Moderate |
| `test_concurrent.py` | 🚀 Async concurrent/stress testing | Advanced | Very Fast |

## 🚀 Quick Start

### 1. Start the FastAPI Server

```bash
# Terminal 1 - Start the server
python fastapi_rate_limiting_example.py
```

### 2. Run Tests

```bash
# Terminal 2 - Choose your test script

# Simplest - just hammer the endpoint
python quick_test.py

# Visual dashboard with live updates
python visual_test.py

# Comprehensive test suite
python test_rate_limits.py

# Async concurrent testing
python test_concurrent.py
```

## 📝 Detailed Test Script Guide

### 1. `quick_test.py` - Super Simple Testing

**Best for:** Quick verification that rate limiting is working

```bash
# Run all tests (auto mode)
python quick_test.py

# Super simple mode (just 20 requests to root)
python quick_test.py --simple
```

**What it does:**
- Sends requests as fast as possible
- Shows immediate results (✅ success, ❌ limited)
- Tests multiple endpoints
- Perfect for debugging

**Example Output:**
```
✅ #1  | SUCCESS | Remaining: 9/10
✅ #2  | SUCCESS | Remaining: 8/10
...
✅ #10 | SUCCESS | Remaining: 0/10
❌ #11 | RATE LIMITED! | Remaining: 0/10
```

---

### 2. `visual_test.py` - Live Dashboard

**Best for:** Watching rate limits in action with visual feedback

```bash
# Run visual dashboard
python visual_test.py

# Stress test mode
python visual_test.py --stress
```

**What it does:**
- Live progress bars
- Real-time rate limit status
- Color-coded displays (green/yellow/red)
- Tests multiple endpoints sequentially

**Example Output:**
```
✅ [████████████████░░░░░░] 70% | Rate Limit: [████░░░░░] 4/10 | ✅ 7 ❌ 3 | 5.2 req/s
```

**Features:**
- 🟢 Green: Plenty of requests remaining
- 🟡 Yellow: Running low on requests
- 🔴 Red: Rate limit about to hit

---

### 3. `test_rate_limits.py` - Comprehensive Testing

**Best for:** Thorough testing of all features

```bash
python test_rate_limits.py
```

**What it tests:**
1. ✅ Basic rate limits (10/minute)
2. ✅ Strict rate limits (3/minute)
3. ✅ Multiple rate limits (10/sec, 50/min, 200/hour)
4. ✅ User-based rate limiting (separate buckets per user)
5. ✅ POST endpoint limiting
6. ✅ Shared limits across endpoints
7. ✅ Burst traffic handling
8. ✅ Recovery after rate limit (optional 65-second test)

**Test Scenarios:**

#### Test 1: Basic Rate Limit
```python
# Endpoint: / (10/minute limit)
# Sends: 15 requests
# Expected: First 10 succeed, last 5 get 429 errors
```

#### Test 4: User-Based Limiting
```python
# Tests that different users have separate rate limit buckets
# User 'alice' gets 10 requests
# User 'bob' also gets 10 requests (separate bucket)
```

#### Test 7: Burst Traffic
```python
# Sends 20 requests with NO delay
# Tests ability to handle sudden burst
# Shows requests/second achieved
```

---

### 4. `test_concurrent.py` - Async Stress Testing

**Best for:** Testing under realistic concurrent load

```bash
python test_concurrent.py
```

**What it tests:**
- High concurrency scenarios
- Multiple simultaneous users
- Sustained load patterns
- Realistic traffic simulation
- Extreme stress testing (100+ concurrent)

**Test Scenarios:**

#### Test 1: Concurrent Load
```python
# 30 requests, 15 concurrent connections
# Tests how rate limiter handles many simultaneous requests
```

#### Test 3: Burst Attack Simulation
```python
# 50 requests ALL AT ONCE
# Maximum concurrency stress test
# Shows how system handles attacks
```

#### Test 5: Multiple Users Concurrent
```python
# 4 users (alice, bob, charlie, david)
# Each sends 10 concurrent requests
# Verifies separate rate limit buckets work under concurrency
```

#### Test 7: Realistic Traffic Pattern
```python
# Simulates real-world traffic:
#   - Low traffic: 5 requests, 2 concurrent
#   - Medium: 15 requests, 5 concurrent
#   - High: 30 requests, 15 concurrent
#   - Cooling down: 20 requests, 10 concurrent
```

---

## 🎯 Testing Specific Features

### Test User-Based Rate Limiting

```bash
# Quick test
curl -H "X-User-ID: alice" http://localhost:8000/user-based
curl -H "X-User-ID: bob" http://localhost:8000/user-based

# Comprehensive test
python test_rate_limits.py  # Will run Test 4
```

### Test POST Endpoints

```bash
# Manual test
for i in {1..8}; do
  curl -X POST http://localhost:8000/api/data \
    -H "Content-Type: application/json" \
    -d '{"name":"test","value":123}'
done

# Automated test
python test_rate_limits.py  # Will run Test 5
```

### Test Shared Limits

```bash
# These share the same 10/minute bucket
curl http://localhost:8000/shared/endpoint1
curl http://localhost:8000/shared/endpoint2

# Automated test
python test_rate_limits.py  # Will run Test 6
```

### Test Different Rate Limit Tiers

```bash
# Advanced example with API keys
curl -H "X-API-Key: pre_test123" http://localhost:8000/api/premium
curl -H "X-User-Tier: enterprise" http://localhost:8000/api/dynamic
```

---

## 📊 Understanding Test Results

### Success Indicators

✅ **Rate limiting is working if:**
- Early requests succeed (200 OK)
- Later requests fail (429 Too Many Requests)
- `X-RateLimit-Remaining` header decreases
- Error message explains the limit

### Example Good Output

```
Request #1: ✅ OK (Remaining: 9)
Request #2: ✅ OK (Remaining: 8)
...
Request #10: ✅ OK (Remaining: 0)
Request #11: ❌ LIMITED (Remaining: 0)
        Error: {'error': 'Rate limit exceeded: 10 per 1 minute'}
```

### Warning Signs

⚠️ **Check configuration if:**
- All requests succeed (no 429 errors)
- No rate limit headers in response
- Limits never trigger even with many requests
- Server errors (500) instead of 429

---

## 🔧 Troubleshooting

### Server Not Responding

```bash
# Check if server is running
curl http://localhost:8000/

# If not, start it:
python fastapi_rate_limiting_example.py
```

### Tests Pass But Rate Limits Never Hit

**Problem:** Rate limit is set too high

**Solution:** Test stricter endpoint
```bash
python quick_test.py  # Will test /strict endpoint (3/minute)
```

### Rate Limits Reset Too Fast

**Problem:** Using in-memory storage with server restarts

**Solution:** Use Redis backend
```bash
# Start Redis
docker run -d -p 6379:6379 redis:alpine

# Use advanced example
python advanced_rate_limiting.py
```

### Inconsistent Results with Concurrent Tests

**Problem:** Normal behavior with in-memory storage

**Solution:** Expected for development. Use Redis for consistency.

---

## 🎪 Fun Testing Ideas

### 1. Race Condition Test
```bash
# Open multiple terminals and run simultaneously:
# Terminal 1, 2, 3:
python quick_test.py --simple
```

### 2. Distributed User Test
```bash
# Simulate users from different IPs (would need proxy)
# Or just use different user IDs:
for user in alice bob charlie david; do
  for i in {1..15}; do
    curl -H "X-User-ID: $user" http://localhost:8000/user-based
  done
done
```

### 3. Sustained Load Test
```bash
# Keep hitting for 5 minutes
for i in {1..300}; do
  curl http://localhost:8000/
  sleep 1
done
```

### 4. Watch Rate Limit Recovery
```bash
# Hit limit
for i in {1..15}; do curl http://localhost:8000/strict; done

# Wait and watch it recover
for i in {1..120}; do
  echo "Second $i:"
  curl -s http://localhost:8000/strict | grep -o "error\|message"
  sleep 1
done
```

---

## 📈 Performance Expectations

### Typical Results (Local Development)

| Test Type | Requests/Second | Expected Behavior |
|-----------|----------------|-------------------|
| Sequential | 5-10 req/s | Controlled, predictable |
| Concurrent (10) | 20-50 req/s | Fast but manageable |
| Concurrent (50) | 50-200 req/s | Stress test level |
| Burst (no limit) | 200-500 req/s | Maximum speed |

### Rate Limit Hit Expectations

| Endpoint | Limit | Requests to Hit | Time to Hit |
|----------|-------|----------------|-------------|
| `/` | 10/minute | 11 | < 5 seconds |
| `/strict` | 3/minute | 4 | < 2 seconds |
| `/multiple-limits` | 10/second | 11 | < 1 second |
| `/generous` | 100/minute | 101 | ~10 seconds |

---

## 🚀 Advanced Testing

### Load Testing with Apache Bench

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Test with 100 requests, 10 concurrent
ab -n 100 -c 10 http://localhost:8000/

# Look for 429 status codes in results
```

### Load Testing with wrk

```bash
# Install wrk
sudo apt-get install wrk

# Run for 30 seconds with 10 threads, 100 connections
wrk -t10 -c100 -d30s http://localhost:8000/

# Check for non-2xx responses
```

### Custom Python Script

```python
import requests
import time

url = "http://localhost:8000/"
results = {"success": 0, "limited": 0}

for i in range(100):
    r = requests.get(url)
    if r.status_code == 200:
        results["success"] += 1
    elif r.status_code == 429:
        results["limited"] += 1
    time.sleep(0.1)

print(f"Success: {results['success']}, Limited: {results['limited']}")
```

---

## 📚 Next Steps

1. ✅ Run `quick_test.py` to verify basic functionality
2. ✅ Run `visual_test.py` to see rate limits in action
3. ✅ Run `test_rate_limits.py` for comprehensive testing
4. ✅ Run `test_concurrent.py` for stress testing
5. ✅ Experiment with Redis backend (`advanced_rate_limiting.py`)
6. ✅ Try custom rate limit configurations
7. ✅ Deploy and test in production-like environment

---

## 🎓 Learning Goals

After running these tests, you should understand:

- ✅ How rate limiting prevents API abuse
- ✅ When requests start getting limited
- ✅ How rate limit headers work
- ✅ Difference between per-IP and per-user limiting
- ✅ How shared limits work across endpoints
- ✅ Why Redis is needed for production
- ✅ How to handle concurrent requests
- ✅ Best practices for API rate limiting

---

## 🆘 Need Help?

**Tests not working?**
1. Ensure server is running on port 8000
2. Check `requirements.txt` dependencies installed
3. Try `quick_test.py --simple` first
4. Check server logs for errors

**Want to modify tests?**
- All test scripts are heavily commented
- Easy to adjust `num_requests` and `delay` parameters
- Add your own endpoints to test

**Questions about rate limiting?**
- Check the main README.md
- Review FastAPI examples
- Read SlowAPI documentation

Good luck testing! 🚀
