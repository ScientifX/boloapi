# Scientifics.io Template System - Complete Package

## 🎉 What You Got

This package contains a complete Jinja2 template system for your Scientifics.io API with:

✅ **Reusable template structure** (base layouts, components)  
✅ **Email templates** (activation, welcome, API key reset)  
✅ **Web page templates** (activation success/error pages)  
✅ **Branded CSS** with your scientifics.io colors  
✅ **Content negotiation** (HTML or JSON from same endpoint)  
✅ **Updated Python files** (email_utils.py, content_negotiation.py)

## 📦 Package Contents

```
outputs/
├── IMPLEMENTATION_GUIDE.md        # Detailed setup guide
├── templates/                     # All Jinja2 templates
│   ├── layouts/                   # Base templates
│   ├── emails/                    # Email templates
│   └── auth/                      # Auth page templates
├── static/                        # CSS and images
│   ├── css/main.css               # Branded stylesheet
│   └── images/                    # Put logo here!
├── email_utils.py                 # Updated (uses templates)
└── content_negotiation.py         # New helper module
```

## 🚀 Quick Start (3 Steps)

### 1. Copy Files to Your Project
```bash
cp -r templates /path/to/your/project/
cp -r static /path/to/your/project/
cp email_utils.py /path/to/your/project/
cp content_negotiation.py /path/to/your/project/
```

### 2. Add Your Logo
Put your scientifics.io logo at:
```
/path/to/your/project/static/images/logo.png
```
*(PNG, ~200-300px wide, transparent background)*

### 3. Update app.py
Add one line after `app = FastAPI(...)`:
```python
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")
```

**That's it! You're ready to go.** 🎊

## 🎨 Your Brand Colors

From your logo, I extracted:
- **Primary Navy:** `#3d4461` (main brand color)
- **Navy Light:** `#5b6a9b` (hover states)
- **Navy Dark:** `#2a2f42` (accents)

Plus standard UI colors (green, red, yellow, blue for alerts/buttons).

## 🧪 Testing

### Test Emails
```bash
python test_email.py your@email.com
```

### Test Web Pages
```bash
uvicorn app:app --reload

# Visit in browser
http://localhost:8000/auth/activate?token=test123
```

## 📖 How It Works

### HTML vs JSON
Same endpoint, different output based on request:

**Browser (HTML):**
```
User clicks link → Gets nice branded HTML page
```

**API (JSON):**
```bash
curl -H "Accept: application/json" /auth/activate?token=xyz
# Returns JSON
```

### Template Inheritance
All templates extend base layouts:

```html
<!-- Email template -->
{% extends "layouts/base_email.html" %}
{% block content %}
  Your email content here
{% endblock %}

<!-- Web page template -->
{% extends "layouts/base_web.html" %}
{% block content %}
  Your page content here
{% endblock %}
```

## 🔧 What Changed

| Before | After |
|--------|-------|
| HTML strings in Python | HTML in template files |
| JSON only | HTML or JSON (flexible) |
| Inconsistent styling | Unified brand |
| Hard to maintain | Easy to extend |

## 🎯 Next Steps

You now have the foundation to easily add:
- Login pages
- User dashboards
- Profile pages
- Billing pages
- Any other web UI

Just create new templates extending `base_web.html`!

## 📚 Documentation

- **IMPLEMENTATION_GUIDE.md** - Detailed setup and examples
- **templates/layouts/base_web.html** - Web page base
- **templates/layouts/base_email.html** - Email base
- **static/css/main.css** - All available CSS classes

## 💡 Pro Tips

1. **Logo location:** Must be at `/static/images/logo.png`
2. **Email templates:** Always use inline styles (email client compatibility)
3. **Web templates:** Use CSS classes from `main.css`
4. **Content negotiation:** Use `wants_json(request)` helper
5. **Testing:** Always test in browser AND with curl

## 🐛 Troubleshooting

**Logo not showing?**
- Check file exists at `/static/images/logo.png`
- Verify `app.mount("/static", ...)` in app.py

**Styles not loading?**
- Check static files mounted correctly
- Clear browser cache
- Look for 404 errors in browser console

**Templates not found?**
- Verify `/templates/` at project root
- Check template paths match exactly
- Ensure jinja2 is installed

## ✅ You're Done!

Everything is ready. Just:
1. Copy the files
2. Add your logo
3. Start building!

The template system is production-ready and waiting for you to extend it.

**Happy coding!** 🚀

---

**Questions?** Check IMPLEMENTATION_GUIDE.md for detailed examples and patterns.
