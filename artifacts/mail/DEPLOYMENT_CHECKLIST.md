# Email Integration Deployment Checklist

## Overview
This document provides a complete checklist for deploying the updated authentication system with email integration.

## Files Modified/Created

### Modified Files
1. **router_auth.py** - Updated with full email integration
   - Registration sends activation emails
   - Activation sends welcome emails with API key
   - Key reset sends new API key via email
   - All endpoints include email_sent flag in responses
   - Graceful degradation when email not configured

### Existing Files (No Changes Required)
- `email_utils.py` - Already complete
- `test_email.py` - Already working
- `config.py` - Already has email config
- `security_utils.py` - Already complete
- `jwt_utils.py` - Already complete
- `auth.py` - Already complete
- `jwt_auth.py` - Already complete

### New Files
1. **test_auth_flow.py** - Comprehensive authentication flow testing script

## Pre-Deployment Checklist

### 1. Environment Variables ✓
Verify all required environment variables are set:

```bash
# Database Configuration
API_DB_HOST=your_host
API_DB_PORT=5432
API_DB_DATABASE=your_db
API_DB_USER=your_user
API_DB_PASSWORD=your_password

# JWT Configuration
API_JWT_SECRET_KEY=your-secret-key-min-32-chars
API_JWT_ALGORITHM=HS256
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Microsoft Email Configuration
API_AZURE_TENANT_ID=your-tenant-id
API_AZURE_CLIENT_ID=your-client-id
API_AZURE_CLIENT_SECRET=your-client-secret
API_EMAIL_FROM_ADDRESS=noreply@yourdomain.com
API_EMAIL_FROM_NAME=Your API Name

# Application Configuration
API_APP_BASE_URL=https://your-api-domain.com
```

### 2. Database Schema ✓
Verify `tbl_users` table exists with correct schema:

```sql
-- Should already exist, but verify:
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tbl_users'
ORDER BY ordinal_position;

-- Required columns:
-- user_id (uuid, primary key)
-- email (varchar, unique)
-- api_key_hash (text)
-- role (varchar)
-- is_active (boolean)
-- activation_token (varchar, nullable)
-- activation_expires_at (timestamp, nullable)
-- created_at (timestamp)
-- updated_at (timestamp)
-- last_login_at (timestamp, nullable)
```

### 3. Email Configuration ✓
Run the email test script to verify email is working:

```bash
python test_email.py your-test-email@domain.com
```

Expected output:
- ✅ All configuration variables are set
- ✅ Successfully obtained access token
- ✅ Activation email sent successfully
- ✅ API key email sent successfully
- ✅ Welcome email sent successfully

### 4. Python Dependencies ✓
Verify all required packages are installed:

```bash
pip install fastapi psycopg2-binary python-jose[cryptography] bcrypt python-dotenv requests slowapi pydantic
```

## Deployment Steps

### Step 1: Backup Current System
```bash
# Backup current router_auth.py
cp router_auth.py router_auth.py.backup

# Backup database
pg_dump your_database > backup_$(date +%Y%m%d).sql
```

### Step 2: Deploy New Code
```bash
# Copy new router_auth.py to your project
cp /path/to/new/router_auth.py ./router_auth.py

# Copy test script (optional but recommended)
cp /path/to/test_auth_flow.py ./test_auth_flow.py

# Verify file permissions
chmod 644 router_auth.py
chmod 755 test_auth_flow.py
```

### Step 3: Verify Imports
Make sure app.py includes the router:

```python
# In app.py
import router_auth

# ...

app.include_router(router_auth.router)
```

### Step 4: Restart Application
```bash
# If using uvicorn directly
uvicorn app:app --reload

# If using systemd
sudo systemctl restart your-api-service

# If using Docker
docker-compose restart api
```

### Step 5: Health Check
```bash
# Check application is running
curl http://localhost:8000/health

# Check auth endpoint
curl http://localhost:8000/auth/

# Expected response includes:
# {
#   "email_configured": true/false,
#   ...
# }
```

## Post-Deployment Testing

### Manual Testing Sequence

