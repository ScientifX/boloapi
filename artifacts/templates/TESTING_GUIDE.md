# Quick Testing Guide - Content Negotiation

## 🧪 How to Test HTML vs JSON Responses

### Test 1: Activation Link (HTML - Default)

**Scenario:** User clicks activation link in email

```bash
# Register a user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@scientifics.io"}'

# Response will include activation token (if email disabled)
# Copy the token from response

# Test HTML response (open in browser or curl)
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN_HERE"
```

**Expected Result:**  
Beautiful HTML page with:
- ✅ Success message
- Your API key displayed prominently
- Code examples
- Your logo in header
- Brand colors (#3d4461)

---

### Test 2: Activation Link (JSON - Explicit)

**Scenario:** API client programmatically activating

```bash
# Same registration as above...

# Test JSON response (with Accept header)
curl "http://localhost:8000/auth/activate?token=YOUR_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Expected Result:**  
JSON response:
```json
{
  "message": "Account activated successfully!",
  "api_key": "your_api_key_here...",
  "instructions": "Save this API key...",
  "email_sent": true
}
```

---

### Test 3: Activation Error (HTML)

```bash
# Test with invalid token
curl "http://localhost:8000/auth/activate?token=invalid_token"
```

**Expected Result:**  
HTML error page with:
- ❌ Error message
- Status code explanation
- Links to help

---

### Test 4: Activation Error (JSON)

```bash
# Test with invalid token, request JSON
curl "http://localhost:8000/auth/activate?token=invalid_token" \
  -H "Accept: application/json"
```

**Expected Result:**  
JSON error:
```json
{
  "error": "Invalid or expired activation token",
  "status_code": 404
}
```

---

## 📧 Test Email Templates

All three email functions now use templates:

```python
# Run the email test script
python test_email.py your_email@example.com
```

**What to Check in Emails:**
- ✅ Header is navy blue (#3d4461)
- ✅ No raw HTML tags visible
- ✅ Buttons are clickable
- ✅ Code blocks are formatted
- ✅ Footer copyright is present
- ✅ Links work correctly

---

## 🌐 Browser Testing

### Test in Real Browser:

1. **Start your server:**
   ```bash
   uvicorn app:app --reload
   ```

2. **Register via API:**
   ```bash
   curl -X POST "http://localhost:8000/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"email": "your_email@example.com"}'
   ```

3. **Get activation token from response**

4. **Open in browser:**
   ```
   http://localhost:8000/auth/activate?token=YOUR_TOKEN
   ```

5. **What you should see:**
   - Professional-looking page
   - Your logo in header
   - Navy blue accents
   - Clean, readable layout
   - Code examples formatted nicely
   - Footer with links

---

## 🔍 Testing Different Clients

### Postman/Insomnia:
- Set `Accept: application/json` in headers → Get JSON
- Remove Accept header or set `Accept: text/html` → Get HTML

### Curl:
- Default (no header) → HTML
- `-H "Accept: application/json"` → JSON

### Browser:
- Always gets HTML (browsers send `Accept: text/html`)

### JavaScript fetch():
```javascript
// Request HTML
fetch('/auth/activate?token=abc123')

// Request JSON
fetch('/auth/activate?token=abc123', {
  headers: { 'Accept': 'application/json' }
})
```

---

## ✅ Success Checklist

- [ ] Email templates display correctly (no raw HTML)
- [ ] Activation link in browser shows HTML page
- [ ] Activation link with JSON header returns JSON
- [ ] Error pages display correctly
- [ ] Logo appears in header (once you add it)
- [ ] Colors match brand (#3d4461)
- [ ] CSS loads properly (no 404 errors)
- [ ] Code blocks are formatted
- [ ] All links work

---

## 🐛 Troubleshooting

### Issue: CSS not loading
**Fix:** Check that `/static` is mounted in `app.py`:
```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

### Issue: Templates not found
**Fix:** Ensure templates are in `/mnt/project/templates/`

### Issue: Logo not showing
**Fix:** Place logo at `/mnt/project/static/images/logo.png`

### Issue: Always getting JSON
**Fix:** Remove `response_model` from endpoint decorator (if present)

### Issue: Always getting HTML
**Fix:** Make sure you're sending `Accept: application/json` header

---

## 📊 What Each Endpoint Returns

| Endpoint | Default Format | With Accept: application/json |
|----------|---------------|-------------------------------|
| `/auth/register` | JSON | JSON |
| `/auth/activate` | HTML | JSON |
| `/auth/token` | JSON | JSON |
| `/auth/key/reset` | JSON | JSON |
| `/api/search/*` | JSON | JSON |

Only `/auth/activate` has content negotiation for now (since users click it from email).

Other endpoints can be updated later using the same pattern!

---

## 🎯 Next Endpoints to Add HTML Support

When you're ready, these would benefit from HTML versions:

1. **`/auth/register`** - Registration confirmation page
2. **`/auth/key/reset`** - Key reset confirmation
3. **`/`** (homepage) - Already has HTML, but could use new template

Just follow the same pattern:
```python
return render_or_json(
    request,
    "template_name.html",
    context,
    json_data
)
```

Easy! 🚀
