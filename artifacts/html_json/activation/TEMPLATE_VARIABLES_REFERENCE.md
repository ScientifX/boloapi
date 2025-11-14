# Template Variables Reference

## Email Templates

### `emails/activation.html`
**Variables:**
- `activation_link` (str) - Full URL to activation endpoint with token
- `header_title` (str) - Custom header text (default: "Welcome to {FROM_NAME}")
- `year` (int) - Current year for footer

**Usage in email_utils.py:**
```python
send_activation_email(to_email: str, activation_token: str)
```

---

### `emails/api_key_reset.html`
**Variables:**
- `api_key` (str) - User's new API key
- `app_base_url` (str) - Base URL for API endpoints
- `header_title` (str) - Custom header text (default: "🔑 API Key Reset")
- `year` (int) - Current year for footer

**Usage in email_utils.py:**
```python
send_api_key_email(to_email: str, api_key: str)
```

---

### `emails/welcome.html`
**Variables:**
- `api_key` (str) - User's API key
- `app_base_url` (str) - Base URL for API endpoints
- `header_title` (str) - Custom header text (default: "✅ Account Activated!")
- `year` (int) - Current year for footer

**Usage in email_utils.py:**
```python
send_welcome_email(to_email: str, api_key: str)
```

---

## Web Templates

### `auth/activate_success.html`
**Variables:**
- `request` (Request) - FastAPI Request object (required for templates)
- `api_key` (str) - User's API key to display
- `email_sent` (bool) - Whether welcome email was sent
- `app_base_url` (str) - Base URL for API examples

**Usage in router_auth.py:**
```python
render_or_json(
    request=request,
    template_name="auth/activate_success.html",
    context={"request": request, "api_key": api_key, ...},
    json_data={...}
)
```

---

### `auth/activate_error.html`
**Variables:**
- `request` (Request) - FastAPI Request object (required)
- `error_message` (str) - Detailed error message
- `error_type` (str) - Error category: "not_found", "expired", "already_active", "error"
- `app_base_url` (str) - Base URL for help examples

**Usage in router_auth.py:**
```python
render_error(
    request=request,
    template_name="auth/activate_error.html",
    error_message="Token has expired",
    error_type="expired",
    context={"app_base_url": app_base_url},
    status_code=400
)
```

---

## Base Templates

### `layouts/base_email.html`
**Variables:**
- `title` (str) - Page title (from block)
- `header_title` (str) - Header text (passed to email_header.html)
- `year` (int) - Current year (passed to email_footer.html)

**Blocks:**
- `{% block title %}` - HTML title tag content
- `{% block email_header %}` - Override header component
- `{% block content %}` - Main email content
- `{% block email_footer %}` - Override footer component

---

### `layouts/base_web.html`
**Variables:**
- `request` (Request) - Required for templates
- `user_authenticated` (bool) - Whether user is logged in (for nav)

**Blocks:**
- `{% block title %}` - HTML title tag content
- `{% block extra_css %}` - Additional CSS includes
- `{% block header %}` - Override header component
- `{% block content %}` - Main page content
- `{% block footer %}` - Override footer component
- `{% block extra_js %}` - Additional JavaScript includes

---

## Component Templates

### `components/email_header.html`
**Variables:**
- `header_title` (str) - Header text to display

---

### `components/email_footer.html`
**Variables:**
- `year` (int) - Current year for copyright

---

### `components/web_header.html`
**Variables:**
- `request` (Request) - For URL generation
- `user_authenticated` (bool) - Show login vs logout links

---

### `components/web_footer.html`
**Variables:**
- `year` (int) - Current year for copyright

---

## Adding New Templates

### Example: Creating a Profile Page

1. **Create template**: `templates/auth/profile.html`

```html
{% extends "layouts/base_web.html" %}

{% block title %}User Profile - Scientifics.io{% endblock %}

{% block content %}
<div class="content">
    <h1>User Profile</h1>
    
    <div class="profile-info">
        <p><strong>Email:</strong> {{ user.email }}</p>
        <p><strong>Role:</strong> {{ user.role }}</p>
        <p><strong>Registered:</strong> {{ user.created_at }}</p>
    </div>
    
    <div class="actions">
        <a href="/auth/key/reset" class="btn btn-warning">Reset API Key</a>
        <a href="/docs" class="btn btn-primary">View Docs</a>
    </div>
</div>
{% endblock %}
```

