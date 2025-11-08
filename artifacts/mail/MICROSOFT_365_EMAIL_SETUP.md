# Microsoft 365 Email Setup Guide

This guide walks you through setting up Microsoft Graph API for sending emails from your FastAPI application using your Microsoft 365-hosted domain.

## Prerequisites

- Microsoft 365 subscription with your domain
- Access to Azure Portal (admin privileges)
- Python 3.8+
- Required packages: `requests`, `msal` (optional, for alternative auth)

## Step 1: Register Application in Azure AD

1. **Go to Azure Portal**
   - Navigate to https://portal.azure.com
   - Sign in with your Microsoft 365 admin account

2. **Register New Application**
   - Go to "Azure Active Directory" → "App registrations"
   - Click "New registration"
   - Enter details:
     - **Name**: `FBI-API-Email-Service` (or any descriptive name)
     - **Supported account types**: "Accounts in this organizational directory only"
     - **Redirect URI**: Leave blank (not needed for daemon/service apps)
   - Click "Register"

3. **Note Your IDs**
   - After registration, you'll see the Overview page
   - Copy and save these values:
     - **Application (client) ID** → This is your `MICROSOFT_CLIENT_ID`
     - **Directory (tenant) ID** → This is your `MICROSOFT_TENANT_ID`

## Step 2: Create Client Secret

1. **Generate Secret**
   - In your app registration, go to "Certificates & secrets"
   - Click "New client secret"
   - Enter a description: `FBI-API-Production`
   - Choose expiration period (recommend "24 months" or "Custom" for production)
   - Click "Add"

2. **Save the Secret**
   - **IMPORTANT**: Copy the "Value" immediately (not the "Secret ID")
   - This is your `MICROSOFT_CLIENT_SECRET`
   - **You cannot view this again** after leaving the page!
   - Store it securely (password manager, Azure Key Vault, etc.)

## Step 3: Configure API Permissions

1. **Add Mail.Send Permission**
   - Go to "API permissions"
   - Click "Add a permission"
   - Select "Microsoft Graph"
   - Choose "Application permissions" (not Delegated)
   - Search for and select: `Mail.Send`
   - Click "Add permissions"

2. **Grant Admin Consent**
   - Click "Grant admin consent for [Your Organization]"
   - Confirm the action
   - Status should show green checkmarks

**Why Application permissions?**
- Your app sends emails without user interaction
- Works as a daemon/service (no user sign-in required)
- More secure for automated systems

## Step 4: Configure Environment Variables

1. **Create `.env` file** in your project root (copy from `.env.example`):

```bash
# Email Configuration
MICROSOFT_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_CLIENT_SECRET=your~secret~value~here
EMAIL_FROM_ADDRESS=noreply@yourdomain.com
API_BASE_URL=https://api.yourdomain.com
```

2. **Set Email From Address**
   - Use a mailbox that exists in your Microsoft 365 tenant
   - Common options:
     - `noreply@yourdomain.com`
     - `api@yourdomain.com`
     - `notifications@yourdomain.com`
   - Create the mailbox in Microsoft 365 admin center if it doesn't exist

## Step 5: Install Required Python Package

```bash
pip install requests
# Optionally, for more advanced scenarios:
pip install msal
```

## Step 6: Test Email Configuration

Create a test script to verify your setup:

```python
# test_email.py
from email_utils import send_activation_email, EmailConfig

# Check configuration
if not EmailConfig.is_configured():
    missing = EmailConfig.get_missing_config()
    print(f"❌ Missing configuration: {', '.join(missing)}")
    exit(1)

print("✅ Email configuration loaded")
print(f"   Tenant ID: {EmailConfig.TENANT_ID[:8]}...")
print(f"   From: {EmailConfig.FROM_ADDRESS}")

# Send test email
test_email = "your-test-email@example.com"
test_token = "test-activation-token-12345"

print(f"\nSending test email to {test_email}...")
success = send_activation_email(test_email, test_token)

if success:
    print("✅ Email sent successfully!")
else:
    print("❌ Email failed to send. Check logs for details.")
```

