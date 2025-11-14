# Content Negotiation Implementation - Complete

## Summary

I've completed the functionality to integrate Jinja2 templates with content negotiation for your FastAPI application. The system now properly returns HTML for browser requests and JSON for API requests.

## What Was Changed

### 1. **email_utils.py** - Template Integration
**Changes:**
- Removed hardcoded HTML strings
- Added Jinja2Templates initialization
- Updated EmailConfig to use environment variables from config.py
- Converted all email functions to use templates:
  - `send_activation_email()` → uses `emails/activation.html`
  - `send_api_key_email()` → uses `emails/api_key_reset.html`
  - `send_welcome_email()` → uses `emails/welcome.html`

**Template Context Variables:**
- `activation_link` - Full URL to activation endpoint
- `api_key` - User's API key
- `app_base_url` - Base URL from config
- `header_title` - Custom header for each email type
- `year` - Current year for footer

### 2. **router_auth.py** - Content Negotiation
**Changes:**
- Added `response_utils` imports for content negotiation
- Updated `/activate` endpoint to return HTML or JSON based on Accept header
- Uses `render_or_json()` for success responses
- Uses `render_error()` for error responses
- Proper HTTP status codes for all scenarios

**How Content Negotiation Works:**
- **Browser Request** (Accept: text/html): Returns HTML page from templates/auth/
- **API Request** (Accept: application/json): Returns JSON response
- Default behavior: HTML for unknown/browser clients

**Templates Used:**
- Success: `auth/activate_success.html`
- Error: `auth/activate_error.html`

### 3. **app.py** - Static Files Support
**Changes:**
- Added `StaticFiles` import
- Mounted `/static` directory for CSS, images, and JavaScript
- Enables templates to reference `{{ url_for('static', path='/css/main.css') }}`

## Directory Structure Required

```
C:\Clients\SD\boloapi\
├── templates/
│   ├── layouts/
│   │   ├── base_email.html     # Base template for emails
│   │   └── base_web.html       # Base template for web pages
│   ├── components/
│   │   ├── email_header.html   # Reusable email header
│   │   ├── email_footer.html   # Reusable email footer
│   │   ├── web_header.html     # Reusable web header
│   │   └── web_footer.html     # Reusable web footer
│   ├── emails/
│   │   ├── activation.html     # Activation email
│   │   ├── api_key_reset.html  # API key reset email
│   │   └── welcome.html        # Welcome email
│   ├── auth/
│   │   ├── activate_success.html  # Success page
│   │   └── activate_error.html    # Error page
│   └── index.htm               # Homepage
└── static/
    ├── css/
    │   └── main.css
    ├── images/
    │   └── logo-scientifx.png
    └── js/
        └── (your JS files)
```

## Testing the Implementation

### 1. Test Email Templates
```bash
# Register a new user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Check your email for the activation link with new template
```

### 2. Test Content Negotiation - Browser
```bash
# Open in browser (will return HTML)
http://localhost:8000/auth/activate?token=YOUR_TOKEN
```

### 3. Test Content Negotiation - API
```bash
# Request with JSON accept header (will return JSON)
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### 4. Test Static Files
```bash
# Verify static files are accessible
curl http://localhost:8000/static/css/main.css
```

## How Content Negotiation Works

The `response_utils.py` module provides two key functions:

### `wants_json(request)`
Determines client preference based on Accept header:
- Returns `True` if client prefers JSON
- Returns `False` if client prefers HTML (default for browsers)

### `render_or_json(request, template_name, context, json_data)`
Returns appropriate response type:
- **HTML**: Uses Jinja2 to render template with context
- **JSON**: Returns JSONResponse with json_data

### `render_error(request, template_name, error_message, error_type, context)`
Handles error responses with content negotiation:
- **HTML**: Renders error template with friendly message
- **JSON**: Returns structured error response

## Environment Variables Required

Make sure these are set in your `.env` file or Railway environment:

```env
# Email Configuration
API_AZURE_CLIENT_ID=your_client_id
API_AZURE_CLIENT_SECRET=your_client_secret
API_AZURE_TENANT_ID=your_tenant_id
API_EMAIL_FROM_ADDRESS=engage@scientifics.io
API_EMAIL_FROM_NAME=BoloAPI

# App Configuration
API_APP_BASE_URL=http://127.0.0.1:8000  # or your production URL
```

## Benefits of This Implementation

1. **Separation of Concerns**: Templates are separate from business logic
2. **Reusability**: Components (header/footer) are reused across templates
3. **Maintainability**: Update email design without changing Python code
4. **Content Negotiation**: Same endpoint serves both web browsers and API clients
5. **Professional UX**: HTML pages for browser users, JSON for programmatic access
6. **Branding Consistency**: Centralized styling through templates

## Next Steps

1. **Create CSS File**: Add `static/css/main.css` with your brand styling
2. **Customize Templates**: Update templates with your branding and copy
3. **Test Email Rendering**: Send test emails to verify formatting
4. **Add More Web Pages**: Create login, dashboard, billing pages using same pattern
5. **Implement Authentication UI**: Build full web interface for user management

## Example: Adding a New Endpoint with Content Negotiation

```python
from response_utils import render_or_json, render_error

@router.get("/profile")
async def get_profile(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        # Your business logic here
        user_data = get_user_profile(current_user["user_id"])
        
        # Prepare response
        return render_or_json(
            request=request,
            template_name="auth/profile.html",
            context={"request": request, "user": user_data},
            json_data={"user": user_data}
        )
    except Exception as e:
        return render_error(
            request=request,
            template_name="auth/error.html",
            error_message=str(e),
            error_type="Profile Error",
            status_code=500
        )
```

## Files Delivered

1. **email_utils.py** - Updated with template support
2. **router_auth.py** - Updated with content negotiation
3. **app.py** - Updated with static files mounting (in place)
4. **IMPLEMENTATION_SUMMARY.md** - This file

## Need Help?

If you encounter any issues:
1. Check that all template files exist in the correct directories
2. Verify static files are accessible at /static/
3. Ensure environment variables are properly set
4. Check logs for template rendering errors
5. Test content negotiation with curl -H "Accept: application/json"

Your implementation is now complete and production-ready! 🚀
