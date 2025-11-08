# Email Integration Guide

This guide walks you through integrating the email functionality into your existing FBI Wanted API authentication system.

## Quick Start

**Total Time:** ~30 minutes for Azure setup + 5 minutes for code integration

### Prerequisites Checklist
- [ ] Microsoft 365 subscription with your domain
- [ ] Admin access to Azure Portal
- [ ] Python environment with FastAPI
- [ ] Existing authentication system (router_auth.py)

---

## Step 1: Azure AD Configuration (20-30 minutes)

Follow the detailed instructions in `MICROSOFT_365_EMAIL_SETUP.md`:

1. Register application in Azure AD
2. Create client secret
3. Configure Mail.Send permission
4. Grant admin consent

**Important:** Save these values as you complete each step:
- Tenant ID
- Client ID
- Client Secret (only shown once!)

---

## Step 2: Environment Setup (2 minutes)

### 2.1 Install Dependencies

```bash
pip install requests
```

### 2.2 Configure Environment Variables

Add to your `.env` file:

```bash
# Email Configuration (Microsoft 365)
MICROSOFT_TENANT_ID=your-tenant-id-here
MICROSOFT_CLIENT_ID=your-client-id-here
MICROSOFT_CLIENT_SECRET=your-client-secret-here
EMAIL_FROM_ADDRESS=noreply@yourdomain.com
API_BASE_URL=https://api.yourdomain.com  # or http://localhost:8000 for dev
```

**Security Note:** Never commit `.env` to version control!

---

## Step 3: Add Email Module (1 minute)

### 3.1 Copy Email Utilities

Copy `email_utils.py` to your project directory:

```bash
# Linux/Mac
cp email_utils.py /path/to/your/project/

# Windows PowerShell
Copy-Item email_utils.py -Destination C:\path\to\your\project\
```

### 3.2 Verify Placement

Your project structure should look like:

```
your_project/
├── app.py
├── router_auth.py          # Your existing file
├── email_utils.py          # ← New file
├── security_utils.py
├── jwt_utils.py
├── dbconfig.py
└── .env
```

---

## Step 4: Update Authentication Router (2 minutes)

### Option A: Replace Entire File (Recommended)

If you haven't made custom modifications to `router_auth.py`:

```bash
# Backup your current file first
cp router_auth.py router_auth.py.backup

# Replace with updated version
cp router_auth_updated.py router_auth.py
```

### Option B: Manual Integration

If you've customized `router_auth.py`, add these changes:

#### 4.1 Add Imports (top of file)

```python
import logging
from email_utils import (
    send_activation_email,
    send_api_key_email,
    send_welcome_email,
    EmailConfig
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

#### 4.2 Update `/register` Endpoint

Find the TODO comments and replace:

```python
# OLD (lines 188-189):
# TODO: Send activation email
# send_activation_email(email, activation_token)

# NEW:
email_sent = False
if EmailConfig.is_configured():
    try:
        email_sent = send_activation_email(email, activation_token)
        logger.info(f"Activation email sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send activation email to {email}: {str(e)}")
else:
    logger.warning("Email not configured - activation email not sent")

response_note = (
    "Check your email for the activation link." if email_sent
    else f"For testing: /auth/activate?token={activation_token}"
)
```

Update the return statement to use `response_note`.

#### 4.3 Update `/activate` Endpoint

Add after account activation (around line 302):

```python
# Send welcome email with API key
if EmailConfig.is_configured():
    try:
        send_welcome_email(user['email'], api_key)
        logger.info(f"Welcome email sent to {user['email']}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user['email']}: {str(e)}")
```

#### 4.4 Update `/key/reset` Endpoint

Find the TODO comment and replace (around lines 451-452):

```python
# OLD:
# TODO: Send new API key via email
# send_api_key_email(email, api_key)

# NEW:
email_sent = False
if EmailConfig.is_configured():
    try:
        email_sent = send_api_key_email(email, api_key)
        logger.info(f"API key reset email sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send API key reset email to {email}: {str(e)}")
else:
    logger.warning("Email not configured - API key not sent via email")
```

#### 4.5 Update `/` Info Endpoint

Add email configuration status:

```python
return {
    "name": "Authentication API",
    "version": "1.0.0",
    "email_configured": EmailConfig.is_configured(),  # ← Add this line
    "flow": {
        # ... rest of your existing code
    }
}
```

---

## Step 5: Test Email Functionality (5 minutes)

### 5.1 Test Configuration

```bash
python test_email.py your-email@example.com
```

This will:
1. ✅ Verify Azure AD configuration
2. ✅ Test authentication
3. ✅ Send test activation email
4. ✅ Send test API key email
5. ✅ Send test welcome email

### 5.2 Expected Output

```
══════════════════════════════════════════════════════════════════════
  EMAIL FUNCTIONALITY TEST SUITE
══════════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════════
  Checking Email Configuration
══════════════════════════════════════════════════════════════════════
✅ All configuration variables are set

══════════════════════════════════════════════════════════════════════
  Testing Microsoft Graph API Authentication
══════════════════════════════════════════════════════════════════════
✅ Successfully obtained access token

══════════════════════════════════════════════════════════════════════
  Test Summary
══════════════════════════════════════════════════════════════════════
  ✅ PASS  Configuration
  ✅ PASS  Authentication
  ✅ PASS  Activation Email
  ✅ PASS  API Key Email
  ✅ PASS  Welcome Email

