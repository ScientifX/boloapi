# Content Negotiation Flow Diagram

## 🌐 How Requests Are Handled

```
┌─────────────────────────────────────────────────────────────────┐
│                    REQUEST COMES IN                              │
│                /auth/activate?token=abc123                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          ┌──────────────────────────────┐
          │  Check "Accept" Header       │
          └──────────┬───────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│ Accept:         │     │ Accept:         │
│ text/html       │     │ application/json│
│ (or no header)  │     │                 │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│ wants_json()    │     │ wants_json()    │
│ returns False   │     │ returns True    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────┐  ┌──────────────────┐
│ Render Template     │  │ Return JSON      │
│ activate_success.   │  │ {"message": ...  │
│ html                │  │  "api_key": ...} │
└──────────┬──────────┘  └────────┬─────────┘
           │                      │
           ▼                      ▼
┌──────────────────────┐  ┌──────────────────┐
│ Load CSS from        │  │ No template      │
│ /static/css/main.css │  │ Pure JSON        │
└──────────┬───────────┘  └────────┬─────────┘
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌──────────────────┐
│ HTMLResponse         │  │ JSONResponse     │
│ with brand styling   │  │ with data only   │
└──────────────────────┘  └──────────────────┘
```

---

## 📱 Client Types

### Browser (Chrome, Firefox, Safari)
```
GET /auth/activate?token=abc123
Accept: text/html,application/xhtml+xml,...

→ Gets HTML page ✅
```

### API Client (curl, Postman, fetch)
```
GET /auth/activate?token=abc123
Accept: application/json

→ Gets JSON response 📊
```

### Default (No Accept header)
```
GET /auth/activate?token=abc123

→ Gets HTML page (default) ✅
```

---

## 🔄 Template Rendering Process

### When HTML is Requested:

```
1. router_auth.activate()
   ↓
2. Check database, validate token
   ↓
3. Prepare context dict:
   {
     'request': request,
     'api_key': 'abc123...',
     'email_sent': True,
     'app_base_url': 'https://...'
   }
   ↓
4. Call render_or_json()
   ↓
5. wants_json(request) → False
   ↓
6. templates.TemplateResponse()
   ↓
7. Jinja2 loads: auth/activate_success.html
   ↓
8. Template extends: layouts/base_web.html
   ↓
9. Base template includes:
   - <link> to /static/css/main.css
   - <img> for logo (/static/images/logo.png)
   ↓
10. HTML rendered with all variables replaced
    ↓
11. Browser requests:
    - /static/css/main.css → 200 OK
    - /static/images/logo.png → 200 OK
    ↓
12. Final page displayed with brand styling ✨
```

### When JSON is Requested:

```
1. router_auth.activate()
   ↓
2. Check database, validate token
   ↓
3. Prepare json_data dict:
   {
     'message': 'Success!',
     'api_key': 'abc123...',
     'email_sent': True
   }
   ↓
4. Call render_or_json()
   ↓
5. wants_json(request) → True
   ↓
6. JSONResponse(content=json_data)
   ↓
7. No template loading
   ↓
8. No CSS loading
   ↓
9. Pure JSON returned 📊
```

---

## 🎯 Decision Tree

```
┌─────────────────────────────────────┐
│ Is this /auth/activate endpoint?    │
└──────┬───────────────────────┬──────┘
       │ Yes                   │ No
       ▼                       ▼
┌──────────────────┐   ┌───────────────────┐
│ Content          │   │ Return JSON only  │
│ Negotiation      │   │ (other endpoints) │
│ Available        │   └───────────────────┘
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────┐
│ Check Accept header          │
└──────┬──────────────┬────────┘
       │              │
       ▼              ▼
┌──────────────┐ ┌──────────────┐
│ JSON needed? │ │ HTML needed? │
│ (API client) │ │ (Browser)    │
└──────┬───────┘ └──────┬───────┘
       │                │
       ▼                ▼
┌──────────────┐ ┌──────────────┐
│ JSONResponse │ │ HTMLResponse │
│              │ │ + Templates  │
│              │ │ + CSS        │
└──────────────┘ └──────────────┘
```

