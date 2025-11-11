# Quick Reference - Template System

## Content Negotiation

### Automatic HTML/JSON Selection

```python
from response_utils import render_or_json, render_error

# Success response
return render_or_json(
    request=request,
    template_name="my/template.html",
    context={"data": value},
    json_data={"message": "Success", "data": value}
)

# Error response
return render_error(
    request=request,
    template_name="errors/my_error.html",
    error_message="What went wrong",
    error_type="Error Title",
    status_code=400
)
```

### How It Decides

```
Accept: application/json  →  Returns JSON
Accept: text/html         →  Returns HTML
No Accept header          →  Returns HTML (default)
```

## Creating New Templates

### Web Page Template

```html
{% extends "layouts/base_web.html" %}

{% block title %}My Page - scientifics.io{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto">
    <h1 class="text-3xl font-bold text-gray-900 mb-6">
        {{ title }}
    </h1>
    <p class="text-gray-600">
        {{ description }}
    </p>
</div>
{% endblock %}
```

### Email Template

```html
{% extends "layouts/base_email.html" %}

{% block title %}Subject Line{% endblock %}

{% block content %}
<h2>Email Heading</h2>
<p>Email content with {{ variable }}.</p>

<div class="info-box">
    <p><strong>💡 Tip:</strong> Helpful information</p>
</div>

<a href="{{ link }}" class="button">Click Here</a>
{% endblock %}
```

## Tailwind Classes (Common)

### Layout
```html
<!-- Container -->
<div class="max-w-4xl mx-auto px-4 py-8">

<!-- Card -->
<div class="bg-white rounded-lg shadow-lg p-6">

<!-- Grid -->
<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
```

### Typography
```html
<h1 class="text-3xl font-bold text-gray-900">
<h2 class="text-2xl font-bold text-gray-900">
<p class="text-gray-600">
<code class="bg-gray-100 px-2 py-1 rounded text-sm font-mono">
```

### Colors (scientifics.io palette)
```html
<!-- Brand colors -->
<div class="bg-brand-600 text-white">    <!-- Primary -->
<div class="text-brand-600">             <!-- Primary text -->
<div class="bg-brand-50">                <!-- Light background -->

<!-- Semantic colors -->
<div class="bg-blue-500">                <!-- Links/actions -->
<div class="bg-green-500">               <!-- Success -->
<div class="bg-red-500">                 <!-- Errors -->
<div class="bg-amber-500">               <!-- Warnings -->
```

### Buttons
```html
<!-- Primary button -->
<button class="bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3 px-6 rounded-lg">

<!-- Secondary button -->
<button class="bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-3 px-6 rounded-lg">

<!-- Link button -->
<a href="#" class="inline-block bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3 px-6 rounded-lg">
```

### Forms
```html
<input type="text" 
       class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-brand-500">

<label class="block text-sm font-medium text-gray-700 mb-2">
```

## Email Components

### Info Box (Blue)
```html
<div class="info-box">
    <p style="margin: 0; font-weight: 600; color: #1e40af;">💡 Note:</p>
    <p style="margin: 8px 0 0 0; color: #1e40af;">Your content here</p>
</div>
```

### Warning Box (Amber)
```html
<div class="warning-box">
    <p style="margin: 0; font-weight: 600; color: #92400e;">⚠️ Important:</p>
    <p style="margin: 8px 0 0 0; color: #92400e;">Your content here</p>
</div>
```

### Success Box (Green)
```html
<div class="success-box">
    <p style="margin: 0; font-weight: 600; color: #065f46;">✅ Success:</p>
    <p style="margin: 8px 0 0 0; color: #065f46;">Your content here</p>
</div>
```

### Button (Email-safe)
```html
<a href="{{ link }}" class="button">Click Here</a>
```

### Code Block
```html
<pre class="code-block">curl -X POST "{{ base_url }}/api/endpoint"</pre>
```

## Environment Variables

Templates have access to:
- `{{ base_url }}` - From EmailConfig.APP_BASE_URL
- `{{ request }}` - FastAPI Request object (web templates only)
- Any variables you pass in context dict

## Common Patterns

### Conditional Content
```html
{% if email_sent %}
    <p>Check your email!</p>
{% else %}
    <p>Email not configured</p>
{% endif %}
```

### Lists
```html
<ul class="space-y-2">
{% for item in items %}
    <li class="flex items-center">
        <svg class="h-5 w-5 text-green-500 mr-2">...</svg>
        {{ item }}
    </li>
{% endfor %}
</ul>
```

### Links
```html
<!-- Email -->
<a href="{{ link }}" class="link">Click here</a>

<!-- Web -->
<a href="{{ url }}" class="text-blue-500 hover:underline">Click here</a>
```

## Debugging Tips

### Check What Template Gets
```html
<!-- In template -->
<pre>{{ context_var }}</pre>

<!-- Or in Python -->
logger.info(f"Template context: {context}")
```

### Test HTML vs JSON
```bash
# Get HTML
curl http://localhost:8000/auth/activate?token=xyz

# Get JSON
curl -H "Accept: application/json" http://localhost:8000/auth/activate?token=xyz
```

### Validate Templates
```python
# In Python console
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('auth/activate_success.html')
html = template.render(api_key="test", base_url="http://localhost")
print(html)
```

## Common Errors

### Template Not Found
```
jinja2.exceptions.TemplateNotFound: auth/activate.html
```
**Fix:** Check template path and ensure `templates/` directory exists

### Variable Not Defined
```
jinja2.exceptions.UndefinedError: 'api_key' is undefined
```
**Fix:** Pass variable in context dict

### Import Error
```
ModuleNotFoundError: No module named 'jinja2'
```
**Fix:** `pip install jinja2`

## File Locations

```
your_project/
├── templates/              # All templates here
│   ├── layouts/           # Base templates
│   ├── emails/            # Email templates
│   └── auth/              # Auth page templates
├── email_utils.py         # Email sending (uses templates)
├── response_utils.py      # Content negotiation helpers
└── router_auth.py         # Your endpoints
```

## Next Steps

1. Copy templates to your project
2. Add response_utils.py
3. Update router endpoints to use render_or_json()
4. Test with browser and curl
5. Expand with more pages!
