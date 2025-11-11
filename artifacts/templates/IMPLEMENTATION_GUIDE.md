# Jinja2 Template Refactor - Implementation Guide

## Overview
This refactor converts all HTML output to use Jinja2 templates with a reusable structure. The system now supports both HTML and JSON responses through content negotiation.

## What's New

### 1. File Structure
```
/static/
  /css/
    main.css              # Main stylesheet (scientifics.io branding)
  /images/
    logo.png             # PUT YOUR LOGO HERE!

/templates/
  /layouts/
    base_email.html       # Base for all emails (inline styles)
    base_web.html         # Base for web pages (uses main.css)
    
  /emails/
    activation.html       # Account activation email
    welcome.html          # Welcome email with API key
    api_key_reset.html    # API key reset email
    
  /auth/
    activate_success.html # Activation success page
    activate_error.html   # Activation error page
```

### 2. Brand Colors (from your logo)
- **Primary Navy:** #3d4461
- **Primary Navy Light:** #5b6a9b  
- **Primary Navy Dark:** #2a2f42
- **Success Green:** #28a745
- **Error Red:** #dc3545
- **Warning Yellow:** #ffc107
- **Info Blue:** #17a2b8

### 3. New/Updated Files

#### New Files:
1. **static/css/main.css** - Main stylesheet for all web pages
2. **templates/** - All template files (see structure above)
3. **content_negotiation.py** - Helper for HTML/JSON content negotiation
4. **email_utils.py** (updated) - Now uses Jinja2 templates instead of HTML strings

#### Updated Files:
1. **app.py** - Added static file mounting

## Installation Steps

### Step 1: Copy Files
```bash
# Copy all files to your project root
cp -r templates /path/to/your/project/
cp -r static /path/to/your/project/
cp email_utils.py /path/to/your/project/
cp content_negotiation.py /path/to/your/project/
```

### Step 2: Add Your Logo
```bash
# Place your logo file at:
/path/to/your/project/static/images/logo.png

# Logo should be PNG format, approximately 200-300px wide, 50-80px height
```

### Step 3: Update app.py
Add static file mounting (if not already done):
```python
from fastapi.staticfiles import StaticFiles

app = FastAPI(...)
app.mount("/static", StaticFiles(directory="static"), name="static")
```

## How It Works

### Email Templates
Emails always render HTML from Jinja2 templates with inline styles (email-client safe).

### Web Endpoints  
Check `Accept` header to return HTML or JSON:
- `Accept: text/html` → HTML page
- `Accept: application/json` → JSON response
- Default → HTML (for browser visits)

### Example Usage
```python
from content_negotiation import wants_json
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

@router.get("/activate")
async def activate(request: Request, token: str):
    # ... business logic ...
    
    if wants_json(request):
        return {"message": "Success", "api_key": api_key}
    else:
        return templates.TemplateResponse(
            "auth/activate_success.html",
            {"request": request, "api_key": api_key}
        )
```

## Testing

### Test Emails
```bash
python test_email.py your@email.com
```

### Test Web Pages
```bash
# Start server
uvicorn app:app --reload

# Visit in browser
http://localhost:8000/auth/activate?token=test

# Or test with curl
curl http://localhost:8000/auth/activate?token=test
curl -H "Accept: application/json" http://localhost:8000/auth/activate?token=test
```

## Next Steps

The foundation is ready for building:
- Login pages
- User dashboards
- Profile pages
- Billing/subscription pages

All using the same base templates and branding!

## Troubleshooting

**Logo not showing:** Check `/static/images/logo.png` exists
**Styles not loading:** Verify `app.mount("/static", ...)` in app.py
**Templates not found:** Check `/templates/` directory at project root

## Files Provided

All files are in the download - copy them to your project:
- `/templates/` folder (all template files)
- `/static/` folder (CSS and images placeholder)
- `email_utils.py` (updated version)
- `content_negotiation.py` (new helper)
- Updated `app.py` snippet

Ready to go! 🚀
