# Key Reset Daily Limit - Setup Guide

## Feature: Daily Key Reset Limit

Prevents abuse by limiting how many times a user can reset their API key per day.

---

## Setup Steps

### 1. Run Database Migration

```bash
psql -U your_user -d your_database -f migration_key_reset_tracking.sql
```

Or manually:
```sql
ALTER TABLE tbl_users 
ADD COLUMN IF NOT EXISTS key_reset_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS key_reset_date DATE;

CREATE INDEX IF NOT EXISTS idx_users_key_reset_date 
ON tbl_users(key_reset_date);
```

### 2. Set Environment Variable (Optional)

```bash
# In your .env file or environment
API_MAX_DAILY_KEY_RESETS=1  # Default if not set
```

**Options:**
- `1` - One reset per day (default, recommended)
- `3` - Three resets per day (more lenient)
- `5` - Five resets per day (very lenient)
- `0` - No limit (not recommended)

### 3. Restart Application

```bash
uvicorn app:app --reload
```

---

## How It Works

### Daily Counter Reset

```
User resets key at 10:00 AM on Jan 1
  → Counter: 1, Date: 2025-01-01
  
User tries to reset again at 11:00 AM on Jan 1
  → ❌ DENIED: "Daily key reset limit (1) reached"
  
User tries to reset at 10:00 AM on Jan 2
  → ✅ ALLOWED: New day, counter resets to 1
  → Counter: 1, Date: 2025-01-02
```

### Database Tracking

The system tracks two fields in `tbl_users`:

| Column | Type | Purpose |
|--------|------|---------|
| `key_reset_count` | INTEGER | How many resets today |
| `key_reset_date` | DATE | Date of last reset |

**Logic:**
```sql
-- On key reset request:
IF key_reset_date = CURRENT_DATE THEN
  -- Same day: increment counter
  key_reset_count = key_reset_count + 1
ELSE
  -- New day: reset counter
  key_reset_count = 1
  key_reset_date = CURRENT_DATE
END IF
```

---

## Configuration Examples

### Conservative (Production)
```bash
API_MAX_DAILY_KEY_RESETS=1
```
- ✅ Best security
- ✅ Prevents abuse
- ⚠️ User must wait until tomorrow if they mess up

### Moderate (Default)
```bash
API_MAX_DAILY_KEY_RESETS=2
```
- ✅ Good security
- ✅ Allows one mistake
- ✅ Still prevents abuse

### Lenient (Development)
```bash
API_MAX_DAILY_KEY_RESETS=5
```
- ⚠️ Lower security
- ✅ Good for testing
- ✅ More forgiving

### No Limit (Not Recommended)
```bash
API_MAX_DAILY_KEY_RESETS=999
```
- ❌ No protection
- Only use for testing/development

---

## Error Response

When limit is exceeded:

```bash
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

**Response:**
```json
{
  "detail": "Daily key reset limit (1) reached. Try again tomorrow."
}
```

**HTTP Status:** `429 Too Many Requests`

---

## Rate Limiting Stack

The system now has **two layers** of rate limiting:

### Layer 1: IP-Based Rate Limiting (slowapi)
```python
@limiter.limit("3/hour")  # Max 3 requests per hour per IP
```

**Purpose:** Prevent brute force from single IP  
**Scope:** Per IP address  
**Reset:** Every hour

### Layer 2: Daily User Limit (Database)
```python
MAX_DAILY_RESETS = 1  # Max 1 reset per day per user
```

**Purpose:** Prevent abuse by authenticated users  
**Scope:** Per user account  
**Reset:** Every day at midnight

**Combined Protection:**
```
IP from 1.2.3.4 makes 3 requests in 1 hour → ❌ Blocked (IP limit)
User makes 1 reset, tries again same day → ❌ Blocked (daily limit)
User makes 1 reset, tries tomorrow → ✅ Allowed (new day)
```

---

## Monitoring

### Check User's Reset Status

```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date,
    CASE 
        WHEN key_reset_date = CURRENT_DATE 
        THEN 'Can reset: ' || (1 - key_reset_count)::text || ' times today'
        ELSE 'Can reset today (new day)'
    END as reset_status
FROM tbl_users
WHERE email = 'user@example.com';
```

### Find Users Who Hit Limit Today

```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date,
    updated_at
FROM tbl_users
WHERE key_reset_date = CURRENT_DATE
  AND key_reset_count >= 1
ORDER BY key_reset_count DESC, updated_at DESC;
```

### Reset Counter Manually (Admin Override)

```sql
-- Reset for specific user
UPDATE tbl_users
SET key_reset_count = 0,
    key_reset_date = NULL
WHERE email = 'user@example.com';

-- Or just update the date to allow reset
UPDATE tbl_users
SET key_reset_date = CURRENT_DATE - INTERVAL '1 day'
WHERE email = 'user@example.com';
```

---

## Testing

### Test the Limit

```bash
# First reset - should work
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response: 200 OK with new API key

# Second reset (same day) - should fail
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response: 429 Too Many Requests
# {"detail": "Daily key reset limit (1) reached. Try again tomorrow."}
```

### Test Counter Reset (New Day)

```sql
-- Simulate next day
UPDATE tbl_users
SET key_reset_date = CURRENT_DATE - INTERVAL '1 day'
WHERE email = 'test@example.com';

-- Now the reset should work again
```

---

## Troubleshooting

### User Says: "I need to reset but hit the limit"

**Options:**

1. **Wait until tomorrow** (recommended)
   - Counter resets at midnight
   - User can reset then

2. **Admin override** (if legitimate need)
   ```sql
   UPDATE tbl_users
   SET key_reset_count = 0
   WHERE email = 'user@example.com';
   ```

3. **Increase limit** (not recommended)
   - Change `API_MAX_DAILY_KEY_RESETS` environment variable
   - Restart application

### Migration Already Applied?

Check if columns exist:
```sql
SELECT column_name 
FROM information_schema.columns
WHERE table_name = 'tbl_users'
  AND column_name IN ('key_reset_count', 'key_reset_date');
```

If they exist, you're good! No need to run migration again.

---

## Best Practices

### For Production
- ✅ Set limit to 1 or 2
- ✅ Monitor reset patterns
- ✅ Alert on unusual activity
- ✅ Log all reset attempts

### For Development
- ✅ Set higher limit (3-5)
- ✅ Or use manual override as needed
- ✅ Test the limit to ensure it works

### For Users
- ✅ Store API keys securely
- ✅ Don't need to reset often
- ✅ Use environment variables
- ✅ Keep backup of API key

---

## Summary

✅ **Added:** Daily key reset limit (default: 1 per day)  
✅ **Database:** Two new columns track resets  
✅ **Configuration:** `API_MAX_DAILY_KEY_RESETS` environment variable  
✅ **Protection:** Prevents abuse while being user-friendly  
✅ **Counter:** Auto-resets at midnight  

**Status:** Ready to deploy after running migration! 🚀
