# 📋 Email Integration Checklist

Track your progress through the email integration process.

---

## Phase 1: Azure AD Setup

**Estimated Time:** 20-30 minutes

### Azure Portal Configuration
- [ ] Logged into Azure Portal (https://portal.azure.com)
- [ ] Navigated to Azure Active Directory
- [ ] Clicked "App registrations" → "New registration"
- [ ] Named app: `FBI-API-Email-Service` (or your choice)
- [ ] Selected "Accounts in this organizational directory only"
- [ ] Clicked "Register"

### Collect Application IDs
- [ ] Copied **Application (client) ID**
- [ ] Copied **Directory (tenant) ID**
- [ ] Saved both IDs securely

### Create Client Secret
- [ ] Navigated to "Certificates & secrets"
- [ ] Clicked "New client secret"
- [ ] Entered description: `FBI-API-Production`
- [ ] Selected expiration period
- [ ] Clicked "Add"
- [ ] **IMMEDIATELY** copied the "Value" (cannot view again!)
- [ ] Saved client secret securely

### Configure Permissions
- [ ] Navigated to "API permissions"
- [ ] Clicked "Add a permission"
- [ ] Selected "Microsoft Graph"
- [ ] Chose "Application permissions"
- [ ] Searched for and selected `Mail.Send`
- [ ] Clicked "Add permissions"
- [ ] Clicked "Grant admin consent for [Organization]"
- [ ] Confirmed consent
- [ ] Verified green checkmarks appear

---

## Phase 2: Local Environment Setup

**Estimated Time:** 5 minutes

### Install Dependencies
- [ ] Opened terminal/PowerShell
- [ ] Ran: `pip install requests`
- [ ] Verified installation succeeded

### Copy Files
- [ ] Copied `email_utils.py` to project directory
- [ ] Located project's `router_auth.py` file
- [ ] Created backup: `router_auth.py.backup`

### Environment Configuration
- [ ] Located/created `.env` file in project root
- [ ] Added `MICROSOFT_TENANT_ID=` with value from Azure
- [ ] Added `MICROSOFT_CLIENT_ID=` with value from Azure
- [ ] Added `MICROSOFT_CLIENT_SECRET=` with value from Azure
- [ ] Added `EMAIL_FROM_ADDRESS=` (e.g., noreply@yourdomain.com)
- [ ] Added `API_BASE_URL=` (your API URL)
- [ ] Verified `.env` is in `.gitignore`

### Create/Verify Email Mailbox
- [ ] Logged into Microsoft 365 Admin Center
- [ ] Navigated to Users → Active Users
- [ ] Verified mailbox exists for `EMAIL_FROM_ADDRESS`
- [ ] Or created new mailbox if needed

---

## Phase 3: Integration

**Estimated Time:** 10 minutes

### Option A: Automated (Windows)
- [ ] Ran: `.\integrate_email.ps1 -ProjectPath "C:\your\project"`
- [ ] Reviewed integration output
- [ ] Verified no errors

### Option B: Manual Integration
- [ ] Backed up current `router_auth.py`
- [ ] Copied `router_auth_updated.py` to `router_auth.py`
- [ ] Or manually integrated email calls (see INTEGRATION_GUIDE.md)
- [ ] Verified imports added correctly
- [ ] Verified email calls added at 3 locations:
  - [ ] Registration endpoint
  - [ ] Activation endpoint  
  - [ ] Key reset endpoint

---

## Phase 4: Testing

**Estimated Time:** 10 minutes

### Configuration Test
- [ ] Ran: `python -c "from email_utils import EmailConfig; print(EmailConfig.is_configured())"`
- [ ] Result: `True`

### Comprehensive Test Suite
- [ ] Ran: `python test_email.py your-test@example.com`
- [ ] Configuration test: ✅ PASS
- [ ] Authentication test: ✅ PASS
- [ ] Activation email test: ✅ PASS
- [ ] API key email test: ✅ PASS
- [ ] Welcome email test: ✅ PASS

### Email Verification
- [ ] Checked inbox/spam for test emails
- [ ] Verified activation email received
- [ ] Verified HTML formatting looks correct
- [ ] Verified links are clickable
- [ ] Verified API key email received
- [ ] Verified welcome email received

### Integration Test
- [ ] Started FastAPI app: `uvicorn app:app --reload`
- [ ] Registered test user: `POST /auth/register`
- [ ] Received success response
- [ ] Email arrived in inbox
- [ ] Clicked activation link
- [ ] Received API key in response
- [ ] Received welcome email with API key copy
- [ ] Successfully got JWT token: `POST /auth/token`

---

## Phase 5: Production Deployment

**Estimated Time:** 15 minutes

### Pre-Deployment Verification
- [ ] All tests passing in production environment
- [ ] Environment variables set correctly on production server
- [ ] API_BASE_URL points to production domain
- [ ] EMAIL_FROM_ADDRESS verified in M365
- [ ] HTTPS enabled on production API
- [ ] Rate limits configured appropriately

### Security Checklist
- [ ] Client secret stored in secure location (not in code)
- [ ] `.env` file not committed to version control
- [ ] `.env` in `.gitignore` confirmed
- [ ] Production environment variables encrypted/secured
- [ ] MFA enabled on Azure AD account
- [ ] MFA enabled on M365 service account

### Deployment
- [ ] Deployed updated code to production
- [ ] Restarted application
- [ ] Verified application starts successfully
- [ ] Checked logs for errors

### Production Testing
- [ ] Registered test user in production
- [ ] Verified email delivered
- [ ] Activated account via email link
- [ ] Verified welcome email received
- [ ] Tested API key reset
- [ ] Verified reset email received
- [ ] Confirmed all workflows working

### Monitoring Setup
- [ ] Configured logging for email operations
- [ ] Set up alerts for email failures
- [ ] Set up monitoring for Graph API errors
- [ ] Documented monitoring procedures
- [ ] Created runbook for common issues

---

## Phase 6: Documentation & Handoff

**Estimated Time:** 10 minutes

### Team Documentation
- [ ] Documented Azure AD app location and credentials
- [ ] Created access procedures for Azure Portal
- [ ] Documented email system architecture
- [ ] Created troubleshooting guide
- [ ] Documented emergency procedures
- [ ] Shared `QUICK_REFERENCE.md` with team

### Knowledge Transfer
- [ ] Trained team on email system
- [ ] Reviewed troubleshooting procedures
- [ ] Explained monitoring and alerts
- [ ] Documented escalation procedures
- [ ] Reviewed Azure AD access requirements

---

## Phase 7: Post-Deployment

**Estimated Time:** Ongoing

### Week 1 Monitoring
- [ ] Checked email delivery success rate daily
- [ ] Reviewed error logs daily
- [ ] Monitored Graph API response times
- [ ] Verified no rate limit issues
- [ ] Collected user feedback

### Week 2-4 Monitoring
- [ ] Reviewed weekly email metrics
- [ ] Checked for any authentication issues
- [ ] Monitored token cache performance
- [ ] Reviewed any support tickets
- [ ] Optimized based on metrics

### Ongoing Maintenance
- [ ] Scheduled client secret rotation (before expiration)
- [ ] Regular review of Azure AD logs
- [ ] Periodic testing of email functionality
- [ ] Keep documentation updated
- [ ] Monitor Microsoft Graph API changes

---

## Optional Enhancements

### Customization
- [ ] Customized email templates with branding
- [ ] Added company logo to emails
- [ ] Updated color scheme
- [ ] Added custom footer/legal text
- [ ] Implemented unsubscribe mechanism (if needed)

### Advanced Features
- [ ] Implemented email queuing for high volume
- [ ] Added retry logic with exponential backoff
- [ ] Set up SMTP fallback
- [ ] Implemented email analytics
- [ ] Added email preview testing

### Production Hardening
- [ ] Implemented rate limiting on email sends
- [ ] Added circuit breaker pattern
- [ ] Set up dead letter queue
- [ ] Implemented email batching
- [ ] Added comprehensive metrics collection

---

## Troubleshooting Record

Use this section to track any issues encountered:

### Issue 1:
- **Date:** _______________
- **Problem:** _______________
- **Solution:** _______________
- **Reference:** _______________

### Issue 2:
- **Date:** _______________
- **Problem:** _______________
- **Solution:** _______________
- **Reference:** _______________

### Issue 3:
- **Date:** _______________
- **Problem:** _______________
- **Solution:** _______________
- **Reference:** _______________

---

## Final Verification

### All Systems Go! ✅

- [ ] **Azure AD configured** with proper permissions
- [ ] **Local testing** completed successfully
- [ ] **Production deployment** completed
- [ ] **Email delivery** verified in production
- [ ] **Monitoring** set up and working
- [ ] **Documentation** complete
- [ ] **Team trained** on system
- [ ] **Backup procedures** in place

---

## Success Metrics

Track these metrics after deployment:

- **Email Delivery Rate:** _____%
- **Average Delivery Time:** _____ seconds
- **User Feedback:** _____/5 stars
- **System Uptime:** _____%
- **Zero-Error Days:** _____ days

---

## 🎉 Congratulations!

You've successfully integrated Microsoft 365 email into your FBI Wanted API!

**Date Completed:** _______________
**Completed By:** _______________
**Total Time:** _______________

---

**Next Steps:**
1. Monitor for 1 week
2. Collect feedback
3. Optimize as needed
4. Document lessons learned

**Questions?** Refer to:
- `QUICK_REFERENCE.md` for commands
- `MICROSOFT_365_EMAIL_SETUP.md` for Azure issues
- `INTEGRATION_GUIDE.md` for integration help
