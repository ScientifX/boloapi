# JWT Token Behavior - Multiple Valid Tokens

## Question: Can I have multiple valid access tokens at once?

**Answer:** YES! This is normal JWT behavior and is by design.

---

## How It Works

### JWT Tokens are Stateless

Unlike traditional session-based auth, JWT tokens:
- ✅ Are self-contained (all info is in the token)
- ✅ Don't require server-side storage
- ✅ Are validated by signature, not database lookup
- ✅ Remain valid until they expire

### Timeline Example

```
10:00 AM - Request token → Get Token #1 (expires 11:00 AM)
10:15 AM - Make API call with Token #1 → ✅ Works
10:30 AM - Request token → Get Token #2 (expires 11:30 AM)
10:45 AM - Make API call with Token #1 → ✅ Still works!
10:45 AM - Make API call with Token #2 → ✅ Also works!
11:05 AM - Make API call with Token #1 → ❌ Expired
11:05 AM - Make API call with Token #2 → ✅ Still works
11:35 AM - Make API call with Token #2 → ❌ Expired
```

**Key Point:** Both tokens are valid simultaneously until their individual expiration times.

---

## Why This Design is Good

### 1. Scalability
- No database lookup needed per request
- Server can be stateless
- Easy to horizontally scale
- No session synchronization needed

### 2. Flexibility
- Users can have multiple devices/apps
- Tokens can have different expiration times
- No "kicked out" when getting new token
- Graceful token rotation possible

### 3. Performance
- No database hit per API request
- Faster request processing
- Lower database load

---

## Security Considerations

### Q: Isn't it dangerous to have multiple valid tokens?

**A:** No, because:

1. **Short-lived:** Tokens expire after 1 hour (configurable)
2. **Signed:** Tokens can't be forged or modified
3. **API key required:** Must have valid API key to get token
4. **Key reset invalidates:** If you reset API key, old tokens become invalid

### Q: What if my API key is compromised?

**A:** Reset your API key immediately:

```bash
curl -X POST http://localhost:8000/auth/key/reset \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com"}'
```

This immediately invalidates:
- ✅ The old API key
- ✅ ALL tokens generated from that API key

### Q: How do tokens get invalidated?

Tokens become invalid when:
1. **Time expires** - After 1 hour (default)
2. **API key reset** - All tokens from old key are invalid
3. **Account deactivated** - All tokens become invalid

---

## Token Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User requests token with API key                         │
│    POST /auth/token {"api_key": "..."}                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Server generates JWT token                               │
│    - Signs with secret key                                  │
│    - Sets expiration (now + 1 hour)                         │
│    - Includes user_id and role                              │
│    - Does NOT store token in database                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. User makes API requests with token                       │
│    Authorization: Bearer {token}                            │
│    - Server verifies signature                              │
│    - Checks expiration                                      │
│    - Extracts user_id and role                              │
│    - No database lookup needed                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Token expires after 1 hour                               │
│    - User must request new token                            │
│    - Old token no longer accepted                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Comparison: JWT vs Session-Based Auth

| Feature | JWT (Our System) | Session-Based |
|---------|------------------|---------------|
| Multiple valid tokens | ✅ Yes | ❌ Usually no |
| Server-side storage | ❌ Not needed | ✅ Required |
| Scalability | ✅ Excellent | ⚠️ More complex |
| Stateless | ✅ Yes | ❌ No |
| Token invalidation | Via expiration or key reset | Via session deletion |
| Database load | ✅ Lower | ⚠️ Higher |

---

## Best Practices

### For Users

1. **Request new token when needed**
   - Don't request new token for every API call
   - Request when old token expires
   - Cache token for its lifetime

2. **Handle expiration gracefully**
   ```javascript
   async function makeApiCall() {
     try {
       return await fetch(url, { headers: { Authorization: `Bearer ${token}` }});
     } catch (error) {
       if (error.status === 401) {
         // Token expired, get new one
         token = await getNewToken();
         return await fetch(url, { headers: { Authorization: `Bearer ${token}` }});
       }
     }
   }
   ```

3. **Store tokens securely**
   - Don't commit to Git
   - Use environment variables
   - Clear from memory when done

### For API Developers

1. **Set appropriate expiration**
   - Default: 1 hour (good balance)
   - Too short: Annoying for users
   - Too long: Security risk

2. **Monitor token usage**
   - Track token generation rate
   - Alert on unusual patterns
   - Log authentication failures

3. **Provide clear error messages**
   ```json
   {
     "detail": "Token has expired",
     "error_code": "TOKEN_EXPIRED",
     "action": "Request new token from /auth/token"
   }
   ```

---

## Configuration

### Change Token Expiration Time

In your `.env` or environment:
```bash
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60  # Default: 1 hour
```

Options:
- **15 minutes**: High security, more frequent refresh
- **60 minutes**: Good balance (default)
- **480 minutes (8 hours)**: Long-lived, less secure

### Check Current Settings

```bash
curl http://localhost:8000/auth/
```

Response includes:
```json
{
  "token_info": {
    "type": "JWT Bearer",
    "expiration": "60 minutes",
    "usage": "Authorization: Bearer {access_token}"
  }
}
```

---

## Common Scenarios

### Scenario 1: Mobile App + Web App
```
User logs in on mobile → Gets token A
User logs in on web → Gets token B
Both tokens work simultaneously ✅
```

### Scenario 2: Token Refresh Strategy
```
10:00 - Get token (expires 11:00)
10:50 - Proactively get new token (expires 11:50)
10:55 - Use new token
11:05 - Old token expired, but already using new one
```

### Scenario 3: Development Testing
```
Terminal 1: Get token, make requests
Terminal 2: Get another token, make requests
Both work at the same time ✅
```

---

## Troubleshooting

### "Why does my old token still work after getting a new one?"

**Answer:** This is normal! Tokens are valid until they expire, not until you get a new one.

**If you need old tokens to stop working:**
1. Wait for expiration (1 hour)
2. OR reset your API key (invalidates all tokens)

### "I want only one token at a time"

**Options:**
1. **Implement token blacklist** (requires database)
2. **Use shorter expiration** (e.g., 15 minutes)
3. **Accept that multiple tokens exist** (recommended)

The stateless nature of JWT makes single-token enforcement complex and defeats the scalability benefits.

---

## Summary

✅ **Multiple valid tokens = Normal JWT behavior**  
✅ **Tokens expire after set time (default: 1 hour)**  
✅ **Stateless = Better scalability**  
✅ **Key reset = All tokens from that key become invalid**  

This design is intentional and provides the best balance of:
- Security (short-lived tokens)
- Performance (no database lookups)
- Scalability (stateless design)
- User experience (flexible token usage)

---

**Bottom Line:** Having multiple valid access tokens is expected behavior and is a feature, not a bug! 🎯
