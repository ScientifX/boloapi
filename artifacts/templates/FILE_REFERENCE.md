# Complete File Reference

## 📁 Project Structure Overview

```
/mnt/project/
│
├── 🎨 STATIC FILES (CSS, Images, JS)
│   └── static/
│       ├── css/
│       │   └── main.css                   # Main stylesheet with brand colors
│       └── images/
│           └── logo.png                    # 👈 PUT YOUR LOGO HERE
│
├── 📄 TEMPLATES (Jinja2 HTML)
│   └── templates/
│       ├── layouts/
│       │   ├── base_email.html            # Base for all emails
│       │   └── base_web.html              # Base for all web pages
│       │
│       ├── emails/
│       │   ├── activation.html            # Account activation email
│       │   ├── welcome.html               # Welcome email with API key
│       │   └── api_key_reset.html         # API key reset email
│       │
│       └── auth/
│           ├── activate_success.html      # Activation success page
│           └── activate_error.html        # Activation error page
│
├── 🐍 PYTHON MODULES
│   ├── app.py                             # Main FastAPI app
│   ├── email_utils.py                     # ✅ UPDATED - Uses templates
│   ├── response_utils.py                  # ✅ NEW - Content negotiation
│   ├── router_auth.py                     # ✅ UPDATED - HTML/JSON support
│   ├── router_search.py                   # Unchanged
│   ├── router_etl.py                      # Unchanged
│   ├── auth.py                            # Unchanged
│   ├── jwt_utils.py                       # Unchanged
│   ├── security_utils.py                  # Unchanged
│   ├── config.py                          # Unchanged
│   └── lookups.py                         # Unchanged
│
└── 📊 DATA & CONFIGS
    ├── data/                              # FBI data files
    └── .env                               # Environment variables
```

---

## 📄 File Details

### 🎨 Static Files

#### `static/css/main.css`
**Purpose:** Main stylesheet for all web pages  
**Contains:**
- CSS variables with brand colors
- Typography styles
- Button styles
- Form styles
- Alert/card styles
- Responsive design

**Key Variables:**
```css
--primary-navy: #3d4461;    /* Your brand color */
--primary-light: #5b6a9b;   /* Hover states */
--success: #28a745;
--error: #dc3545;
```

**Used by:** All web page templates (via `base_web.html`)

---

#### `static/images/logo.png`
**Purpose:** Your Scientifics.io logo  
**Dimensions:** Recommended 500px width, transparent background  
**Used in:**
- Header of all web pages
- Could be added to emails if needed

**Current status:** 🚨 NEEDS YOUR LOGO FILE

---

### 📄 Template Files

#### `templates/layouts/base_email.html`
**Purpose:** Base template for all emails  
**Features:**
- Inline styles (email-safe)
- Responsive table layout
- Header with brand color
- Footer with copyright
- Blocks for customization

**Blocks available:**
- `title` - Page title
- `header_title` - Header text
- `content` - Main email content
- `email_footer` - Footer customization

**Inherited by:**
- `activation.html`
- `welcome.html`
- `api_key_reset.html`

---

#### `templates/layouts/base_web.html`
**Purpose:** Base template for all web pages  
**Features:**
- Links to external CSS
- Logo in header
- Navigation menu
- Footer with links
- Responsive design

**Blocks available:**
- `title` - Page title
- `navigation` - Navigation links
- `content` - Main page content
- `footer` - Footer customization
- `extra_css` - Additional stylesheets
- `extra_js` - Additional JavaScript

**Inherited by:**
- `activate_success.html`
- `activate_error.html`
- Future pages (login, dashboard, etc.)

---

#### `templates/emails/activation.html`
**Purpose:** Email sent when user registers  
**Contains:**
- Welcome message
- Activation button (links to `/auth/activate`)
- Activation link (copy/paste option)
- Warning about expiration
- What happens next steps

**Variables required:**
- `activation_link` - Full URL with token
- `base_url` - API base URL
- `year` - Current year

**Sent by:** `send_activation_email()` in `email_utils.py`

---

#### `templates/emails/welcome.html`
**Purpose:** Email sent after activation  
**Contains:**
- Success message
- API key displayed
- Getting started guide
- Code examples (curl)
- Link to documentation

**Variables required:**
- `api_key` - User's API key
- `base_url` - API base URL
- `year` - Current year

**Sent by:** `send_welcome_email()` in `email_utils.py`

---

#### `templates/emails/api_key_reset.html`
**Purpose:** Email sent when API key is reset  
**Contains:**
- New API key
- Security warning
- Instructions for use
- Example curl command

**Variables required:**
- `api_key` - New API key
- `base_url` - API base URL
- `year` - Current year

**Sent by:** `send_api_key_email()` in `email_utils.py`

---

#### `templates/auth/activate_success.html`
**Purpose:** Web page shown when activation succeeds  
**Contains:**
- Success message
- API key display (large, prominent)
- Email confirmation (if sent)
- Next steps guide
- Code examples
- Account details
- Links to docs/homepage

**Variables required:**
- `request` - FastAPI request object (required!)
- `api_key` - User's API key
- `email_sent` - Boolean
- `app_base_url` - For code examples

**Rendered by:** `/auth/activate` endpoint when successful

---

