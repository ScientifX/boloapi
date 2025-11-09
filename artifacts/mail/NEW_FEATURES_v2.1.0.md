# New Features Summary - v2.1.0

## Two New Features Added

### 1. ✅ Daily Key Reset Limit
Configurable daily limit on API key resets per user (default: 1/day)

### 2. ✅ Multiple Valid JWT Tokens
Documented and confirmed: Multiple tokens can be valid simultaneously (by design)

---

## Feature 1: Daily Key Reset Limit

### What It Does
Prevents users from resetting their API key too many times in one day.

### Configuration
```bash
# Environment variable (optional, defaults to 1)
API_MAX_DAILY_KEY_RESETS=1
```

### Database Changes Required
```sql
ALTER TABLE tbl_users 
ADD COLUMN IF NOT EXISTS key_reset_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS key_reset_date DATE;
```

### Setup Instructions
1. Run migration: `psql -U user -d db -f migration_key_reset_tracking.sql`
2. Set environment variable (optional, defaults to 1)
3. Restart application

### Behavior
- First reset of the day: ✅ Works
- Subsequent resets same day: ❌ Blocked with 429 error
- Next day: ✅ Counter resets, can reset again

### Files
- **Code:** Updated in `router_auth.py`
- **Migration:** [migration_key_reset_tracking.sql](computer:///mnt/user-data/outputs/migration_key_reset_tracking.sql)
- **Guide:** [KEY_RESET_LIMIT_SETUP.md](computer:///mnt/user-data/outputs/KEY_RESET_LIMIT_SETUP.md)

---

## Feature 2: Multiple Valid JWT Tokens (Documentation)

### What It Means
Users can have multiple valid access tokens at the same time. This is **normal** JWT behavior.

### Example
```
10:00 - Get token A (expires 11:00)
10:30 - Get token B (expires 11:30)
10:45 - Both tokens work! ✅
```

### Why This Is Good
- ✅ **Scalability:** Stateless tokens, no database lookups
- ✅ **Flexibility:** Multiple devices can use different tokens
- ✅ **Performance:** No server-side session management

### Security
- Tokens are short-lived (1 hour default)
- Tokens can't be forged (signed)
- Resetting API key invalidates all tokens from that key

### Files
- **Documentation:** [JWT_TOKEN_BEHAVIOR.md](computer:///mnt/user-data/outputs/JWT_TOKEN_BEHAVIOR.md)

---

## Quick Start

### Setup Key Reset Limit

1. **Run Migration:**
   ```bash
   psql -U your_user -d your_db -f migration_key_reset_tracking.sql
   ```

2. **Set Limit (Optional):**
   ```bash
   # In .env or environment
   API_MAX_DAILY_KEY_RESETS=1
   ```

3. **Restart App:**
   ```bash
   uvicorn app:app --reload
   ```

4. **Test It:**
   ```bash
   # First reset - should work
   curl -X POST http://localhost:8000/auth/key/reset \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com"}'
   
   # Second reset same day - should fail with 429
   curl -X POST http://localhost:8000/auth/key/reset \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com"}'
   ```

### Understanding JWT Tokens

Read the documentation:
- [JWT_TOKEN_BEHAVIOR.md](computer:///mnt/user-data/outputs/JWT_TOKEN_BEHAVIOR.md)

Key takeaways:
- Multiple valid tokens = normal ✅
- Tokens expire after 1 hour
- Old tokens work until they expire
- Reset API key to invalidate all tokens

---

## All Updated Files

### Production Code
- **[router_auth.py v2.1.0](computer:///mnt/user-data/outputs/router_auth.py)** - Added key reset limit logic

### Database
- **[migration_key_reset_tracking.sql](computer:///mnt/user-data/outputs/migration_key_reset_tracking.sql)** - New columns for tracking

### Documentation
- **[KEY_RESET_LIMIT_SETUP.md](computer:///mnt/user-data/outputs/KEY_RESET_LIMIT_SETUP.md)** - Complete setup guide
- **[JWT_TOKEN_BEHAVIOR.md](computer:///mnt/user-data/outputs/JWT_TOKEN_BEHAVIOR.md)** - Token behavior explained
- **[DEPLOYMENT_STATUS.md](computer:///mnt/user-data/outputs/DEPLOYMENT_STATUS.md)** - Updated status
- **[USER_WORKFLOW_GUIDE.md](computer:///mnt/user-data/outputs/USER_WORKFLOW_GUIDE.md)** - User guide (from earlier)

---

## Testing Checklist

### Key Reset Limit
- [ ] Run database migration
- [ ] Set environment variable
- [ ] Restart application
- [ ] Test first reset (should work)
- [ ] Test second reset same day (should fail)
- [ ] Verify error message shows limit
- [ ] Verify counter resets next day

### JWT Tokens
- [ ] Get first access token
- [ ] Make API request with token #1 (works)
- [ ] Get second access token
- [ ] Make API request with token #1 (still works)
- [ ] Make API request with token #2 (also works)
- [ ] Wait for token #1 to expire
- [ ] Make API request with token #1 (fails)
- [ ] Make API request with token #2 (still works)

---

## Configuration Reference

### Environment Variables

```bash
# JWT Configuration
API_JWT_SECRET_KEY=your-secret-key
API_JWT_ALGORITHM=HS256
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60  # 1 hour

# Key Reset Limit (NEW)
API_MAX_DAILY_KEY_RESETS=1  # Default: 1
```

### Recommended Settings

**Production:**
```bash
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
API_MAX_DAILY_KEY_RESETS=1
```

**Development:**
```bash
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=480  # 8 hours
API_MAX_DAILY_KEY_RESETS=5
```

---

## Monitoring

### Check Key Reset Status
```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date,
    CASE 
        WHEN key_reset_date = CURRENT_DATE 
        THEN key_reset_count || ' resets today'
        ELSE 'No resets today'
    END as status
FROM tbl_users
ORDER BY key_reset_date DESC NULLS LAST;
```

### Find Users Hitting Limit
```sql
SELECT 
    email,
    key_reset_count,
    key_reset_date
FROM tbl_users
WHERE key_reset_date = CURRENT_DATE
  AND key_reset_count >= 1
ORDER BY key_reset_count DESC;
```

---

## Troubleshooting

### "Daily key reset limit reached"

**User hit the limit. Options:**

1. **Wait until tomorrow** (recommended)
2. **Admin override:**
   ```sql
   UPDATE tbl_users
   SET key_reset_count = 0
   WHERE email = 'user@example.com';
   ```

### "My old token still works after getting a new one"

**This is normal!** See [JWT_TOKEN_BEHAVIOR.md](computer:///mnt/user-data/outputs/JWT_TOKEN_BEHAVIOR.md) for explanation.

**To invalidate old tokens:**
- Wait for them to expire (1 hour)
- OR reset API key (invalidates all tokens)

---

## Version History

### v2.1.0 (Current)
- ✅ Added daily key reset limit
- ✅ Documented JWT token behavior
- ✅ Added user workflow guide
- ✅ Improved UX messaging

### v2.0.3
- Fixed timezone comparison
- Fixed query parameter type
- Improved user instructions

### v2.0.0
- Initial email integration

---

## Summary

Two important updates:

1. **Security:** Added configurable daily limit on key resets (default: 1/day)
2. **Clarity:** Documented that multiple valid JWT tokens is normal behavior

Both features enhance security and user experience!

**Status:** Ready to deploy (run migration first) 🚀

---

**Next Steps:**
1. Read [KEY_RESET_LIMIT_SETUP.md](computer:///mnt/user-data/outputs/KEY_RESET_LIMIT_SETUP.md)
2. Read [JWT_TOKEN_BEHAVIOR.md](computer:///mnt/user-data/outputs/JWT_TOKEN_BEHAVIOR.md)
3. Run database migration
4. Test the new features
5. Deploy with confidence!
