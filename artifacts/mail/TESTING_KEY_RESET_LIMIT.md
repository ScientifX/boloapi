# Testing Key Reset Limit - Usage Guide

## Two Ways to Test

### Method 1: Integrated Test (test_auth_flow.py)
Tests the key reset limit as part of the complete authentication flow.

**Usage:**
```bash
python test_auth_flow.py your-email@example.com
```

**What it does:**
1. Tests registration
2. Tests activation
3. Tests token generation
4. Tests authenticated requests
5. Tests basic key reset (optional)
6. **Tests key reset daily limit (optional)** ← NEW!

**Pros:**
- ✅ Tests everything in one go
- ✅ Good for comprehensive testing
- ✅ Part of regular test suite

**Cons:**
- ⚠️ Optional - easy to skip
- ⚠️ Part of longer test flow

---

### Method 2: Dedicated Test (test_key_reset_limit.py)
Focused test specifically for the daily limit feature.

**Usage:**
```bash
python test_key_reset_limit.py your-email@example.com
```

**What it does:**
1. Checks API is accessible
2. Verifies account exists and is activated
3. Attempts multiple key resets
4. Detects when daily limit is hit
5. Provides detailed analysis

**Pros:**
- ✅ Focused on one feature
- ✅ Detailed reporting
- ✅ Easy to run repeatedly
- ✅ Configurable attempt count

**Cons:**
- ⚠️ Requires existing activated account

---

## Quick Start: Method 2 (Recommended)

### Step 1: Ensure Account Exists
```bash
# Register if needed
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Activate (click email link or use token)
# Then verify it's active with a token request
```

### Step 2: Run the Test
```bash
python test_key_reset_limit.py test@example.com
```

### Step 3: Follow Prompts
```
Enter email address to test: test@example.com
Maximum reset attempts to try (default: 5, max: 20): 5

⚠️  WARNING: This test will:
   1. Reset your API key multiple times
   2. Invalidate previous API keys with each reset
   3. Test the daily limit enforcement

Proceed with test? (yes/no): yes
```

---

## Example Output

### Test with Limit = 1 (Success)
```
======================================================================
  KEY RESET DAILY LIMIT TEST
======================================================================

🔄 Attempt #1
   ✅ Status: 200 OK
   📧 Email sent: true
   🔑 API Key: cmkDp2TtGnXLc7EoeQ...slD5ZbPv

🔄 Attempt #2
   🛑 Status: 429 Too Many Requests
   💬 Message: Daily key reset limit (1) reached. Try again tomorrow.

======================================================================
  🎯 DAILY LIMIT ENFORCEMENT DETECTED!
======================================================================

======================================================================
  TEST SUMMARY
======================================================================

Total Attempts: 2
Successful Resets: 1
Limit Hit: Yes ✅
Limit Hit At: Attempt #2
Daily Limit: 1 reset(s) per day

📋 Successful Resets:
   #1: cmkDp2TtGnXLc7EoeQOauwRJslD... at 2025-01-09T10:30:45

----------------------------------------------------------------------

✅ TEST PASSED: Daily limit enforcement is working!
   The system correctly blocked reset attempt #2
   Daily limit appears to be: 1 reset(s)

💡 Recommendation: Limit is set to 1 (recommended for production)

🎉 Test completed successfully!
```

### Test with No Limit (Warning)
```
======================================================================
  TEST SUMMARY
======================================================================

Total Attempts: 5
Successful Resets: 5
Limit Hit: No ❌

⚠️  TEST INCONCLUSIVE: Did not hit daily limit
   Completed 5 resets without hitting limit

   Possible reasons:
   1. Daily limit is set higher than test attempts
   2. Daily limit feature is not configured
   3. Database columns not added
   4. Environment variable API_MAX_DAILY_KEY_RESETS not set

📝 To configure:
   1. Run migration: migration_key_reset_tracking.sql
   2. Set: API_MAX_DAILY_KEY_RESETS=1
   3. Restart application
```

---

## Configuring the Limit

### Check Current Setting
```bash
# Check if environment variable is set
echo $API_MAX_DAILY_KEY_RESETS

# Or check in .env file
grep API_MAX_DAILY_KEY_RESETS .env
```

### Set the Limit

**In .env file:**
```bash
API_MAX_DAILY_KEY_RESETS=1
```

**In environment:**
```bash
export API_MAX_DAILY_KEY_RESETS=1
```

**Test different limits:**
```bash
# Very strict (production)
API_MAX_DAILY_KEY_RESETS=1

# Moderate
API_MAX_DAILY_KEY_RESETS=2

# Lenient (development)
API_MAX_DAILY_KEY_RESETS=5

# No limit (testing only)
API_MAX_DAILY_KEY_RESETS=999
```

---

## Testing Strategy

