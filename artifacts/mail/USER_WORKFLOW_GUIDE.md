# User Workflow Guide - No More BDAC Errors! 😄

## The Correct Registration & Activation Flow

### Step-by-Step: How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER REGISTERS                                               │
│    POST /auth/register {"email": "user@example.com"}           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. SYSTEM SENDS ACTIVATION EMAIL                                │
│    Subject: "Activate Your Account"                             │
│    Content: Click this link to activate → [ACTIVATION LINK]     │
│    ⚠️  This email does NOT contain your API key                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. USER CLICKS ACTIVATION LINK                                  │
│    Browser opens: /auth/activate?token=xxx                      │
│    Account is now ACTIVATED                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. SYSTEM SENDS WELCOME EMAIL                                   │
│    Subject: "Welcome - Your API Key"                            │
│    Content: Here is your API key: [API_KEY_HERE]               │
│    ✅ THIS is the email with your API key!                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. USER USES API KEY FROM WELCOME EMAIL                         │
│    POST /auth/token {"api_key": "..."}                          │
│    Gets JWT access token                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Common Mistakes (BDAC Errors 😄)

### ❌ MISTAKE #1: Using API Key from Wrong Email
**What users do:**
- Get activation email
- Get welcome email  
- Try to use API key from activation email (doesn't exist!)
- Wonder why it doesn't work

**Solution:**
- ✅ Use API key from **WELCOME email** (received AFTER clicking activation link)

---

### ❌ MISTAKE #2: Clicking Activation Link Twice
**What users do:**
- Click activation link from email
- Manually click the same link again in browser
- Now have two different API keys
- Use the old one, which no longer works

**Solution:**
- ✅ Only click activation link **ONCE**
- ✅ If you click twice, use the **NEWEST** API key (from latest response)

---

### ❌ MISTAKE #3: Mixing Up Emails
**What users do:**
- Register multiple test accounts
- Get confused about which email goes with which account
- Use wrong API key for wrong account

**Solution:**
- ✅ Each email address = separate account = separate API key
- ✅ Keep track of which email you registered with

---

## Quick Reference: Which Email Has What?

| Email | Subject | Contents | What To Do |
|-------|---------|----------|------------|
| **Email 1** | "Activate Your Account" | Activation link | Click the link |
| **Email 2** | "Welcome - Your API Key" | **API KEY** ← Use this! | Save the API key |

---

## Visual Guide: The Two Emails

### 📧 Email #1: Activation Email (No API Key)
```
Subject: Activate Your [App Name] Account
─────────────────────────────────────────
Welcome! Please activate your account by 
clicking the button below:

    [Activate Account]  ← Click this

Or copy this link: http://...activate?token=xxx

⚠️ This activation link expires in 48 hours.
```

**What's in it:** Activation link  
**What's NOT in it:** API key  
**What to do:** Click the link

---

### 📧 Email #2: Welcome Email (HAS API Key!)
```
Subject: Welcome to [App Name] - Your API Key
─────────────────────────────────────────────
✅ Account Activated!

Your API Key:
┌─────────────────────────────────────┐
│ cmkDp2TtGnXLc7EoeQOauwRJslD5ZbPv   │  ← THIS IS IT!
└─────────────────────────────────────┘

💾 Save this key securely!
🔒 Never share it or commit to Git
🔄 Use /auth/token to get access tokens

Quick Start:
curl -X POST http://api.example.com/auth/token \
  -d '{"api_key": "cmkDp2TtGnXLc7EoeQOauwRJslD5ZbPv"}'
```

**What's in it:** Your actual API key  
**What to do:** Copy and save the API key  
**What NOT to do:** Delete this email before copying the key!

---

## Testing Workflow

### Correct Testing Flow
```bash
# Step 1: Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response shows:
# "📧 STEP 1: Check your email for the ACTIVATION link..."

# Step 2: Check email, click activation link
# (Opens in browser: http://localhost:8000/auth/activate?token=xxx)

# Step 3: Check email again for WELCOME email with API key

# Step 4: Copy API key from WELCOME email

# Step 5: Get access token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YOUR_API_KEY_FROM_WELCOME_EMAIL"}'

# Step 6: Use access token
curl http://localhost:8000/api/search/simple \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filters": [{"field": "sex", "value": "Male"}], "limit": 25}'
```

---

## Troubleshooting

### "Invalid API key or account not activated"

**Possible causes:**
1. ❌ Using API key from activation email (there isn't one!)
2. ❌ Using old API key after clicking activation link twice
3. ❌ Using API key from different account
4. ❌ Typo in API key

**Solution:**
- ✅ Use API key from **WELCOME email**
- ✅ Check which email address you registered with
- ✅ Make sure you copied the full key (no spaces)

---

### "I can't find my API key!"

**Check these places:**
1. ✅ Welcome email (Subject: "Welcome to [App Name] - Your API Key")
2. ✅ Browser response after clicking activation link (shows API key)
3. ✅ If you lost it, use `/auth/key/reset` to get a new one

---

### "I clicked the activation link twice and now nothing works"

**What happened:**
- First click: Generated API key #1 (sent in welcome email)
- Second click: Generated API key #2 (shown in browser)
- API key #1 is now invalid

**Solution:**
- ✅ Use API key #2 (from the browser response)
- ✅ Check your email for a SECOND welcome email
- ✅ Or request a key reset with `/auth/key/reset`

---

## For Developers: Testing Without Email

If email is NOT configured (development mode):

```bash
# Step 1: Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response includes activation token in "note" field:
# "For testing, activate at: /auth/activate?token=xxx"

# Step 2: Copy token and activate
curl "http://localhost:8000/auth/activate?token=PASTE_TOKEN_HERE"

# Response includes API key:
# {"api_key": "cmkDp2TtGnXLc7EoeQOauwRJslD5ZbPv", ...}

# Step 3: Copy API key and get token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "PASTE_API_KEY_HERE"}'
```

---

## Remember

✅ **Two Emails**:
1. Activation email (has link, NO API key)
2. Welcome email (has API key, after activation)

✅ **One Activation**:
- Click activation link only once
- If clicked twice, use newest API key

✅ **API Key Location**:
- Welcome email (after activation)
- OR activation response in browser
- NOT in activation email!

---

## Need Help?

**Lost your API key?**
```bash
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com"}'
```

**Check system status:**
```bash
curl http://localhost:8000/auth/health
```

**Read full documentation:**
- API_QUICK_REFERENCE.md
- DEPLOYMENT_CHECKLIST.md

---

**Remember:** The API key is in the WELCOME email, not the activation email! 📧

**Pro tip:** If you're testing a lot, keep a text file with your test accounts and their API keys. Your future self will thank you! 📝