2. **Create endpoint in router**:

```python
from response_utils import render_or_json

@router.get("/profile")
async def get_profile(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    user_id = current_user["user_id"]
    
    # Get user data from database
    user = get_user_by_id(user_id)
    
    return render_or_json(
        request=request,
        template_name="auth/profile.html",
        context={
            "request": request,
            "user": user,
            "user_authenticated": True
        },
        json_data={
            "email": user["email"],
            "role": user["role"],
            "created_at": user["created_at"].isoformat()
        }
    )
```

---

## Template Inheritance Examples

### Email Template Example
```html
{% extends "layouts/base_email.html" %}

{% block title %}My Custom Email{% endblock %}
{% block header_title %}Custom Header Text{% endblock %}

{% block content %}
<h2>Hello {{ user_name }}!</h2>
<p>This is my custom email content.</p>

<div style="background-color: #f8f9fa; padding: 15px;">
    <strong>Custom styled box</strong>
</div>
{% endblock %}
```

### Web Template Example
```html
{% extends "layouts/base_web.html" %}

{% block title %}My Custom Page{% endblock %}

{% block extra_css %}
<style>
    .custom-class { color: red; }
</style>
{% endblock %}

{% block content %}
<div class="content">
    <h1>{{ page_title }}</h1>
    <p>{{ page_content }}</p>
</div>
{% endblock %}

{% block extra_js %}
<script>
    console.log('Custom page loaded');
</script>
{% endblock %}
```

---

## Static File References in Templates

### CSS
```html
<link rel="stylesheet" href="{{ url_for('static', path='/css/main.css') }}">
<link rel="stylesheet" href="{{ url_for('static', path='/css/custom.css') }}">
```

### Images
```html
<img src="{{ url_for('static', path='/images/logo.png') }}" alt="Logo">
<img src="{{ url_for('static', path='/images/icon.svg') }}" alt="Icon">
```

### JavaScript
```html
<script src="{{ url_for('static', path='/js/app.js') }}"></script>
<script src="{{ url_for('static', path='/js/utils.js') }}"></script>
```

---

## Common Template Filters

### Date Formatting
```html
{{ user.created_at.strftime('%Y-%m-%d') }}
{{ user.created_at.strftime('%B %d, %Y') }}
```

### String Manipulation
```html
{{ user.email | upper }}
{{ user.role | lower }}
{{ description | truncate(100) }}
```

### Conditional Display
```html
{% if email_sent %}
    <div class="alert alert-success">Email sent!</div>
{% else %}
    <div class="alert alert-warning">Email not configured</div>
{% endif %}
```

### Loops
```html
{% for item in items %}
    <div class="item">{{ item.name }}</div>
{% endfor %}
```

---

## Best Practices

1. **Always pass `request`** to web templates for url_for() to work
2. **Use blocks** for flexibility and customization
3. **Include components** for reusable UI elements
4. **Keep inline styles** in email templates (email client compatibility)
5. **Use external CSS** for web templates (better maintainability)
6. **Escape user input** with `{{ variable | e }}` when needed
7. **Test both HTML and JSON** responses for each endpoint
8. **Validate template rendering** in development before deploying

---

## Troubleshooting

### Template Not Found
- Check file path: `templates/folder/file.html`
- Verify templates directory in `Jinja2Templates(directory="templates")`
- Case-sensitive on Linux/Mac

### Variable Not Defined
- Ensure variable is passed in context dict
- Check for typos in variable names
- Use `{{ variable | default('fallback') }}` for optional values

### Static Files 404
- Verify static files mounting: `app.mount("/static", StaticFiles(directory="static"))`
- Check file exists in static directory
- Use `url_for('static', path='/...')` in templates

### Email Rendering Issues
- Use inline styles (external CSS doesn't work in emails)
- Test with multiple email clients
- Keep HTML simple and table-based for emails
- Avoid JavaScript in emails