#### `templates/auth/activate_error.html`
**Purpose:** Web page shown when activation fails  
**Contains:**
- Error message
- Explanation
- Links to help/support
- Suggestions for next steps

**Variables required:**
- `request` - FastAPI request object (required!)
- `error` - Error message string
- `status_code` - HTTP status code

**Rendered by:** `/auth/activate` endpoint on error

---

### 🐍 Python Modules

#### `email_utils.py` ✅ UPDATED
**Purpose:** Send emails via Microsoft Graph API  
**Changes:** Removed all hardcoded HTML (300+ lines!)

**Functions:**
```python
send_activation_email(to_email, activation_token)
# Uses: emails/activation.html

send_welcome_email(to_email, api_key)
# Uses: emails/welcome.html

send_api_key_email(to_email, api_key)
# Uses: emails/api_key_reset.html
```

**Configuration:**
- Uses environment variables from `config.py`
- Jinja2 template environment configured
- Token caching for Graph API

---

#### `response_utils.py` ✅ NEW
**Purpose:** Handle content negotiation between HTML and JSON

**Functions:**
```python
wants_json(request)
# Returns: True if client wants JSON, False for HTML
# Checks: Accept header

render_or_json(request, template_name, context, json_data, status_code)
# Returns: HTMLResponse or JSONResponse based on client preference
# Use: For success responses

render_error(request, template_name, error_message, status_code, additional_context)
# Returns: HTML error page or JSON error
# Use: For error responses
```

**How it works:**
1. Checks `Accept` header in request
2. If `application/json` → Returns JSON
3. If `text/html` or no header → Returns HTML (default)

---

#### `router_auth.py` ✅ UPDATED
**Purpose:** Authentication endpoints  
**Changes:** `/auth/activate` now returns HTML or JSON

**Endpoints:**
- `POST /auth/register` - Still JSON only
- `GET /auth/activate` - Now HTML by default, JSON on request ⭐
- `POST /auth/token` - Still JSON only
- `POST /auth/key/reset` - Still JSON only

**Pattern for future endpoints:**
```python
@router.get("/endpoint")
async def endpoint(request: Request):
    # ... your logic ...
    
    context = {
        'request': request,  # Required!
        'your_data': data
    }
    
    json_data = {
        'message': 'Success',
        'data': data
    }
    
    return render_or_json(
        request,
        "template_name.html",
        context,
        json_data
    )
```

---

## 🎯 Quick Reference: What Uses What

### Email Flow:
```
1. router_auth.register() 
   → email_utils.send_activation_email()
   → templates/emails/activation.html
   → User's inbox

2. User clicks link → router_auth.activate()

3. router_auth.activate()
   → email_utils.send_welcome_email()
   → templates/emails/welcome.html
   → User's inbox
```

### Web Page Flow:
```
User clicks activation link
→ router_auth.activate()
→ response_utils.render_or_json()
→ templates/auth/activate_success.html
→ Browser renders with static/css/main.css
```

### Content Negotiation:
```
Request with Accept: text/html
→ response_utils.wants_json() returns False
→ renders HTML template
→ HTMLResponse returned

Request with Accept: application/json
→ response_utils.wants_json() returns True
→ returns json_data
→ JSONResponse returned
```

---

## 🔧 How to Extend

### Add a New Email Template:

1. Create template in `templates/emails/your_email.html`:
```html
{% extends "layouts/base_email.html" %}
{% block header_title %}Your Title{% endblock %}
{% block content %}
<!-- Your content with inline styles -->
{% endblock %}
```

2. Add function in `email_utils.py`:
```python
def send_your_email(to_email: str, data: str) -> bool:
    subject = "Your Subject"
    template = template_env.get_template('emails/your_email.html')
    html_body = template.render(
        data=data,
        base_url=EmailConfig.APP_BASE_URL,
        year=datetime.now().year
    )
    sender = get_email_sender()
    return sender.send_email(to_email, subject, html_body)
```

---

### Add a New Web Page:

1. Create template in `templates/your_section/page.html`:
```html
{% extends "layouts/base_web.html" %}
{% block title %}Page Title{% endblock %}
{% block content %}
<!-- Your content, uses main.css -->
{% endblock %}
```

2. Add endpoint in your router:
```python
@router.get("/your-page")
async def your_page(request: Request):
    context = {
        'request': request,
        'data': your_data
    }
    
    json_data = {'data': your_data}
    
    return render_or_json(
        request,
        "your_section/page.html",
        context,
        json_data
    )
```

3. Done! Auto gets:
- Your logo
- Brand colors
- Navigation
- Footer
- Responsive design

---

## ✅ What's Ready to Use

**For Emails:** ✅
- All three email types use templates
- Brand colors applied
- Reusable base template
- Easy to add new email types

**For Web Pages:** ✅
- Content negotiation working
- Base template ready
- CSS with brand colors
- Ready to build dashboard/profile/billing

**For APIs:** ✅
- All API endpoints unchanged
- Still return JSON
- Can add HTML versions anytime using same pattern

**For Future Development:** ✅
- Template inheritance set up
- CSS variables defined
- No HTML in Python code
- Scalable architecture ready

---

## 🚀 You're All Set!

Everything is in place and ready to scale. Just add your logo and start testing!
