# Authentication API Quick Reference

## Overview
The authentication system now includes full email integration for professional user onboarding and API key management.

## Key Features
✅ Email-based activation workflow  
✅ Automated welcome emails with API keys  
✅ Secure API key reset via email  
✅ Graceful degradation (works with or without email)  
✅ Production-ready security with bcrypt + JWT  
✅ Comprehensive logging and error handling  

---

## Email Behavior

### When Email IS Configured
- **Registration**: Activation email sent with link
- **Activation**: Welcome email sent with API key copy
- **Key Reset**: New API key sent via email
- **Response**: `email_sent: true` in all responses

### When Email NOT Configured
- **Registration**: Activation token shown in response
- **Activation**: API key shown in response only
- **Key Reset**: New API key shown in response only
- **Response**: `email_sent: false` in all responses

---

## API Endpoints

### 1. Get Authentication Info
```bash
GET /auth/
```

**Response:**
```json
{
  "name": "Authentication API",
  "version": "2.0.0",
  "email_configured": true,
  "flow": {
    "1_register": "POST /auth/register with email",
    "2_activate": "GET /auth/activate?token={token} from email",
    "3_get_token": "POST /auth/token with API key",
    "4_use_token": "Include 'Authorization: Bearer {token}' header"
  },
  "email_info": {
    "provider": "Microsoft Graph API",
    "from_address": "noreply@domain.com",
    "from_name": "Your API Name"
  }
}
```

---

### 2. Register New User
```bash
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com"
}
```

**Success Response (Email Configured):**
```json
{
  "message": "Registration successful. Check your email for activation link.",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "user@example.com",
  "note": "An activation link has been sent to your email...",
  "email_sent": true
}
```

**Success Response (Email NOT Configured):**
```json
{
  "message": "Registration successful (email disabled)",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "user@example.com",
  "note": "For testing, activate at: /auth/activate?token=abc123...",
  "email_sent": false
}
```

**Error Response (Email Exists):**
```json
{
  "detail": "Email already registered and active. Use /auth/token..."
}
```

---

### 3. Activate Account
```bash
GET /auth/activate?token=YOUR_ACTIVATION_TOKEN
```

**Success Response (Email Configured):**
```json
{
  "message": "Account activated successfully!",
  "api_key": "abc123def456...",
  "instructions": "Account activated! Your API key has been sent to your email...",
  "email_sent": true
}
```

**Success Response (Email NOT Configured):**
```json
{
  "message": "Account activated successfully!",
  "api_key": "abc123def456...",
  "instructions": "Save this API key securely - you won't be able to see it again...",
  "email_sent": false
}
```

**Error Response (Invalid Token):**
```json
{
  "detail": "Invalid or expired activation token"
}
```

**Error Response (Already Active):**
```json
{
  "detail": "Account already activated. Use /auth/token to get access token."
}
```

---

### 4. Get Access Token
```bash
POST /auth/token
Content-Type: application/json

{
  "api_key": "YOUR_API_KEY"
}
```

**Success Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "role": "basic"
}
```

**Error Response (Invalid Key):**
```json
{
  "detail": "Invalid API key or account not activated"
}
```

---

### 5. Reset API Key
```bash
POST /auth/key/reset
Content-Type: application/json

{
  "email": "user@example.com"
}
```

**Success Response (Email Configured):**
```json
{
  "message": "API key reset successful - check your email",
  "api_key": "new_key_abc123...",
  "instructions": "Your old API key and all tokens are now invalid. The new key has been sent to your email...",
  "email_sent": true
}
```

**Success Response (Email NOT Configured):**
```json
{
  "message": "API key reset successful (email disabled)",
  "api_key": "new_key_abc123...",
  "instructions": "Your old API key and all tokens are now invalid. Save this new key securely...",
  "email_sent": false
}
```

**Error Response (Email Not Found):**
```json
{
  "detail": "Email not found. Please register first."
}
```

**Error Response (Not Activated):**
```json
{
  "detail": "Account not activated. Please activate your account first."
}
```

---

## Authentication Flow

### Standard Flow (Email Configured)

```
1. Register
   └─> POST /auth/register {"email": "user@example.com"}
       └─> ✉️ Activation email sent
           └─> User clicks link in email

2. Activate
   └─> GET /auth/activate?token=...
       └─> ✉️ Welcome email sent with API key
           └─> User saves API key

3. Get Token
   └─> POST /auth/token {"api_key": "..."}
       └─> Receive JWT access token

4. Make Requests
   └─> Any API endpoint with header:
       Authorization: Bearer {access_token}
```

### Testing Flow (Email NOT Configured)

```
1. Register
   └─> POST /auth/register {"email": "user@example.com"}
       └─> Activation token in response