### Initial Test (Verify It Works)
```bash
# Set limit to 1
API_MAX_DAILY_KEY_RESETS=1

# Restart app
uvicorn app:app --reload

# Run test
python test_key_reset_limit.py test@example.com

# Expected: Hit limit after 1 successful reset
```

### Test Different Limits
```bash
# Test limit = 2
API_MAX_DAILY_KEY_RESETS=2 uvicorn app:app --reload
python test_key_reset_limit.py test@example.com
# Expected: Hit limit after 2 successful resets

# Test limit = 3
API_MAX_DAILY_KEY_RESETS=3 uvicorn app:app --reload
python test_key_reset_limit.py test@example.com
# Expected: Hit limit after 3 successful resets
```

### Test Daily Reset
```sql
-- Simulate next day (resets counter)
UPDATE tbl_users
SET key_reset_date = CURRENT_DATE - INTERVAL '1 day'
WHERE email = 'test@example.com';

-- Run test again - should allow reset again
python test_key_reset_limit.py test@example.com
```

---

## Troubleshooting

### "Email address not registered"
**Problem:** Account doesn't exist

**Solution:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

---

### "Account not activated"
**Problem:** Account exists but not activated

**Solution:**
1. Check email for activation link
2. Or get token from registration response
3. Click/call activation endpoint

---

### "Cannot connect to API"
**Problem:** API not running

**Solution:**
```bash
uvicorn app:app --reload
```

---

### "Did not hit daily limit"
**Problem:** Limit not configured or set too high

**Solutions:**

1. **Check database columns exist:**
   ```sql
   SELECT column_name 
   FROM information_schema.columns
   WHERE table_name = 'tbl_users'
     AND column_name IN ('key_reset_count', 'key_reset_date');
   ```
   If missing, run: `migration_key_reset_tracking.sql`

2. **Check environment variable:**
   ```bash
   echo $API_MAX_DAILY_KEY_RESETS
   ```
   If not set, add to .env: `API_MAX_DAILY_KEY_RESETS=1`

3. **Restart application:**
   ```bash
   uvicorn app:app --reload
   ```

4. **Run test again:**
   ```bash
   python test_key_reset_limit.py test@example.com
   ```

---

## Advanced Usage

### Custom Attempt Count
```bash
# Test with more attempts
python test_key_reset_limit.py test@example.com
# Enter 10 when prompted for max attempts
```

### Multiple Users
```bash
# Test different users
python test_key_reset_limit.py user1@example.com
python test_key_reset_limit.py user2@example.com

# Each user has independent limit
```

### Automated Testing
```bash
#!/bin/bash
# test_limits.sh

echo "Testing limit = 1"
API_MAX_DAILY_KEY_RESETS=1 uvicorn app:app &
sleep 2
python test_key_reset_limit.py test@example.com
kill %1

echo "Testing limit = 3"
API_MAX_DAILY_KEY_RESETS=3 uvicorn app:app &
sleep 2
python test_key_reset_limit.py test@example.com
kill %1
```

---

## Database Inspection

### Check Current Reset Status
```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date,
    CASE 
        WHEN key_reset_date = CURRENT_DATE THEN 
            'Used ' || key_reset_count || ' resets today'
        ELSE 
            'No resets today'
    END as status
FROM tbl_users
WHERE email = 'test@example.com';
```

### Reset Counter Manually (Testing)
```sql
-- Allow user to reset again today
UPDATE tbl_users
SET key_reset_count = 0,
    key_reset_date = NULL
WHERE email = 'test@example.com';
```

### View All Reset Activity
```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date,
    updated_at
FROM tbl_users
WHERE key_reset_date = CURRENT_DATE
ORDER BY key_reset_count DESC, updated_at DESC;
```

---

## Summary

**Two test methods:**
1. **test_auth_flow.py** - Comprehensive test suite (includes limit test)
2. **test_key_reset_limit.py** - Dedicated limit testing (recommended)

**Quick test:**
```bash
python test_key_reset_limit.py your-email@example.com
```

**Expected result with limit=1:**
- ✅ First reset succeeds
- 🛑 Second reset blocked with 429 error
- ✅ Test passes

**Configuration:**
- Environment variable: `API_MAX_DAILY_KEY_RESETS=1`
- Database columns: `key_reset_count`, `key_reset_date`
- Restart required after changes

---

**Files:**
- [test_key_reset_limit.py](computer:///mnt/user-data/outputs/test_key_reset_limit.py) - Dedicated test
- [test_auth_flow.py](computer:///mnt/user-data/outputs/test_auth_flow.py) - Updated with limit test
- [KEY_RESET_LIMIT_SETUP.md](computer:///mnt/user-data/outputs/KEY_RESET_LIMIT_SETUP.md) - Setup guide

**Happy testing! 🧪**