---

## 🚦 Response Status Codes

### Success (200 OK):
- **HTML:** activate_success.html
- **JSON:** {"message": "Success!", ...}

### Not Found (404):
- **HTML:** activate_error.html with error message
- **JSON:** {"error": "Invalid token", "status_code": 404}

### Bad Request (400):
- **HTML:** activate_error.html with explanation
- **JSON:** {"error": "Already activated", "status_code": 400}

### Server Error (500):
- **HTML:** Generic error page (if configured)
- **JSON:** {"error": "Server error", "status_code": 500}

---

## 📊 Data Flow Comparison

### Old Way (All JSON):
```
User clicks email link
  ↓
JSON response: {"message": "...", "api_key": "..."}
  ↓
User sees raw JSON in browser 😞
  ↓
User confused, has to manually use API key
```

### New Way (HTML by default):
```
User clicks email link
  ↓
HTML response with beautiful page
  ↓
User sees:
  - Success message ✅
  - API key prominently displayed
  - Code examples ready to copy
  - Next steps clearly explained
  - Your branding throughout
  ↓
User happy, understands what to do 😊
```

### For API Clients (JSON when needed):
```
API client sends Accept: application/json
  ↓
JSON response: {"message": "...", "api_key": "..."}
  ↓
Client parses JSON, extracts api_key
  ↓
Automated workflows work perfectly 🤖
```

---

## 🎨 Styling Flow

### Email Templates:
```
emails/activation.html
  ↓
extends base_email.html
  ↓
Inline styles in HTML
  (email clients don't support external CSS)
  ↓
Brand colors hardcoded: #3d4461
  ↓
Renders in email client
```

### Web Templates:
```
auth/activate_success.html
  ↓
extends base_web.html
  ↓
<link rel="stylesheet" href="/static/css/main.css">
  ↓
CSS file loaded from server
  ↓
CSS variables: --primary-navy: #3d4461
  ↓
Renders in browser with full CSS support
```

---

## 🔧 Customization Points

### To Change Brand Colors:
```
Edit: static/css/main.css
Change: --primary-navy: #3d4461
Effect: All web pages update automatically
```

### To Change Email Colors:
```
Edit: templates/layouts/base_email.html
Change: background-color: #3d4461
Effect: All emails update automatically
```

### To Add New Page:
```
1. Create: templates/section/page.html
2. Extend: base_web.html
3. Add: endpoint with render_or_json()
4. Done: Auto gets branding
```

---

## 💡 Key Insights

### Why Content Negotiation?
- Users clicking links → Want nice web pages
- API clients → Want JSON for parsing
- Same endpoint → Serves both needs

### Why Template Inheritance?
- Define branding once → Use everywhere
- Change logo/colors → Updates all pages
- No code duplication

### Why Separate Email/Web Styles?
- Email clients → Need inline styles
- Web browsers → Support external CSS
- Different templates → Optimal for each

---

## ✅ Summary

```
┌────────────────────────────────────────────┐
│           USER EXPERIENCE                  │
├────────────────────────────────────────────┤
│ Clicks Email Link → Beautiful HTML Page   │
│ API Client → Clean JSON Response          │
│ Both → Work perfectly                     │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│       DEVELOPER EXPERIENCE                 │
├────────────────────────────────────────────┤
│ No HTML in Python Code → Clean codebase   │
│ Template Inheritance → Easy maintenance   │
│ Content Negotiation → Flexible responses  │
│ CSS Variables → Simple customization      │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│          SCALABILITY                       │
├────────────────────────────────────────────┤
│ Add New Page → Just extend base template  │
│ Change Branding → Edit CSS variables      │
│ Add Endpoint → Use render_or_json()       │
│ Everything → Ready to scale               │
└────────────────────────────────────────────┘
```

🚀 **Ready to build the future!**
