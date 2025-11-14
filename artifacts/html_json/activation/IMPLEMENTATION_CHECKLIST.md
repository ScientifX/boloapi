# Implementation Checklist

## Step-by-Step Guide to Complete the Integration

### ✅ Step 1: File Replacement
Replace these files in your project with the updated versions:

- [ ] Copy `email_utils.py` to `C:\Clients\SD\boloapi\email_utils.py`
- [ ] Copy `router_auth.py` to `C:\Clients\SD\boloapi\router_auth.py`
- [ ] Your `app.py` has been updated in place (static files mounting added)

### ✅ Step 2: Create Static Directory
Create the static files structure:

- [ ] Create directory: `C:\Clients\SD\boloapi\static\css\`
- [ ] Copy `main.css` to `C:\Clients\SD\boloapi\static\css\main.css`
- [ ] Create directory: `C:\Clients\SD\boloapi\static\images\`
- [ ] Add your logo to `C:\Clients\SD\boloapi\static\images\logo-scientifx.png`

### ✅ Step 3: Verify Template Files
Ensure all template files exist in the correct locations:

#### Base Templates
- [ ] `C:\Clients\SD\boloapi\templates\layouts\base_email.html`
- [ ] `C:\Clients\SD\boloapi\templates\layouts\base_web.html`

#### Components
- [ ] `C:\Clients\SD\boloapi\templates\components\email_header.html`
- [ ] `C:\Clients\SD\boloapi\templates\components\email_footer.html`
- [ ] `C:\Clients\SD\boloapi\templates\components\web_header.html`
- [ ] `C:\Clients\SD\boloapi\templates\components\web_footer.html`

#### Email Templates
- [ ] `C:\Clients\SD\boloapi\templates\emails\activation.html`
- [ ] `C:\Clients\SD\boloapi\templates\emails\api_key_reset.html`
- [ ] `C:\Clients\SD\boloapi\templates\emails\welcome.html`

#### Auth Templates
- [ ] `C:\Clients\SD\boloapi\templates\auth\activate_success.html`
- [ ] `C:\Clients\SD\boloapi\templates\auth\activate_error.html`

#### Other
- [ ] `C:\Clients\SD\boloapi\templates\index.htm`

### ✅ Step 4: Environment Variables
Verify these are set in your `.env` file or Railway:

```env
# Database
API_DB_HOST=your_host
API_DB_PORT=5432
API_DB_DATABASE=your_database
API_DB_USER=your_user
API_DB_PASSWORD=your_password

# JWT
API_JWT_SECRET_KEY=your_secret_key
API_JWT_ALGORITHM=HS256
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Email (Microsoft Graph API)
API_AZURE_CLIENT_ID=your_client_id
API_AZURE_CLIENT_SECRET=your_client_secret
API_AZURE_TENANT_ID=your_tenant_id
API_EMAIL_FROM_ADDRESS=engage@scientifics.io
API_EMAIL_FROM_NAME=BoloAPI

# Application
API_APP_BASE_URL=http://127.0.0.1:8000
API_MAX_DAILY_KEY_RESETS=3
```

- [ ] All database variables set
- [ ] All JWT variables set
- [ ] All email variables set
- [ ] APP_BASE_URL set correctly

### ✅ Step 5: Install Dependencies (if needed)
Make sure you have the required packages:

```bash
pip install fastapi jinja2 python-multipart --break-system-packages
```

- [ ] FastAPI installed
- [ ] Jinja2 installed
- [ ] Python-multipart installed (for form data)

### ✅ Step 6: Test the Implementation

#### Test 1: Static Files
```bash
# Start your server
uvicorn app:app --reload

# Test static files (in another terminal)
curl http://127.0.0.1:8000/static/css/main.css
```
- [ ] Static CSS file accessible
- [ ] No 404 errors

#### Test 2: Email Templates
```bash
# Register a new user
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```
- [ ] Registration successful
- [ ] Activation email received (if email configured)
- [ ] Email uses new template design

#### Test 3: HTML Response (Browser)
Open in browser:
```
http://127.0.0.1:8000/auth/activate?token=YOUR_TOKEN
```
- [ ] HTML page displays correctly
- [ ] CSS styles applied
- [ ] Logo visible (if added)
- [ ] Success message shows API key

#### Test 4: JSON Response (API)
```bash
curl "http://127.0.0.1:8000/auth/activate?token=YOUR_TOKEN" \
  -H "Accept: application/json"
