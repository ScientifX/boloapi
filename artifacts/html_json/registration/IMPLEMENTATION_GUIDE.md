# Register Endpoint Content Negotiation Implementation

## Overview
Extended content negotiation to the `/auth/register` endpoint, allowing it to return either HTML (for browsers) or JSON (for API clients) based on the Accept header.

## Files Created

### 1. register_success.html
**Location:** `templates/auth/register_success.html`

**Features:**
- Extends `layouts/base_web.html` for brand consistency
- Displays registration details (email, user_id)
- Shows different content based on email configuration:
  - **Email enabled:** Instructions about the two-email workflow (activation + welcome)
  - **Email disabled:** Direct activation link for testing
- Handles both new registrations and resent activations (is_resend flag)
- Clear next steps with numbered instructions
- Account tier information (BASIC role)
- Links to documentation and homepage

**Template Variables:**
- `email` - User's email address
- `user_id` - Generated user UUID
- `email_sent` - Boolean indicating if email was sent
- `activation_token` - Token for manual activation (when email disabled)
- `app_base_url` - Base URL for links
- `is_resend` - Boolean indicating if this is a resend scenario

### 2. register_error.html
**Location:** `templates/auth/register_error.html`

**Features:**
- Extends `layouts/base_web.html` for brand consistency
- Handles multiple error scenarios:
  - **already_registered:** User exists and is active
  - **validation errors:** Invalid email format
  - **server errors:** Unexpected failures
- Provides context-specific solutions for each error type
- Includes code examples for recovery actions
- Links to relevant endpoints (/auth/token, /auth/key/reset)

**Template Variables:**
- `error_message` - Detailed error description
- `error_type` - Error category
- `email` - User's email (when available)
- `app_base_url` - Base URL for links

### 3. Updated Register Endpoint
**Location:** `router_auth.py` (replace existing `/register` endpoint)

**Key Changes:**
1. **Return Type:** Changed from `RegisterResponse` to `Response` for flexibility
2. **Content Negotiation:**
   - Uses `render_or_json()` for success responses
   - Uses `render_error()` for error responses
3. **Error Handling:**
   - Converts `HTTPException` to rendered errors
   - Catches all exceptions and renders them properly
4. **Context Preparation:**
   - Builds separate `template_context` for HTML
   - Builds separate `json_data` for JSON API
   - Includes `is_resend` flag to differentiate scenarios

## How Content Negotiation Works

The endpoint checks the `Accept` header in the request:

**Browser Request (HTML):**
```
Accept: text/html
```
→ Returns HTML page using Jinja2 templates

**API Request (JSON):**
```
Accept: application/json
```
→ Returns JSON response

**Default:** If no Accept header or both formats accepted, defaults to HTML (browser-friendly).

## Integration Steps

1. **Place Templates:**
   ```
   templates/
   ├── auth/
   │   ├── register_success.html  ← Create this
   │   └── register_error.html    ← Create this
   ```

2. **Update Router:**
   - Replace the existing `/register` endpoint in `router_auth.py` with the updated code
   - Ensure `Response` is imported from `fastapi.responses`
   - Ensure `render_or_json` and `render_error` are imported from `response_utils`

3. **No Changes Needed:**
   - `response_utils.py` - Already has required functions
   - `base_web.html` - Already set up for template extension
   - CSS/styling - Uses existing styles from `main.css`

## Testing

### Test with cURL (JSON response):
```bash
# Successful registration
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email": "test@example.com"}'

# Already registered error
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email": "existing@example.com"}'
```

### Test with Browser (HTML response):
```
# Navigate to a form that submits to /auth/register
# Or use browser dev tools to POST
```

### Test Accept Header Priority:
```bash
# Prefers JSON when both accepted
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/html" \
  -d '{"email": "test@example.com"}'
```

## Consistency with Activate Endpoint

Both `/register` and `/activate` now use:
- Same content negotiation approach
- Same template structure (extends `base_web.html`)
- Same utility functions (`render_or_json`, `render_error`)
- Same styling and branding
- Similar error handling patterns

## Future Enhancements

Optional additions to consider:
1. **GET /register** - HTML registration form page
2. **Rate limiting display** - Show remaining attempts in error pages
3. **Email verification** - Show if email is reachable before sending
4. **Captcha integration** - Prevent automated abuse
5. **Password fields** - If adding password authentication later

## Notes

- Templates use existing CSS classes from `main.css`
- Alert styles: `.alert-success`, `.alert-info`, `.alert-warning`, `.alert-error`
- Code blocks use `.code-block` class
- Buttons use `.btn`, `.btn-primary`, `.btn-secondary` classes
- Layout uses `.content`, `.form-group`, `.text-center` classes
- All inline styles from email templates are avoided (external CSS only)