#### Test 1: Registration (Email Configured)
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Expected response:
# {
#   "message": "Registration successful. Check your email for activation link.",
#   "user_id": "...",
#   "email": "test@example.com",
#   "note": "An activation link has been sent...",
#   "email_sent": true
# }

# ✓ Check: Email received in inbox
# ✓ Check: Activation link is clickable
# ✓ Check: Link format is correct
```

#### Test 2: Registration (Email NOT Configured)
```bash
# Same as above, but expected response:
# {
#   "message": "Registration successful (email disabled)",
#   "user_id": "...",
#   "email": "test@example.com",
#   "note": "For testing, activate at: /auth/activate?token=...",
#   "email_sent": false
# }

# ✓ Check: Activation token provided in response
```

#### Test 3: Activation
```bash
# Click email link OR use token from registration
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN"

# Expected response:
# {
#   "message": "Account activated successfully!",
#   "api_key": "...",
#   "instructions": "...",
#   "email_sent": true/false
# }

# ✓ Check: API key returned
# ✓ Check: Welcome email sent (if email configured)
# ✓ Check: Account is active in database
```

#### Test 4: Token Generation
```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YOUR_API_KEY"}'

# Expected response:
# {
#   "access_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 3600,
#   "role": "basic"
# }

# ✓ Check: Valid JWT token returned
# ✓ Check: Token works for authenticated requests
```

#### Test 5: Authenticated Request
```bash
curl http://localhost:8000/api/search/simple \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": [{"field": "sex", "value": "Male"}],
    "logic": "AND",
    "limit": 25
  }'

# Expected response:
# {
#   "query": {...},
#   "role": "basic",
#   "resultcount": X,
#   "items": [...]
# }

# ✓ Check: Request succeeds with token
# ✓ Check: Results returned
```

#### Test 6: Key Reset
```bash
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Expected response:
# {
#   "message": "API key reset successful - check your email",
#   "api_key": "...",
#   "instructions": "...",
#   "email_sent": true
# }

# ✓ Check: New API key returned
# ✓ Check: Old API key no longer works
# ✓ Check: Reset email sent (if configured)
```

### Automated Testing
```bash
# Run complete test suite
python test_auth_flow.py test@example.com

# Expected output:
# ✅ PASS  Auth Info
# ✅ PASS  Registration
# ✅ PASS  Activation
# ✅ PASS  Token Generation
# ✅ PASS  Authenticated Request
# ✅ PASS  Key Reset (optional)
```

## Verification Checklist

### Functionality Verification
- [ ] Registration endpoint accepts valid emails
- [ ] Registration rejects invalid emails
- [ ] Registration handles duplicate emails correctly
- [ ] Activation emails are sent (if configured)
- [ ] Activation links work correctly
- [ ] Activation generates valid API keys
- [ ] Welcome emails are sent (if configured)
- [ ] Token endpoint accepts valid API keys
- [ ] Token endpoint rejects invalid API keys
- [ ] Generated tokens are valid JWTs
- [ ] Tokens work for authenticated endpoints
- [ ] Key reset endpoint works
- [ ] Key reset emails are sent (if configured)
- [ ] Old keys are invalidated after reset

### Email Verification (If Configured)
- [ ] Activation emails have correct subject
- [ ] Activation emails have clickable links
- [ ] Activation links have correct format
- [ ] Welcome emails include API key
- [ ] Welcome emails have getting started info
- [ ] Key reset emails include new key
- [ ] Key reset emails have security warnings
- [ ] All emails have professional formatting
- [ ] Email sender name is correct
- [ ] Emails don't go to spam

### Graceful Degradation (Email NOT Configured)
- [ ] Registration works without email
- [ ] Activation token shown in response
- [ ] Activation works with token
- [ ] API key shown in activation response
- [ ] Key reset works without email
- [ ] New key shown in reset response
- [ ] All endpoints indicate email_sent: false

### Security Verification
- [ ] API keys are properly hashed in database
- [ ] Activation tokens expire after 48 hours
- [ ] JWT tokens expire after configured time
- [ ] Old tokens don't work after key reset
- [ ] Rate limiting is enforced
- [ ] SQL injection protection works
- [ ] Invalid tokens are rejected properly

### Database Verification
```sql
-- Check user records are created correctly
SELECT 
    user_id,
    email,
    role,
    is_active,
    activation_token IS NOT NULL as has_activation_token,
    created_at,
    last_login_at
