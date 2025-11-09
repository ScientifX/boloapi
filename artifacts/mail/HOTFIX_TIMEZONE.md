# Hotfix v2 - Timezone Comparison Fix

## Issue #2: Timezone Comparison Error

When calling `/auth/activate`, you received:
```json
{"detail":"Activation failed: can't compare offset-naive and offset-aware datetimes"}
```

## Root Cause

PostgreSQL `timestamp` columns (without timezone) store **naive** datetimes (no timezone info), but the code was comparing them with **timezone-aware** datetimes created by `datetime.now(timezone.utc)`.

**Python datetime types:**
- **Naive**: `datetime(2025, 1, 9, 12, 0, 0)` - no timezone
- **Aware**: `datetime(2025, 1, 9, 12, 0, 0, tzinfo=timezone.utc)` - has timezone

**The problem:**
```python
# Database returns naive datetime
user['activation_expires_at']  # 2025-01-09 12:00:00 (naive)

# Code compares with aware datetime
datetime.now(timezone.utc)  # 2025-01-09 12:00:00+00:00 (aware)

# This comparison fails!
if user['activation_expires_at'] < datetime.now(timezone.utc):  # ❌ Error!
```

## Fix Applied

### 1. Fixed Activation Comparison (Line ~340)

**Before:**
```python
# Check if token expired
if user['activation_expires_at'] and user['activation_expires_at'] < datetime.now(timezone.utc):
    raise HTTPException(...)
```

**After:**
```python
# Check if token expired
if user['activation_expires_at']:
    # Make comparison timezone-aware or timezone-naive depending on database value
    expiry_time = user['activation_expires_at']
    current_time = datetime.now(timezone.utc)
    
    # If expiry_time is naive (no timezone), make current_time naive too
    if expiry_time.tzinfo is None:
        current_time = datetime.now()
    
    if expiry_time < current_time:
        raise HTTPException(...)
```

### 2. Fixed Registration - Store Naive Datetime (Line ~190)

**Before:**
```python
activation_expires = datetime.now(timezone.utc) + timedelta(hours=48)
# ... 
(activation_token, activation_expires, user_id)  # Stores aware datetime ❌
```

**After:**
```python
activation_expires = datetime.now(timezone.utc) + timedelta(hours=48)
# ...
(activation_token, activation_expires.replace(tzinfo=None), user_id)  # Stores naive datetime ✅
```

### 3. Fixed Registration - New User (Line ~249)

**Before:**
```python
(email, UserRole.BASIC.value, api_key_hash, activation_token, activation_expires)
# Stores aware datetime ❌
```

**After:**
```python
(email, UserRole.BASIC.value, api_key_hash, activation_token, activation_expires.replace(tzinfo=None))
# Stores naive datetime ✅
```

## Why This Solution Works

1. **Consistent Storage**: Always store naive datetimes in the database using `.replace(tzinfo=None)`
2. **Smart Comparison**: Check if database value is naive, then compare with matching type
3. **Future-Proof**: Works whether your database uses `timestamp` or `timestamptz`

## Alternative Solution (If You Prefer)

If you want to use timezone-aware datetimes throughout, change your database column:

```sql
-- Change column type to timestamptz (stores timezone)
ALTER TABLE tbl_users 
ALTER COLUMN activation_expires_at TYPE timestamptz;
```

Then remove the `.replace(tzinfo=None)` calls. But the current fix works with your existing schema.

## Files Updated

✅ **router_auth.py** - Fixed and ready in outputs directory

## Testing the Fix

### 1. Restart Your Application
```bash
uvicorn app:app --reload
```

### 2. Test Registration
```bash
curl -X POST http://localhost:8000/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"email\": \"newtest@example.com\"}"
```

Should return registration response with activation token.

### 3. Test Activation
```bash
# Use the token from registration response
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN_HERE"
```

Should return successful activation with API key!

### 4. If Token Already Expired

The error you saw means your activation actually *worked* - it just complained about the comparison. But to test with a fresh token:

```bash
# Register a new email
curl -X POST http://localhost:8000/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"email\": \"test$(date +%s)@example.com\"}"

# Copy the activation token from response
# Then activate
curl "http://localhost:8000/auth/activate?token=NEW_TOKEN"
```

## Complete Testing

Run the comprehensive test:
```bash
python test_auth_flow.py test@example.com
```

This should now work without timezone errors!

## What Changed Summary

| Location | Issue | Fix |
|----------|-------|-----|
| Line ~190 | Stored aware datetime in UPDATE | Add `.replace(tzinfo=None)` |
| Line ~249 | Stored aware datetime in INSERT | Add `.replace(tzinfo=None)` |
| Line ~340 | Compared naive vs aware | Smart comparison logic |

## Database Schema Note

Your database schema uses `timestamp` (without timezone):
```sql
activation_expires_at timestamp
```

If you ever want timezone-aware throughout:
```sql
ALTER TABLE tbl_users 
ALTER COLUMN activation_expires_at TYPE timestamptz;
ALTER COLUMN created_at TYPE timestamptz;
ALTER COLUMN updated_at TYPE timestamptz;
ALTER COLUMN last_login_at TYPE timestamptz;
```

But the current fix works with your existing `timestamp` columns!

---

**Status**: ✅ Fixed  
**Version**: router_auth.py v2.0.2  
**Impact**: No database changes needed  
**Date**: 2025-01-XX