```
- [ ] JSON response returned
- [ ] Contains api_key field
- [ ] No HTML in response

#### Test 5: Error Handling
Test with invalid token:
```
http://127.0.0.1:8000/auth/activate?token=invalid
```
- [ ] Error page displays
- [ ] Helpful error message
- [ ] Guidance provided

### ✅ Step 7: Production Deployment

#### Update Railway Environment Variables
- [ ] All environment variables updated in Railway dashboard
- [ ] APP_BASE_URL set to production URL (e.g., https://yourapp.railway.app)
- [ ] EMAIL_FROM_ADDRESS configured
- [ ] Test email sending in production

#### Verify Static Files in Production
- [ ] Static files accessible at https://yourapp.railway.app/static/css/main.css
- [ ] Images loading correctly
- [ ] CSS styles applied

#### Test Full Flow in Production
- [ ] Register new user
- [ ] Receive activation email
- [ ] Click activation link
- [ ] See success page with branding
- [ ] Receive welcome email

### ✅ Step 8: Customization (Optional)

#### Branding
- [ ] Update logo in `static/images/`
- [ ] Customize CSS colors in `main.css`
- [ ] Update email header text
- [ ] Customize footer links

#### Additional Pages
- [ ] Create login page (templates/auth/login.html)
- [ ] Create dashboard (templates/dashboard.html)
- [ ] Create profile page (templates/auth/profile.html)
- [ ] Create billing page (templates/billing.html)

#### Email Customization
- [ ] Update activation email copy
- [ ] Update welcome email copy
- [ ] Add company logo to emails
- [ ] Test email rendering in multiple clients

### 🎯 Verification Checklist

Run through this complete flow to verify everything works:

1. **Registration**
   - [ ] POST to /auth/register
   - [ ] Receive 201 Created response
   - [ ] Get activation email (or token in response)

2. **Activation (Browser)**
   - [ ] Click activation link in email
   - [ ] See HTML success page
   - [ ] API key displayed prominently
   - [ ] Branding/styles applied
   - [ ] Receive welcome email

3. **Activation (API)**
   - [ ] GET /auth/activate with JSON Accept header
   - [ ] Receive JSON response
   - [ ] api_key field present

4. **Token Generation**
   - [ ] POST to /auth/token with API key
   - [ ] Receive access_token
   - [ ] Token works in protected endpoints

5. **API Key Reset**
   - [ ] POST to /auth/key/reset
   - [ ] Receive new API key
   - [ ] Get reset email
   - [ ] Old key no longer works

### 📝 Common Issues and Solutions

#### Issue: Templates not found
**Solution:**
- Verify templates directory structure matches exactly
- Check templates path in Jinja2Templates()
- Ensure file names are correct (case-sensitive on Linux)

#### Issue: Static files 404
**Solution:**
- Verify static files mounting in app.py
- Check static directory exists
- Confirm files are in correct subdirectories (css/, images/)

#### Issue: Email not using templates
**Solution:**
- Check email_utils.py was replaced
- Verify template files exist in emails/ directory
- Check logs for template rendering errors

#### Issue: Content negotiation not working
**Solution:**
- Verify router_auth.py was replaced
- Check Accept header in request
- Test with curl -H "Accept: application/json"

#### Issue: CSS not applied
**Solution:**
- Verify main.css exists in static/css/
- Check browser developer tools for 404 errors
- Clear browser cache
- Verify StaticFiles mounted in app.py

### 🚀 You're Done!

Once all checkboxes are complete, your implementation is ready for production!

**Next Steps:**
1. Monitor logs for any errors
2. Test with real users
3. Gather feedback on email templates
4. Customize branding as needed
5. Add additional pages (login, dashboard, etc.)

**Reference Documents:**
- `IMPLEMENTATION_SUMMARY.md` - Overview and architecture
- `TEMPLATE_VARIABLES_REFERENCE.md` - All template variables
- `main.css` - Base stylesheet

**Need Help?**
- Check logs for detailed error messages
- Verify all environment variables are set
- Test each component individually
- Review template rendering errors in logs

---

## Quick Test Script

Save this as `test_implementation.py` and run it:

```python
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_static_files():
    """Test static files are accessible"""
    r = requests.get(f"{BASE_URL}/static/css/main.css")
    print(f"Static CSS: {'✅ OK' if r.status_code == 200 else '❌ FAIL'}")

def test_html_response():
    """Test HTML response with invalid token"""
    r = requests.get(
        f"{BASE_URL}/auth/activate?token=invalid",
        headers={"Accept": "text/html"}
    )
    print(f"HTML Error Page: {'✅ OK' if 'html' in r.headers.get('content-type', '') else '❌ FAIL'}")

def test_json_response():
    """Test JSON response with invalid token"""
    r = requests.get(
        f"{BASE_URL}/auth/activate?token=invalid",
        headers={"Accept": "application/json"}
    )
    print(f"JSON Error Response: {'✅ OK' if 'json' in r.headers.get('content-type', '') else '❌ FAIL'}")

def test_registration():
    """Test registration endpoint"""
    r = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": f"test{random.randint(1000,9999)}@example.com"}
    )
    print(f"Registration: {'✅ OK' if r.status_code == 201 else '❌ FAIL'}")

if __name__ == "__main__":
    print("\n🧪 Testing Implementation...\n")
    test_static_files()
    test_html_response()
    test_json_response()
    test_registration()
    print("\n✨ Tests complete!\n")
```

Run with: `python test_implementation.py`