FROM tbl_users
ORDER BY created_at DESC
LIMIT 5;

-- Verify API key hashes are stored
SELECT 
    user_id,
    email,
    length(api_key_hash) as hash_length,
    api_key_hash LIKE '$2b$%' as is_bcrypt_hash
FROM tbl_users
WHERE is_active = true
LIMIT 5;

-- Check activation token cleanup
SELECT 
    user_id,
    email,
    is_active,
    activation_token IS NULL as token_cleared,
    activation_expires_at IS NULL as expiry_cleared
FROM tbl_users
WHERE is_active = true;
```

## Rollback Procedure

If deployment fails:

### Step 1: Stop Application
```bash
# Stop the API
sudo systemctl stop your-api-service
# OR
kill $(pgrep -f "uvicorn app:app")
```

### Step 2: Restore Backup
```bash
# Restore previous router_auth.py
cp router_auth.py.backup router_auth.py

# If database changes were made (shouldn't be necessary):
# psql your_database < backup_$(date +%Y%m%d).sql
```

### Step 3: Restart Application
```bash
sudo systemctl start your-api-service
# OR
uvicorn app:app --reload
```

### Step 4: Verify Rollback
```bash
curl http://localhost:8000/auth/
# Should return previous version
```

## Monitoring

### Key Metrics to Monitor
1. **Registration Success Rate**
   - Track successful vs failed registrations
   - Monitor for validation errors

2. **Email Delivery Rate**
   - Track email_sent: true vs false
   - Monitor email sending failures

3. **Activation Rate**
   - Track activations vs registrations
   - Monitor activation token expiration

4. **Token Generation Rate**
   - Track successful token generations
   - Monitor invalid API key attempts

5. **Error Rates**
   - Monitor 400/401/500 error responses
   - Track specific error types

### Log Monitoring
```bash
# Watch logs for email-related entries
tail -f /var/log/your-api.log | grep -E "(email|activation|registration)"

# Look for these patterns:
# INFO: New user registered: email@example.com
# INFO: Activation email sent to email@example.com
# INFO: Account activated: email@example.com
# INFO: Welcome email sent to email@example.com
# INFO: Token generated for user: email@example.com
# INFO: API key reset for user: email@example.com
# WARNING: Failed to send activation email to email@example.com
# ERROR: Registration error: ...
```

## Support Resources

### Common Issues

**Issue: Email not sending**
- Check: Environment variables set correctly
- Check: Azure AD permissions granted
- Check: Network connectivity to Microsoft Graph API
- Solution: Run `python test_email.py` to diagnose

**Issue: Activation links not working**
- Check: API_APP_BASE_URL is correct
- Check: Token hasn't expired
- Check: Token matches database
- Solution: Verify activation token in database

**Issue: Tokens not working**
- Check: JWT secret key is set
- Check: Token hasn't expired
- Check: API key is correct
- Solution: Generate new token with valid API key

**Issue: Rate limiting too strict**
- Check: Rate limit configuration
- Solution: Adjust rate_max in router_auth.py

### Documentation References
- Microsoft Graph API: https://docs.microsoft.com/en-us/graph/
- FastAPI: https://fastapi.tiangolo.com/
- JWT: https://jwt.io/introduction
- Bcrypt: https://github.com/pyca/bcrypt/

## Success Criteria

Deployment is successful when:
- ✅ All automated tests pass
- ✅ Manual registration flow works
- ✅ Emails are delivered (if configured)
- ✅ Activation works correctly
- ✅ Tokens are generated successfully
- ✅ Authenticated requests work
- ✅ Key reset works correctly
- ✅ No errors in logs
- ✅ Database records are correct
- ✅ Graceful degradation works (email disabled)

---

**Document Version:** 2.0
**Last Updated:** 2025-01-XX
**Prepared by:** Development Team