2. Activate
   └─> GET /auth/activate?token=... (from step 1)
       └─> API key in response

3. Get Token
   └─> POST /auth/token {"api_key": "..."} (from step 2)
       └─> Receive JWT access token

4. Make Requests
   └─> Any API endpoint with header:
       Authorization: Bearer {access_token}
```

---

## Using Access Tokens

### In curl
```bash
curl http://localhost:8000/api/search/simple \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": [{"field": "sex", "value": "Male"}],
    "logic": "AND",
    "limit": 25
  }'
```

### In Python
```python
import requests

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:8000/api/search/simple",
    json={
        "filters": [{"field": "sex", "value": "Male"}],
        "logic": "AND",
        "limit": 25
    },
    headers=headers
)

print(response.json())
```

### In JavaScript
```javascript
const response = await fetch('http://localhost:8000/api/search/simple', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    filters: [{field: 'sex', value: 'Male'}],
    logic: 'AND',
    limit: 25
  })
});

const data = await response.json();
console.log(data);
```

---

## Email Templates

### Activation Email
- **Subject**: "Activate Your [App Name] Account"
- **Content**: 
  - Welcome message
  - Clickable activation button
  - Manual activation link (copy/paste)
  - Expiration warning (48 hours)
  - Next steps overview

### Welcome Email
- **Subject**: "Welcome to [App Name] - Your API Key"
- **Content**:
  - Congratulations message
  - API key (monospace font)
  - Security reminders
  - Quick start guide
  - Example API calls
  - Documentation link

### API Key Reset Email
- **Subject**: "Your New [App Name] Key"
- **Content**:
  - New API key (monospace font)
  - Security warnings
  - Invalidation notice
  - Usage instructions
  - Example API calls

---

## Security Notes

### API Key Security
- ✅ API keys are 32+ characters alphanumeric
- ✅ Stored as bcrypt hashes (never plaintext)
- ✅ Cannot be retrieved after first display
- ✅ Reset invalidates old key and all tokens

### JWT Token Security
- ✅ Tokens expire after 60 minutes (configurable)
- ✅ Stateless - no server-side session storage
- ✅ Signed with HS256 algorithm
- ✅ Contains role for authorization

### Activation Token Security
- ✅ Cryptographically secure random generation
- ✅ URL-safe encoding
- ✅ Expires after 48 hours
- ✅ Single-use (cleared on activation)

### Rate Limiting
- Registration: 10/minute per IP
- Token generation: 10/minute per IP
- Key reset: 3/hour per IP (stricter)

---

## Logging

All authentication events are logged:

```
INFO: New user registered: user@example.com (user_id: ...)
INFO: Activation email sent to user@example.com
INFO: Account activated: user@example.com (user_id: ...)
INFO: Welcome email sent to user@example.com
INFO: Token generated for user: user@example.com (user_id: ...)
INFO: API key reset for user: user@example.com (user_id: ...)
WARNING: Failed to send activation email to user@example.com
ERROR: Registration error: ...
```

---

## Testing

### Quick Test
```bash
# Test registration
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# If email NOT configured, copy activation token from response
# If email configured, check email for activation link

# Test activation (use token from email or response)
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN"

# Copy API key from response or email

# Test token generation
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YOUR_API_KEY"}'

# Copy access_token from response

# Test authenticated request
curl http://localhost:8000/api/search/simple \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filters": [{"field": "sex", "value": "Male"}], "logic": "AND", "limit": 25}'
```

### Comprehensive Test
```bash
python test_auth_flow.py test@example.com
```

---

## Troubleshooting

### Email Not Sending
1. Check: `curl http://localhost:8000/auth/` - is `email_configured: true`?
2. Run: `python test_email.py test@example.com`
3. Verify environment variables are set
4. Check logs for email errors

### Activation Link Not Working
1. Check: Token hasn't expired (48 hours)
2. Verify: `API_APP_BASE_URL` is correct
3. Check: Token in database matches link

### Token Invalid
1. Check: Token hasn't expired (60 minutes)
2. Verify: API key is correct
3. Confirm: Account is activated
4. Try: Generate new token

### Rate Limit Hit
1. Wait: Rate limit will reset
2. Check: Current rate limits in code
3. Adjust: `rate_max` variable if needed

---

## Support

### Get System Status
```bash
curl http://localhost:8000/auth/health
```

### View API Documentation
```
http://localhost:8000/docs
```

### Check Logs
```bash
tail -f /var/log/your-api.log | grep -E "(auth|email|activation)"
```

---

**Version:** 2.0  
**Last Updated:** 2025-01-XX  
**Documentation:** See DEPLOYMENT_CHECKLIST.md for complete deployment guide
