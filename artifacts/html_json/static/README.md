# Static Pages Installation Guide

This package contains static pages for About, Privacy Policy, Terms of Service, and Contact.

## Installation Steps

### 1. Copy Templates

Copy the contents of the `templates/static/` folder to your project's `templates/static/` directory:

```
your_project/
├── templates/
│   └── static/
│       ├── about.html
│       ├── privacy.html
│       ├── terms.html
│       └── contact.html
```

### 2. Update CSS

Add the contents of `static/css/static_pages.css` to your existing `static/css/main.css` file.

### 3. Update app.py

Add the route code from `app_routes_to_add.py` to your `app.py` file.

**Location:** Add these routes after your existing routes, before the validation functions.

**Important:** The routes are already configured with:
- More permissive rate limiting (30/minute)
- Proper template paths
- Integration with your existing authentication system

### 4. Test the Pages

Start your FastAPI application and visit:
- http://localhost:8000/about
- http://localhost:8000/privacy
- http://localhost:8000/terms
- http://localhost:8000/contact

## Customization

### Email Addresses
In `app_routes_to_add.py`, update the contact page email addresses:
```python
"support_email": "support@scientifics.io",  # Change to your email
"business_email": "contact@scientifics.io"  # Change to your email
```

### Last Updated Dates
The privacy and terms pages show "November 2024" as last updated. Update these in the route context:
```python
"last_updated": "November 2024"  # Change to current date
```

### Legal Review
While the Privacy Policy and Terms of Service are comprehensive and realistic, you should have your attorney review them to ensure they meet your specific legal requirements and jurisdiction.

## File Structure

```
static_pages_package/
├── README.md (this file)
├── app_routes_to_add.py (code to add to app.py)
├── templates/
│   └── static/
│       ├── about.html
│       ├── privacy.html
│       ├── terms.html
│       └── contact.html
└── static/
    └── css/
        └── static_pages.css (add to main.css)
```

## Notes

- All pages use your existing template structure (base_web.html)
- Styling matches your navy blue (#3d4461) brand colors
- Content is written in plain, accessible English
- Pages are mobile-responsive
- Rate limiting is more permissive for static content (30/minute vs 10/minute)

## Support

If you have questions about these static pages or need customization, refer to your project documentation or contact your development team.
