# Template Components Guide

## 📦 What Are Components?

Components are reusable template fragments that can be included in multiple templates using Jinja2's `{% include %}` directive. This promotes DRY (Don't Repeat Yourself) principles and makes maintenance easier.

---

## 📁 Component Files Created

### Email Components (Inline Styles)

**`templates/components/email_header.html`**
- Navy blue header with customizable title
- Inline styles for email client compatibility
- Variables: `header_title` (optional)

**`templates/components/email_footer.html`**
- Standard disclaimer text
- Copyright notice
- Variables: `year` (optional, defaults to 2024)

### Web Components (Uses main.css)

**`templates/components/web_header.html`**
- Logo and site title
- Navigation menu
- Conditional login/logout links based on `user_authenticated`
- Uses external CSS classes

**`templates/components/web_footer.html`**
- Copyright notice
- Footer navigation links
- Site description
- Variables: `year` (optional)

---

## 🎯 How Components Are Used

### In Base Templates

Components are automatically included in base templates:

**`base_email.html`:**
```jinja2
{% block email_header %}
    {% include 'components/email_header.html' %}
{% endblock %}

<!-- Content here -->

{% block email_footer %}
    {% include 'components/email_footer.html' %}
{% endblock %}
```

**`base_web.html`:**
```jinja2
{% block header %}
    {% include 'components/web_header.html' %}
{% endblock %}

<!-- Content here -->

{% block footer %}
    {% include 'components/web_footer.html' %}
{% endblock %}
```

### When You Extend Base Templates

Most of the time, you just extend the base template and components are included automatically:

```jinja2
{% extends "layouts/base_web.html" %}

{% block title %}My Page{% endblock %}

{% block content %}
    <h1>My Page Content</h1>
    <!-- Your content here -->
{% endblock %}
```

**Result:** Automatically gets header, footer, navigation, and all styling!

---

## 🔧 Customizing Components

### Option 1: Override Blocks (Recommended)

Override the entire header or footer block in your template:

```jinja2
{% extends "layouts/base_web.html" %}

{% block header %}
    {# Custom header for this page only #}
    <header class="header special-header">
        <h1>Custom Header</h1>
    </header>
{% endblock %}

{% block content %}
    <p>Page content...</p>
{% endblock %}
```

### Option 2: Pass Variables to Components

Pass variables when rendering templates:

**In Python:**
```python
return templates.TemplateResponse(
    "auth/activate_success.html",
    {
        'request': request,
        'header_title': 'Custom Title',  # Used by email_header.html
        'year': datetime.now().year,     # Used by footers
        'user_authenticated': True       # Used by web_header.html
    }
)
```

### Option 3: Modify Component Files Directly

Edit the component files to change default behavior:

**`templates/components/web_header.html`:**
```jinja2
<nav class="nav">
    <a href="/">Home</a>
    <a href="/docs">API Docs</a>
    <a href="/pricing">Pricing</a>  {# Added new link #}
    <!-- ... -->
</nav>
```

**Effect:** All pages using this component automatically get the new link!

---

## 🎨 Component Variables

### Email Header Component
```jinja2
{% include 'components/email_header.html' %}
```
**Variables:**
- `header_title` (optional) - Text to display in header
- Default: "Scientifics.io"

**Example:**
```python
template.render(header_title='Account Activated!')
```

### Email Footer Component
```jinja2
{% include 'components/email_footer.html' %}
```
**Variables:**
- `year` (optional) - Copyright year
- Default: 2024

**Example:**
```python
template.render(year=datetime.now().year)
```

### Web Header Component
```jinja2
{% include 'components/web_header.html' %}
```
**Variables:**
- `user_authenticated` (optional) - Show login/logout links
- Default: Shows login/register links

**Example:**
```python
template.render(user_authenticated=True)
```

### Web Footer Component
```jinja2
{% include 'components/web_footer.html' %}
```
**Variables:**
- `year` (optional) - Copyright year
- Default: 2024

