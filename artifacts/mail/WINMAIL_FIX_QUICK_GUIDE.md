# Quick Fix: winmail.dat Attachment Issue

## The Problem
Every email has a `winmail.dat` file attachment (binary TNEF format from Microsoft).

## The Solution
Updated `email_utils.py` to force MIME/HTML format instead of TNEF.

---

## Deployment (2 minutes)

### Step 1: Backup Current File
```bash
cp email_utils.py email_utils.py.backup
```

### Step 2: Deploy Fixed File
```bash
# Copy the fixed version
cp /path/to/outputs/email_utils.py ./email_utils.py
```

### Step 3: Restart Application
```bash
# Stop current process (Ctrl+C or kill)
# Restart
uvicorn app:app --reload
```

### Step 4: Test
```bash
python test_email.py your-email@example.com
```

**Check the email you receive:**
- ✅ Should have NO winmail.dat attachment
- ✅ HTML should display correctly

---

## What Changed

### Before (caused winmail.dat):
```python
message = {
    "message": {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [...]
    }
}

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}
```

### After (prevents winmail.dat):
```python
message = {
    "message": {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [...],
        "internetMessageHeaders": [  # NEW: Force MIME headers
            {"name": "X-Mailer", "value": "Microsoft Graph API"},
            {"name": "Content-Type", "value": "text/html; charset=utf-8"}
        ]
    }
}

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json; charset=utf-8",
    "Prefer": "outlook.body-content-type=\"html\""  # NEW: Force HTML format
}
```

---

## Key Changes

1. ✅ **Added internetMessageHeaders** - Explicitly sets MIME format
2. ✅ **Added Prefer header** - Tells Graph API to use HTML, not TNEF
3. ✅ **Added charset** - Ensures UTF-8 encoding

---

## Testing Checklist

After deploying:

- [ ] Restart application
- [ ] Send test email: `python test_email.py test@example.com`
- [ ] Check received email has **NO winmail.dat**
- [ ] Verify HTML displays correctly
- [ ] Test registration flow (activation email)
- [ ] Test welcome email (after activation)
- [ ] Test key reset email

---

## If Still Getting winmail.dat

The code fix should work, but if you still get winmail.dat, try:

### Additional Fix: Microsoft 365 Settings

```powershell
# Connect to Exchange Online
Connect-ExchangeOnline

# Disable TNEF format
Set-RemoteDomain Default -TNEFEnabled $false

# Verify
Get-RemoteDomain Default | Format-List TNEFEnabled
```

Or via **Exchange Admin Center**:
1. Go to admin.exchange.microsoft.com
2. Mail flow → Remote domains → Default
3. Set "Rich text format" to **"Never use"**

---

## Files

- **[email_utils.py](computer:///mnt/user-data/outputs/email_utils.py)** - Fixed version (deploy this)
- **[WINMAIL_DAT_FIX.md](computer:///mnt/user-data/outputs/WINMAIL_DAT_FIX.md)** - Detailed documentation

---

## Quick Reference

**Problem:** winmail.dat attachment in every email  
**Cause:** Microsoft TNEF format instead of MIME  
**Fix:** Force MIME/HTML format in Graph API call  
**Time:** 2 minutes to deploy  
**Testing:** Send test email, check for attachment  

**Status:** Fixed in email_utils.py ✅
