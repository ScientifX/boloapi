# File Placement Reference

## Template Files Location

Your templates directory should look like this after adding the new files:

```
templates/
├── components/
│   ├── email_header.html
│   ├── email_footer.html
│   ├── web_header.html
│   └── web_footer.html
├── layouts/
│   ├── base_email.html
│   └── base_web.html
├── auth/
│   ├── activation.html        (existing - email template)
│   ├── activate_success.html  (existing - web page)
│   ├── activate_error.html    (existing - web page)
│   ├── register_success.html  ← ADD THIS (web page)
│   └── register_error.html    ← ADD THIS (web page)
├── emails/
│   ├── activation.html        (existing)
│   ├── api_key_reset.html     (existing)
│   └── welcome.html           (existing)
└── index.htm                  (existing - homepage)
```

## Python Files to Update

### router_auth.py
Location: `router_auth.py` (project root)

**Replace the `/register` endpoint** (starts at line ~172) with the updated version from `register_endpoint_updated.py`.

**Before replacement, the function signature looks like:**
```python
@router.post(
    "/register",
    response_model=RegisterResponse,  # ← This line changes
    status_code=status.HTTP_201_CREATED,
```

**After replacement, it should be:**
```python
@router.post(
    "/register",
    summary="Register New User",  # ← No response_model
```

**Required imports** (should already exist):
```python
from response_utils import render_or_json, render_error
from fastapi.responses import Response
```

## No Other Changes Needed

These files already have everything they need:
- ✅ `response_utils.py` - Has `render_or_json()` and `render_error()`
- ✅ `base_web.html` - Layout template ready to extend
- ✅ `web_header.html` - Header component
- ✅ `web_footer.html` - Footer component
- ✅ `static/css/main.css` - Should have all CSS classes used

## Quick Copy Commands

If you're working in a terminal:

```bash
# Create auth directory if it doesn't exist
mkdir -p templates/auth

# Copy the templates
cp /path/to/register_success.html templates/auth/
cp /path/to/register_error.html templates/auth/

# Verify placement
ls -la templates/auth/
```

## Verification Checklist

After placing files, verify:

- [ ] Templates are in `templates/auth/` directory
- [ ] Templates can extend `layouts/base_web.html`
- [ ] `/register` endpoint updated in `router_auth.py`
- [ ] Server restarts without errors
- [ ] Test with cURL using JSON Accept header
- [ ] Test with browser (HTML Accept header)
- [ ] Both success and error cases render correctly

## Testing Quick Reference

```bash
# Test JSON response (API client)
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email": "newuser@example.com"}'

# Test HTML response (browser simulation)
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -H "Accept: text/html" \
  -d '{"email": "newuser@example.com"}' \
  -L  # Follow redirects if any
```

## Common Issues and Solutions

### Issue: Template not found error
**Solution:** Check that template is in `templates/auth/register_success.html` (not `auth/register_success.html`)

### Issue: CSS styles not applying
**Solution:** Verify `main.css` is served from `/static/css/main.css` and contains required classes

### Issue: Import errors in router_auth.py
**Solution:** Ensure these imports exist at top of file:
```python
from fastapi.responses import Response
from response_utils import render_or_json, render_error
```

### Issue: Still getting JSON even from browser
**Solution:** Check `response_utils.wants_json()` logic - it should default to HTML for browsers

## File Contents Summary

| File | Purpose | Type | Uses |
|------|---------|------|------|
| `register_success.html` | Registration success page | Web template | `base_web.html` |
| `register_error.html` | Registration error page | Web template | `base_web.html` |
| `router_auth.py` | Updated /register endpoint | Python router | Both templates |

## Dependencies

All dependencies should already be installed:
- FastAPI
- Jinja2
- Pydantic
- Your existing project modules

No new packages needed! 🎉