---

## 📋 When to Use Components Directly

### Use Case 1: Custom Layouts

Creating a special layout that doesn't use the base templates:

```jinja2
<!DOCTYPE html>
<html>
<head>
    <title>Special Page</title>
    <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
    <table>
        <tr>
            {# Include just the header #}
            {% include 'components/email_header.html' %}
        </tr>
        <tr>
            <td>
                <h1>Custom Content</h1>
            </td>
        </tr>
    </table>
</body>
</html>
```

### Use Case 2: Reusing Components in Different Contexts

Using the same component in multiple places:

```jinja2
{% extends "layouts/base_web.html" %}

{% block content %}
    <div class="main-content">
        <!-- Main content here -->
    </div>
    
    <div class="sidebar">
        {# Include footer in sidebar too #}
        {% include 'components/web_footer.html' %}
    </div>
{% endblock %}
```

### Use Case 3: Email Templates with Custom Headers

```jinja2
{% extends "layouts/base_email.html" %}

{% block email_header %}
    {# Custom header for this specific email #}
    <tr>
        <td style="background-color: #28a745; padding: 30px; text-align: center;">
            <h1 style="color: #ffffff;">✅ Success!</h1>
        </td>
    </tr>
{% endblock %}

{% block content %}
    <p>Your custom email content...</p>
{% endblock %}
```

---

## 🔄 Component vs Block vs Extend

### Extend (Most Common)
**Use when:** Creating a new full page
```jinja2
{% extends "layouts/base_web.html" %}
```
**Gets:** Everything (header, footer, CSS, structure)

### Include (Components)
**Use when:** Reusing a fragment in multiple places
```jinja2
{% include 'components/web_footer.html' %}
```
**Gets:** Just that component

### Block Override
**Use when:** Customizing one section of a base template
```jinja2
{% block header %}
    {# Your custom header #}
{% endblock %}
```
**Gets:** Control over that specific section

---

## 💡 Best Practices

### DO:
✅ Use base templates for full pages (extends)  
✅ Use components for reusable fragments  
✅ Pass variables to components for customization  
✅ Override blocks when you need custom sections  
✅ Keep components small and focused  

### DON'T:
❌ Copy/paste header HTML into every template  
❌ Hardcode values in components (use variables)  
❌ Mix inline styles in web components  
❌ Create components for one-time use  

---

## 🎯 Quick Reference

### I Want to...

**Create a standard web page:**
```jinja2
{% extends "layouts/base_web.html" %}
```

**Create a standard email:**
```jinja2
{% extends "layouts/base_email.html" %}
```

**Change the logo site-wide:**
Edit `/static/images/logo.png`

**Change navigation links site-wide:**
Edit `templates/components/web_header.html`

**Change footer text site-wide:**
Edit `templates/components/web_footer.html`

**Customize header for ONE page:**
```jinja2
{% block header %}
    {# Custom header #}
{% endblock %}
```

**Reuse footer in two places:**
```jinja2
{% include 'components/web_footer.html' %}
```

---

## 🏗️ Component Architecture

```
Base Templates (Full Page Structure)
├── base_email.html
│   ├── includes: email_header.html
│   └── includes: email_footer.html
│
└── base_web.html
    ├── includes: web_header.html
    └── includes: web_footer.html

Your Templates (Content)
├── emails/
│   ├── activation.html (extends base_email.html)
│   ├── welcome.html (extends base_email.html)
│   └── api_key_reset.html (extends base_email.html)
│
└── auth/
    ├── activate_success.html (extends base_web.html)
    └── activate_error.html (extends base_web.html)
```

**Result:** Change component once → Updates everywhere! 🎉

---

## 📦 Summary

**Components = Reusable building blocks**

- Created 4 component files
- Automatically included in base templates  
- Can be used directly with `{% include %}`
- Customizable via variables or overrides
- Change once, update everywhere

**You now have maximum flexibility and minimal duplication!** 🚀
