# Winmail.dat Attachment Fix

## The Problem

Every email sent includes a `winmail.dat` file attachment, which:
- ❌ Looks suspicious to users (security concern)
- ❌ Contains binary TNEF data
- ❌ Can't be opened by non-Outlook clients
- ❌ Is completely unnecessary

## What is winmail.dat?

`winmail.dat` is created when Microsoft Outlook/Exchange sends email in **TNEF** (Transport Neutral Encapsulation Format) instead of standard **MIME** format.

### Why It Happens with Graph API

Microsoft Graph API, when used with Microsoft 365, can default to TNEF format under certain conditions, especially when:
- The sender uses Outlook/Exchange
- Rich text formatting is involved
- Certain email properties aren't explicitly set

## The Solution

### Code Changes in email_utils.py

#### 1. Add Internet Message Headers
```python
"internetMessageHeaders": [
    {
        "name": "X-Mailer",
        "value": "Microsoft Graph API"
    },
    {
        "name": "Content-Type", 
        "value": "text/html; charset=utf-8"
    }
]
```

#### 2. Add Prefer Header
```python
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json; charset=utf-8",
    "Prefer": "outlook.body-content-type=\"html\""  # Forces HTML/MIME format
}
```

### Updated send_email() Method

The key changes:
1. ✅ Added `internetMessageHeaders` to message structure
2. ✅ Added `Prefer` header to force HTML format
3. ✅ Added charset to Content-Type
4. ✅ Updated logging to confirm MIME format

---

## Additional Configuration (If Code Fix Doesn't Work)

If the code changes alone don't resolve the issue, you may need to adjust Microsoft 365 settings:

### Option 1: Exchange Admin Center Settings

1. Go to **Exchange Admin Center** (admin.exchange.microsoft.com)
2. Navigate to **Mail flow** → **Remote domains**
3. Select **Default**
4. Under **Message format**, set:
   - ✅ **Message format**: HTML or Plain text
   - ✅ **Rich text format**: Never use
5. Save changes

### Option 2: PowerShell Configuration

```powershell
# Connect to Exchange Online
Connect-ExchangeOnline

# Get current remote domain settings
Get-RemoteDomain Default | Format-List TNEFEnabled

# Disable TNEF for default remote domain
Set-RemoteDomain Default -TNEFEnabled $false

# Verify the change
Get-RemoteDomain Default | Format-List TNEFEnabled
```

### Option 3: Per-User Outlook Settings

If only specific users are affected:

1. Open **Outlook** (desktop app)
2. Go to **File** → **Options** → **Mail**
3. Scroll to **Message format**
4. Select **HTML** or **Plain Text**
5. Under **Internet Format**, choose:
   - ✅ **Convert to HTML format**
   - ✅ **Convert to Plain Text format**
   - ❌ NOT "Let Outlook decide" or "Send in Outlook Rich Text Format"

---

## Testing the Fix

### Test 1: Send Test Email

```bash
python test_email.py your-email@domain.com
```

Check the received email:
- ✅ Should have NO winmail.dat attachment
- ✅ HTML content should display correctly
- ✅ All formatting should be preserved

