# Quick Reference: Subscription Authentication

## 🚀 Quick Start (5 minutes)

### 1. Install Dependencies
```bash
pip install fastapi httpx pyjwt python-dotenv
```

### 2. Set Environment Variables
```bash
# .env file
JWT_SECRET_KEY=your-super-secret-key-min-32-chars
LEMON_SQUEEZY_API_KEY=your_api_key
LEMON_SQUEEZY_WEBHOOK_SECRET=your_webhook_secret
```

### 3. Use in Your Endpoints
```python
from auth import require_active_subscription, User
from fastapi import Depends

@app.get("/premium")
async def premium(user: User = Depends(require_active_subscription)):
    return {"content": "Premium stuff"}
```

That's it! Your endpoint now requires an active subscription.

---

## 🎯 Common Use Cases

### Protect Any Endpoint
```python
# Requires active subscription
@app.get("/protected")
async def protected(user: User = Depends(require_active_subscription)):
    return {"data": "secret"}
```

### Require Specific Plan
```python
# Only Pro/Enterprise users
@app.get("/pro")
async def pro(
    user: User = Depends(require_active_subscription),
    _: None = Depends(require_plan(["pro_variant_id", "enterprise_variant_id"]))
):
    return {"feature": "pro"}
```

### Just Check Login (No Subscription Required)
```python
# Any logged-in user
@app.get("/profile")
async def profile(user: User = Depends(get_current_user)):
    return {"user": user.email}
```

---

## 🔐 Authentication Flow

```
1. User buys subscription on Lemon Squeezy
2. Webhook updates your database
3. User logs in → receives JWT token
4. User includes token in requests
5. Your API checks token + subscription status
```

---

## 📝 Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Show content |
| 401 | Not logged in | Redirect to login |
| 403 | No subscription | Redirect to pricing |
| 403 | Wrong plan | Show upgrade modal |

---

## 🧪 Testing

### Get Token
```bash
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}' \
  | jq -r '.access_token'
```

### Use Token
```bash
curl http://localhost:8000/api/premium-content \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Test Different States
```bash
# No token (expect 401)
curl http://localhost:8000/api/premium-content

# With token (expect 200 or 403)
curl http://localhost:8000/api/premium-content \
  -H "Authorization: Bearer TOKEN"
```

---

## 🔧 Files You Need

### Core Files
1. **auth.py** - Authentication logic (import this)
2. **protected_endpoints.py** - Example endpoints
3. **lemon_squeezy_router.py** - Webhook handler

### Your Main App
```python
from fastapi import FastAPI
from lemon_squeezy_router import router as lemon_router
from protected_endpoints import router as protected_router

app = FastAPI()
app.include_router(lemon_router)
app.include_router(protected_router)
```

---

## 📊 Database Schema (Minimal)

```sql
-- Users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    subscription_id VARCHAR(255)
);

-- Subscriptions  
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    lemon_squeezy_id VARCHAR(255) UNIQUE,
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(50),
    variant_id VARCHAR(255)
);
```

---

## 🎨 Frontend Integration

### Login
```javascript
const response = await fetch('/api/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password })
});
const { access_token } = await response.json();
localStorage.setItem('token', access_token);
```

### Call Protected Endpoint
```javascript
const token = localStorage.getItem('token');
const response = await fetch('/api/premium-content', {
  headers: { 'Authorization': `Bearer ${token}` }
});

if (response.status === 401) {
  // Not logged in
  window.location.href = '/login';
} else if (response.status === 403) {
  // No subscription
  window.location.href = '/pricing';
}
```

---

## 🔥 Quick Troubleshooting

### "401 Unauthorized"
- ✅ Check token is in Authorization header
- ✅ Verify JWT_SECRET_KEY is set
- ✅ Token might be expired (30 min default)

### "403 Forbidden - No subscription"
- ✅ Check webhook updated database
- ✅ Verify subscription_id in users table
- ✅ Confirm subscription status is "active"

### "403 Forbidden - Wrong plan"
- ✅ Get correct variant IDs from Lemon Squeezy
- ✅ Update variant IDs in require_plan()
- ✅ Check user's actual variant_id

---

## 📚 Full Documentation

- **AUTH_GUIDE.md** - Complete implementation guide
- **README.md** - Lemon Squeezy integration
- **WEBHOOK_TESTING_GUIDE.md** - Test webhooks locally

---

## 🎁 Bonus: Complete Working Example

See **complete_example.py** for a fully working app with:
- ✅ Login endpoint
- ✅ Protected endpoints  
- ✅ Plan-specific features
- ✅ Webhook handler
- ✅ Test instructions

Just run: `uvicorn complete_example:app --reload`

---

## ⚡ Advanced Patterns

### Custom Error Messages
```python
@app.exception_handler(HTTPException)
async def custom_exception_handler(request, exc):
    if exc.status_code == 403:
        if "subscription" in exc.detail.lower():
            return JSONResponse(
                status_code=403,
                content={
                    "error": "subscription_required",
                    "message": "Upgrade to access this feature",
                    "upgrade_url": "https://yoursite.com/pricing"
                }
            )
    return exc
```

### Rate Limiting by Plan
```python
from auth import rate_limiter

@app.get("/api-call")
async def api_call(user: User = Depends(rate_limiter.check_limit)):
    # Different limits per plan
    return {"data": "..."}
```

### Check Multiple Plans
```python
# Must have one of these plans
require_plan(["basic_id", "pro_id", "enterprise_id"])
```

---

## 🎯 Remember

1. **Always use HTTPS in production**
2. **Verify webhook signatures**
3. **Hash passwords (use bcrypt)**
4. **Set strong JWT_SECRET_KEY**
5. **Test all subscription states**
6. **Handle expired tokens gracefully**
7. **Cache subscription checks**
8. **Log authentication attempts**

---

## 🚨 Security Checklist

- [ ] JWT_SECRET_KEY is strong (32+ chars)
- [ ] Passwords are hashed (never store plain text)
- [ ] HTTPS only in production
- [ ] Webhook signatures verified
- [ ] Tokens expire (implement refresh)
- [ ] Rate limiting enabled
- [ ] SQL injection prevented (use parameterized queries)
- [ ] CORS configured properly
- [ ] Error messages don't leak info
- [ ] Logs don't contain sensitive data

---

## 💡 Tips

**Get Variant IDs**: Lemon Squeezy Dashboard → Products → Variants → Copy ID

**Test Locally**: Use ngrok for webhooks: `ngrok http 8000`

**Debug Auth**: Add logging in auth.py to see what's happening

**Mock Data**: Use complete_example.py to test without real database

**Frontend**: Check protected_endpoints.py for JavaScript examples

---

## 📞 Need Help?

1. Check **AUTH_GUIDE.md** for detailed explanations
2. See **complete_example.py** for working code
3. Test with **curl** commands in this file
4. Review **protected_endpoints.py** for patterns
5. Read Lemon Squeezy docs: https://docs.lemonsqueezy.com

---

## 🎉 You're Ready!

You now have everything needed to implement subscription-based authentication. Start with **complete_example.py** to see it working, then customize for your needs.

**Happy coding! 🚀**
