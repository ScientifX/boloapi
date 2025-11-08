# Email Integration Quick Reference

## 🚀 Setup Commands

```bash
# Install dependencies
pip install requests

# Test configuration
python -c "from email_utils import EmailConfig; print(EmailConfig.is_configured())"

# Run full test suite
python test_email.py your-email@example.com

# Windows automated integration
.\integrate_email.ps1 -ProjectPath "C:\your\project"
```

## 📧 Environment Variables

```bash
# Required in .env file
MICROSOFT_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_SECRET=your~secret~value
EMAIL_FROM_ADDRESS=noreply@yourdomain.com
API_BASE_URL=https://api.yourdomain.com
```

## 🔧 Common Tasks

### Send Test Email
```python
from email_utils import send_activation_email
send_activation_email("test@example.com", "test-token-123")
```

### Check Configuration
```python
from email_utils import EmailConfig
print(f"Configured: {EmailConfig.is_configured()}")
print(f"Missing: {EmailConfig.get_missing_config()}")
```

### Get Access Token Manually
```python
from email_utils import get_email_sender
sender = get_email_sender()
token = sender._get_access_token()
print(token[:20])  # First 20 chars
```

## 🐛 Debug Commands

### Test Graph API Auth
```bash
curl -X POST "https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token" \
  -d "client_id={CLIENT_ID}" \
  -d "client_secret={CLIENT_SECRET}" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials"
```

### Test Registration Flow
```bash
# Register
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Activate (use token from email or response)
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN"

# Get access token
curl -X POST "http://localhost:8000/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YOUR_API_KEY"}'
```

## 🔍 Troubleshooting Quick Checks

```bash
# 1. Check environment variables
cat .env | grep MICROSOFT

# 2. Test Python imports
python -c "import requests; print('requests OK')"
python -c "from email_utils import EmailConfig; print('email_utils OK')"

# 3. Check Azure AD app
# Go to: https://portal.azure.com → Azure Active Directory → App registrations

# 4. Check M365 mailbox
# Go to: https://admin.microsoft.com → Users → Active users

# 5. Run diagnostic test
python test_email.py test@yourdomain.com
```

## 📊 Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Email sent | ✅ Success |
| 401 | Invalid auth | Check tenant/client ID/secret |
| 403 | Insufficient privileges | Add Mail.Send permission |
| 404 | Mailbox not found | Check EMAIL_FROM_ADDRESS |
| 429 | Rate limited | Wait and retry |
| 500 | Server error | Check logs |

## 📝 File Locations

```
your_project/
├── email_utils.py           ← Core email module
├── router_auth.py           ← Updated auth router
├── test_email.py            ← Testing script
├── .env                     ← Configuration (DO NOT COMMIT!)
└── logs/                    ← Check for errors
```

## 🔐 Security Checklist

- [ ] Client secret in environment variables only
- [ ] `.env` in `.gitignore`
- [ ] EMAIL_FROM_ADDRESS mailbox exists in M365
- [ ] Mail.Send permission granted with admin consent
- [ ] API_BASE_URL uses HTTPS in production
- [ ] Rate limits configured appropriately
- [ ] Monitoring/alerting set up

## 📞 Quick Links

| Resource | URL |
|----------|-----|
| Azure Portal | https://portal.azure.com |
| M365 Admin | https://admin.microsoft.com |
| Graph Explorer | https://developer.microsoft.com/graph/graph-explorer |
| Graph Docs | https://docs.microsoft.com/graph |

## 🎯 Common Error Fixes

### "Email not configured"
```bash
# Check .env file
cat .env | grep -E "MICROSOFT|EMAIL"

# Add missing variables
echo "MICROSOFT_TENANT_ID=your-value" >> .env
```

### "Invalid client secret"
```bash
# Generate new secret in Azure Portal
# Update .env with new value
```

### "Mailbox not found"
```bash
# Create mailbox in M365 admin center
# Or change EMAIL_FROM_ADDRESS to existing mailbox
```

### Emails in spam/junk
```bash
# 1. Check SPF/DKIM/DMARC records
# 2. Use Microsoft 365 Message Trace to verify delivery
# 3. Whitelist sender in recipient's email client
```

## ⚡ Performance Tips

```python
# Token is cached automatically for 1 hour
# No need to cache manually

# For high volume, implement:
# 1. Async email sending
# 2. Queue system (Celery)
# 3. Batch operations
# 4. Retry logic with exponential backoff
```

## 🧪 Test Scenarios

```bash
# Test 1: Configuration
python -c "from email_utils import EmailConfig; assert EmailConfig.is_configured()"

# Test 2: Authentication
python -c "from email_utils import get_email_sender; get_email_sender()._get_access_token()"

# Test 3: Send email
python test_email.py your-test@example.com

# Test 4: Full registration flow
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "your-test@example.com"}'
```

## 📦 Backup/Restore

```bash
# Before integration
cp router_auth.py router_auth.py.backup

# Restore if needed
cp router_auth.py.backup router_auth.py

# Check backups
ls -la *.backup
```

## 🔄 Update Process

```bash
# 1. Backup current files
cp email_utils.py email_utils.py.backup
cp router_auth.py router_auth.py.backup

# 2. Copy new versions
cp /path/to/new/email_utils.py .
cp /path/to/new/router_auth_updated.py router_auth.py

# 3. Test
python test_email.py your-test@example.com

# 4. Restart application
# systemctl restart your-api-service
```

## 💡 Pro Tips

1. **Use environment-specific configs**: Different .env for dev/staging/prod
2. **Monitor email delivery rates**: Set up alerts for failures
3. **Implement fallback SMTP**: Backup email method if Graph API unavailable
4. **Cache tokens efficiently**: Current implementation caches for 1 hour automatically
5. **Log everything**: Email attempts, successes, failures for auditing
6. **Test regularly**: Run test_email.py in your CI/CD pipeline

---

**Need more details?** See the full guides:
- `MICROSOFT_365_EMAIL_SETUP.md` - Azure AD setup
- `INTEGRATION_GUIDE.md` - Complete integration walkthrough
- `README.md` - Full documentation