### Test 2: Register New User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "newuser@example.com"}'
```

Check activation email:
- ✅ No winmail.dat
- ✅ Activation button works
- ✅ HTML displays properly

### Test 3: Check Email Headers

When you receive the email, view the **raw email source** or headers:

**Good (MIME format):**
```
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: quoted-printable
```

**Bad (TNEF format):**
```
Content-Type: application/ms-tnef
Content-Transfer-Encoding: binary
```

---

## Verification Checklist

After applying the fix:

- [ ] Updated `email_utils.py` with new code
- [ ] Restarted application
- [ ] Sent test email via `test_email.py`
- [ ] Checked received email has NO winmail.dat
- [ ] Verified HTML displays correctly
- [ ] Tested activation email flow
- [ ] Tested welcome email
- [ ] Tested key reset email

---

## Understanding the Fix

### What We Changed

**Before (causes winmail.dat):**
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

**After (prevents winmail.dat):**
```python
message = {
    "message": {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [...],
        "internetMessageHeaders": [
            {"name": "X-Mailer", "value": "Microsoft Graph API"},
            {"name": "Content-Type", "value": "text/html; charset=utf-8"}
        ]
    }
}

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json; charset=utf-8",
    "Prefer": "outlook.body-content-type=\"html\""
}
```

### Why This Works

1. **internetMessageHeaders**: Explicitly sets MIME headers in the outgoing message
2. **Prefer header**: Tells Microsoft Graph to use HTML/MIME format, not TNEF
3. **charset=utf-8**: Ensures proper encoding without TNEF wrapper

---

## Alternative Solutions (If Above Doesn't Work)

### Solution A: Use SMTP Instead of Graph API

If you can't get Graph API to stop sending winmail.dat, consider using SMTP:

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email_smtp(to_addr, subject, html_body):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = 'noreply@yourdomain.com'
    msg['To'] = to_addr
    msg['Content-Type'] = 'text/html; charset=utf-8'
    
    html_part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(html_part)
    
    with smtplib.SMTP('smtp.office365.com', 587) as server:
        server.starttls()
        server.login('user@domain.com', 'password')
        server.send_message(msg)
```

**Pros:**
- ✅ Complete control over MIME format
- ✅ No winmail.dat issues
- ✅ Standard protocol

**Cons:**
- ⚠️ Requires SMTP credentials
- ⚠️ More complex authentication

### Solution B: Third-Party Email Service

Use services that don't have this issue:
- SendGrid
- Mailgun
- Amazon SES
- Postmark

---

## Monitoring

### Check Email Delivery

After deploying the fix, monitor:

```sql
-- Check recent email sends (if you add logging)
SELECT 
    email,
    created_at,
    'Check for winmail.dat' as note
FROM tbl_users
WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY created_at DESC;
```

### User Reports

Ask test users to confirm:
1. No winmail.dat attachment present
2. HTML displays correctly
3. All links work
4. No security warnings

---

## Troubleshooting

### "Still getting winmail.dat after code fix"

**Possible causes:**
1. Code not deployed (restart application)
2. Microsoft 365 tenant settings override
3. Sender mailbox configured for TNEF
4. Recipient mailbox requesting TNEF

**Solutions:**
1. Verify code changes are active:
   ```python
   # Check logs for "MIME format" message
   # Should see: "Successfully sent email to user@example.com (MIME format)"
   ```

2. Check Microsoft 365 settings (see Option 1 above)

3. Try PowerShell configuration (see Option 2 above)

### "Some users get winmail.dat, others don't"

This is recipient-dependent. The fix should work for all, but if not:

1. Check if affected users are on Exchange/Outlook
2. Verify remote domain settings
3. Consider SMTP alternative for affected domains

### "HTML doesn't display in some email clients"

This is different from winmail.dat. If HTML fails:

1. Check email client supports HTML
2. Verify HTML is valid
3. Use simpler HTML (avoid complex CSS)
4. Provide plain text alternative

---

## Summary

### The Fix

✅ **Updated email_utils.py** with:
- internetMessageHeaders
- Prefer header
- Proper Content-Type

### Testing

```bash
# Deploy fix
cp email_utils.py /path/to/your/project/
uvicorn app:app --reload

# Test it
python test_email.py your-email@example.com

# Check received email
# Should have NO winmail.dat attachment
```

### If Still Having Issues

1. Check Microsoft 365 admin settings
2. Run PowerShell commands
3. Consider SMTP alternative
4. Contact Microsoft support

---

## Files Updated

- **[email_utils.py](computer:///mnt/user-data/outputs/email_utils.py)** - Fixed send_email() method

## References

- [Microsoft Graph API sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- [TNEF Format Documentation](https://learn.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxtnef)
- [Exchange Remote Domains](https://learn.microsoft.com/en-us/exchange/mail-flow-best-practices/remote-domains/remote-domains)

---

**The winmail.dat issue should now be resolved! 🎉**
