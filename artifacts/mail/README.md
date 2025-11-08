# FBI Wanted API - Email Integration Package

Complete Microsoft 365 email integration for your FastAPI authentication system.

## 📦 What's Included

| File | Description |
|------|-------------|
| **email_utils.py** | Core email functionality using Microsoft Graph API |
| **router_auth_updated.py** | Updated authentication router with email integration |
| **test_email.py** | Comprehensive testing script |
| **integrate_email.ps1** | Automated integration helper (Windows PowerShell) |
| **INTEGRATION_GUIDE.md** | Step-by-step integration instructions |
| **MICROSOFT_365_EMAIL_SETUP.md** | Detailed Azure AD setup guide |
| **env.example** | Environment variable template |
| **requirements_email.txt** | Python dependencies |

## 🚀 Quick Start

### 1. Azure AD Setup (20-30 minutes)
Follow `MICROSOFT_365_EMAIL_SETUP.md` to:
- Register app in Azure AD
- Create client secret
- Configure Mail.Send permission
- Grant admin consent

### 2. Configure Environment Variables
Copy values from Azure AD to your `.env` file:

```bash
MICROSOFT_TENANT_ID=your-tenant-id
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret
EMAIL_FROM_ADDRESS=noreply@yourdomain.com
API_BASE_URL=https://api.yourdomain.com
```

### 3. Install Dependencies
```bash
pip install requests
```

### 4. Integration

**Windows (Automated):**
```powershell
.\integrate_email.ps1 -ProjectPath "C:\path\to\your\project"
```

**Manual (All Platforms):**
1. Copy `email_utils.py` to your project
2. Replace `router_auth.py` with `router_auth_updated.py` (or merge manually)
3. See `INTEGRATION_GUIDE.md` for detailed steps

### 5. Test
```bash
python test_email.py your-email@example.com
```

## ✨ Features

### Professional HTML Email Templates
- **Activation Email**: Secure token-based account activation
- **Welcome Email**: API key delivery with quick start guide
- **Key Reset Email**: Secure API key replacement

### Robust Implementation
- ✅ OAuth2 authentication with Microsoft Graph API
- ✅ Token caching for performance
- ✅ Comprehensive error handling
- ✅ Graceful degradation (works without email)
- ✅ Production-ready logging
- ✅ Security best practices

### Testing Infrastructure
- ✅ Configuration validation
- ✅ Authentication testing
- ✅ Email delivery testing
- ✅ Detailed diagnostics

## 📚 Documentation

### For First-Time Setup
1. **Start here:** `MICROSOFT_365_EMAIL_SETUP.md`
2. **Then:** `INTEGRATION_GUIDE.md`
3. **Finally:** Test with `test_email.py`

### For Troubleshooting
- Check logs in your FastAPI application
- Review Azure AD sign-in logs
- Run `test_email.py` for diagnostics
- See troubleshooting sections in guides

## 🔧 Architecture

### How It Works

```
User Registration Flow:
1. POST /auth/register → Creates user
2. send_activation_email() → Sends email via Graph API
3. User clicks link → GET /auth/activate
4. Account activated → send_welcome_email()
5. User receives API key → Ready to use

API Key Reset Flow:
1. POST /auth/key/reset → Generates new key
2. send_api_key_email() → Delivers via email
3. Old key invalidated
4. User uses new key
```

### Microsoft Graph API Integration

```python
# Authentication (OAuth2 Client Credentials)
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
  → Access Token (cached for 1 hour)

# Send Email
POST https://graph.microsoft.com/v1.0/users/{from}/sendMail
  Authorization: Bearer {access_token}
  → Email delivered
```

## 🔒 Security Features

- **Client Credentials Flow**: Service-to-service authentication
- **Token Caching**: Reduces API calls, improves performance
- **Secure Secret Storage**: Environment variables only
- **HTTPS Only**: All Graph API calls over TLS
- **No Password Storage**: API keys are bcrypt hashed
- **Rate Limiting**: Built into FastAPI endpoints

## 📊 Email Templates

All templates are professionally designed with:
- Responsive HTML/CSS
- Clear call-to-action buttons
- Security warnings where appropriate
- Code examples for developers
- Mobile-friendly design

### Customization

Edit templates in `email_utils.py`:

```python
def send_activation_email(to_email: str, activation_token: str) -> bool:
    subject = "Activate Your Account"  # ← Customize
    html_body = f"""
        <!-- Your custom HTML here -->
    """
```

## 🧪 Testing

### Test Configuration
```bash
python -c "from email_utils import EmailConfig; print('OK' if EmailConfig.is_configured() else 'Missing config')"
```

### Test Authentication
```bash
python -c "from email_utils import get_email_sender; s = get_email_sender(); print('Token:', s._get_access_token()[:20])"
```

### Full Test Suite
```bash
python test_email.py your-email@example.com
```

Expected: All 5 tests pass (Configuration, Authentication, 3 email types)

## 🚨 Troubleshooting

### Common Issues

**"Email not configured"**
- Missing environment variables
- Check: `EmailConfig.is_configured()`
- Solution: Add all required vars to `.env`

**"Invalid client secret"**
- Wrong secret or expired
- Solution: Generate new secret in Azure Portal

**"Insufficient privileges"**
- Missing Mail.Send permission
- Solution: Add permission and grant admin consent

**"Mailbox not found"**
- EMAIL_FROM_ADDRESS doesn't exist
- Solution: Create mailbox in Microsoft 365 admin center

**Emails not arriving**
- Check spam/junk folders
- Verify email address
- Check Microsoft 365 Message Trace
- Review sent items

## 📈 Production Considerations

### Before Deploying
- [ ] Client secret stored securely (Azure Key Vault recommended)
- [ ] API_BASE_URL points to production domain
- [ ] Email templates reviewed and branded
- [ ] Test emails sent successfully
- [ ] Monitoring configured for failures
- [ ] Rate limits appropriate
- [ ] Logs configured

### Monitoring
Monitor these metrics:
- Email delivery success rate
- Graph API authentication failures
- Token refresh frequency
- Rate limit hits
- Error rates by endpoint

### Scaling
For high volume:
- Consider async email sending
- Implement queue system (Celery + Redis)
- Add retry logic with exponential backoff
- Monitor Graph API throttling limits

## 💰 Costs

- **Microsoft 365**: No additional cost for Graph API with existing subscription
- **Azure AD**: Free for basic app registration
- **Rate Limits**: Subject to Microsoft's service limits

## 🔗 Resources

- [Microsoft Graph API Documentation](https://docs.microsoft.com/graph)
- [Azure Portal](https://portal.azure.com)
- [Microsoft 365 Admin Center](https://admin.microsoft.com)
- [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)

## 🤝 Support

### Getting Help
1. Review documentation in `INTEGRATION_GUIDE.md`
2. Run diagnostics with `test_email.py`
3. Check Azure AD logs for authentication issues
4. Review FastAPI application logs for errors

### Common Questions

**Q: Can I use a different email provider?**
A: Yes, but you'll need to modify `email_utils.py`. The Graph API code can be replaced with SMTP, SendGrid, AWS SES, etc.

**Q: Do I need different Azure apps for dev/prod?**
A: Optional but recommended for security. Use same tenant but different client IDs/secrets.

**Q: What happens if email fails?**
A: The system gracefully degrades. Registration succeeds but activation token is shown in response (for development). In production, implement proper error handling.

**Q: Can I customize the email templates?**
A: Absolutely! Edit the HTML in `email_utils.py` functions.

**Q: Is this production-ready?**
A: Yes. Includes proper error handling, logging, token caching, and security best practices.

## 📝 Version History

### v1.0.0 (Current)
- ✅ Microsoft Graph API integration
- ✅ Three email types (activation, welcome, key reset)
- ✅ Professional HTML templates
- ✅ Comprehensive testing suite
- ✅ Complete documentation
- ✅ Windows integration helper

## 📄 License

This email integration package is provided as part of the FBI Wanted API project.

---

## 🎯 Next Steps

1. **Complete Azure AD setup** → `MICROSOFT_365_EMAIL_SETUP.md`
2. **Integrate into your project** → `INTEGRATION_GUIDE.md`
3. **Test thoroughly** → `python test_email.py`
4. **Customize templates** → Edit `email_utils.py`
5. **Deploy to production** → Follow production checklist

---

**Questions?** Check the comprehensive guides included in this package!

**Ready to get started?** Open `MICROSOFT_365_EMAIL_SETUP.md` first! 🚀