Run the test:
```bash
python test_email.py
```

## Step 7: Update Authentication Router

The email functions are already integrated into your authentication router. The system will automatically:

1. **Registration** (`/auth/register`):
   - Send activation email with secure token
   - Token expires in 48 hours

2. **Activation** (`/auth/activate`):
   - User clicks link from email
   - Account activated, API key generated
   - Welcome email sent with API key

3. **Key Reset** (`/auth/key/reset`):
   - Generate new API key
   - Invalidate old key
   - Send email with new key

## Security Best Practices

### 1. Client Secret Management
- **Never commit secrets to Git**
- Use environment variables
- Consider Azure Key Vault for production
- Rotate secrets periodically (before expiration)

### 2. Mailbox Security
- Use a dedicated service account (not personal)
- Enable MFA on the mailbox
- Monitor sent items for unauthorized use
- Set up alerts for unusual activity

### 3. API Permissions
- Use least privilege principle
- Only `Mail.Send` is needed (not Mail.Read)
- Regularly review app permissions
- Audit access logs

### 4. Rate Limiting
- Microsoft Graph has rate limits
- Current implementation caches tokens
- Monitor for 429 (Too Many Requests) errors
- Implement exponential backoff if needed

## Troubleshooting

### Error: "Invalid client secret"
- Client secret expired or wrong value
- Generate new secret in Azure Portal
- Update `.env` file

### Error: "Insufficient privileges"
- Admin consent not granted
- Grant consent in Azure Portal → API permissions

### Error: "Mailbox not found"
- `EMAIL_FROM_ADDRESS` doesn't exist in your tenant
- Create the mailbox or use existing one
- Verify spelling/domain

### Error: "Access denied"
- App doesn't have Mail.Send permission
- Check API permissions in Azure Portal
- Ensure admin consent was granted

### Emails Not Arriving
- Check spam/junk folders
- Verify email address is correct
- Check Microsoft 365 admin center → Message trace
- Review sent items in the service account

### Authentication Token Issues
- Token cache works for 1 hour
- Automatic renewal implemented
- Check network connectivity
- Verify tenant ID is correct

## Alternative: Using MSAL Library

If you prefer Microsoft's official library:

```python
from msal import ConfidentialClientApplication

app = ConfidentialClientApplication(
    client_id=EmailConfig.CLIENT_ID,
    client_credential=EmailConfig.CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{EmailConfig.TENANT_ID}"
)

result = app.acquire_token_for_client(
    scopes=["https://graph.microsoft.com/.default"]
)
access_token = result["access_token"]
```

The current implementation uses `requests` for simplicity and fewer dependencies.

## Production Considerations

1. **Monitoring**
   - Log all email attempts
   - Set up alerts for failures
   - Monitor Graph API usage

2. **Failover**
   - Consider backup SMTP as fallback
   - Implement retry logic
   - Queue failed emails

3. **Compliance**
   - Include unsubscribe mechanism (if applicable)
   - GDPR compliance for EU users
   - Store email logs as required

4. **Performance**
   - Token caching reduces API calls
   - Consider async implementation for high volume
   - Batch operations if needed

## Cost Considerations

- Microsoft Graph API is included with Microsoft 365 licenses
- No additional cost for reasonable usage
- Subject to service limits and throttling

## Support Resources

- **Microsoft Graph Documentation**: https://docs.microsoft.com/graph
- **Azure Portal**: https://portal.azure.com
- **Microsoft 365 Admin Center**: https://admin.microsoft.com
- **Graph Explorer** (testing): https://developer.microsoft.com/graph/graph-explorer

## Next Steps

1. ✅ Complete Azure AD setup
2. ✅ Configure environment variables
3. ✅ Test email sending
4. ✅ Update authentication router
5. ✅ Deploy to production
6. Monitor and maintain

---

**Need Help?** Check the troubleshooting section or review Microsoft's Graph API documentation.