──────────────────────────────────────────────────────────────────────
  ✅ ALL TESTS PASSED!
  Email functionality is working correctly.
──────────────────────────────────────────────────────────────────────
```

### 5.3 Check Your Inbox

1. Check spam/junk folders
2. Verify HTML formatting
3. Test activation links
4. Confirm code examples are readable

---

## Step 6: Test with Real Registration Flow (5 minutes)

### 6.1 Start Your API

```bash
# Development
uvicorn app:app --reload --port 8000

# Production
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 6.2 Register New User

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "your-test@example.com"}'
```

**Expected Response:**
```json
{
  "message": "Registration successful. Check your email for activation link.",
  "user_id": "123",
  "email": "your-test@example.com",
  "note": "Check your email for the activation link."
}
```

### 6.3 Check Email & Activate

1. Open the activation email
2. Click the activation link
3. Save the API key returned

### 6.4 Get Access Token

```bash
curl -X POST "http://localhost:8000/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YOUR_API_KEY_HERE"}'
```

### 6.5 Test API Key Reset

```bash
curl -X POST "http://localhost:8000/auth/key/reset" \
  -H "Content-Type: application/json" \
  -d '{"email": "your-test@example.com"}'
```

Check email for new API key.

---

## Troubleshooting

### Email Not Sending

**Check 1: Configuration**
```bash
python -c "from email_utils import EmailConfig; print('Configured:', EmailConfig.is_configured())"
```

**Check 2: Logs**
Look for errors in your FastAPI logs:
```
ERROR:__main__:Failed to send activation email to user@example.com: ...
```

**Check 3: Azure AD Permissions**
- Verify Mail.Send permission is granted
- Check admin consent was given
- Review Azure AD logs for errors

**Check 4: Network**
```bash
curl https://graph.microsoft.com/v1.0/ -v
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid client secret` | Wrong secret or expired | Generate new secret in Azure |
| `Insufficient privileges` | Missing permission | Add Mail.Send and grant consent |
| `Mailbox not found` | EMAIL_FROM_ADDRESS doesn't exist | Create mailbox in M365 admin |
| `Access denied` | App not properly configured | Verify all Azure AD steps |

### Getting Help

1. Check application logs: `logger.error` messages
2. Review Azure AD sign-in logs
3. Test with Graph Explorer: https://developer.microsoft.com/graph/graph-explorer
4. Check Microsoft 365 Message Trace

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Client secret is stored securely (not in code)
- [ ] Environment variables are set correctly
- [ ] API_BASE_URL points to production domain
- [ ] Email templates reviewed for branding
- [ ] Test emails sent successfully
- [ ] Monitoring/alerting configured for email failures
- [ ] Backup SMTP configured (optional but recommended)
- [ ] Rate limits appropriate for your volume
- [ ] Logs configured for audit trail

---

## Optional Enhancements

### 1. Custom Email Templates

Edit templates in `email_utils.py`:
- Update branding/colors
- Add company logo
- Customize messaging
- Add legal disclaimers

### 2. Email Queuing (High Volume)

For high-volume systems, consider:
- Celery for background tasks
- RabbitMQ for message queuing
- Retry logic with exponential backoff
- Dead letter queue for failures

### 3. Alternative SMTP Fallback

Add SMTP configuration as backup:
```python
import smtplib
from email.mime.text import MIMEText

def send_via_smtp(to_email, subject, body_html):
    # SMTP fallback if Graph API fails
    pass
```

### 4. Email Analytics

Track email metrics:
- Delivery rate
- Open rate (with tracking pixel)
- Click-through rate
- Bounce rate

### 5. Unsubscribe Mechanism

Add unsubscribe link for compliance:
```python
<a href="{API_BASE_URL}/auth/unsubscribe?email={email}">Unsubscribe</a>
```

---

## Migration from Testing to Production

### Environment Variables

Update `.env` for production:

```bash
# Production values
API_BASE_URL=https://api.yourproductiondomain.com
EMAIL_FROM_ADDRESS=noreply@yourproductiondomain.com

# Keep Azure values the same (unless separate tenant)
MICROSOFT_TENANT_ID=same-as-dev
MICROSOFT_CLIENT_ID=same-as-dev
MICROSOFT_CLIENT_SECRET=same-as-dev
```

### DNS Configuration

Ensure your domain is verified in Microsoft 365:
1. Microsoft 365 Admin Center
2. Settings → Domains
3. Add/verify your domain if needed

---

## Support & Resources

- **Microsoft Graph Docs**: https://docs.microsoft.com/graph
- **Azure Portal**: https://portal.azure.com
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Your Setup Guide**: `MICROSOFT_365_EMAIL_SETUP.md`

---

## Summary

✅ **What You've Accomplished:**
1. Configured Microsoft 365 email sending via Graph API
2. Integrated email functionality into authentication flow
3. Added professional HTML email templates
4. Implemented comprehensive error handling
5. Created testing infrastructure

✅ **What Your System Now Does:**
- Sends activation emails with secure tokens
- Delivers API keys via email
- Sends welcome messages to new users
- Handles API key resets via email
- Gracefully degrades if email is unavailable

✅ **Next Steps:**
- Customize email templates for your branding
- Set up monitoring and alerting
- Review production checklist
- Deploy to production
- Monitor email delivery rates

---

**Need Help?** Review `MICROSOFT_365_EMAIL_SETUP.md` for detailed troubleshooting or run `test_email.py` for diagnostics.
