# Email Integration Flow Diagrams

## 🎯 Complete Authentication Flow with Email

```
┌─────────────────────────────────────────────────────────────────────┐
│                      USER REGISTRATION FLOW                          │
└─────────────────────────────────────────────────────────────────────┘

   User                    API                  Database           Email System
    │                       │                       │                    │
    │  POST /auth/register  │                       │                    │
    ├──────────────────────>│                       │                    │
    │    {email}            │                       │                    │
    │                       │  Check if exists      │                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  User not found       │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  Generate:            │                    │
    │                       │  - activation_token   │                    │
    │                       │  - api_key_hash       │                    │
    │                       │                       │                    │
    │                       │  INSERT user          │                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  user_id returned     │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  send_activation_email()                   │
    │                       ├────────────────────────────────────────────>│
    │                       │                       │                    │
    │                       │                       │  Get OAuth token   │
    │                       │                       │  POST to Graph API │
    │                       │                       │  Send HTML email   │
    │                       │                       │                    │
    │                       │  email_sent=True      │                    │
    │                       │<────────────────────────────────────────────┤
    │                       │                       │                    │
    │  201 Created          │                       │                    │
    │  {user_id, message}   │                       │                    │
    │<──────────────────────┤                       │                    │
    │                       │                       │                    │
    │                                                                     │
    │  [User receives email with activation link]                        │
    │<────────────────────────────────────────────────────────────────────┤
    │                       │                       │                    │

```

## ✉️ Email Activation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ACCOUNT ACTIVATION FLOW                          │
└─────────────────────────────────────────────────────────────────────┘

   User                    API                  Database           Email System
    │                       │                       │                    │
    │  Click email link     │                       │                    │
    │  GET /auth/activate?  │                       │                    │
    │      token=xxx        │                       │                    │
    ├──────────────────────>│                       │                    │
    │                       │                       │                    │
    │                       │  Find user by token   │                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  User found           │                    │
    │                       │  Check: is_active     │                    │
    │                       │  Check: token_expires │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  Generate new API key │                    │
    │                       │  (bcrypt hash)        │                    │
    │                       │                       │                    │
    │                       │  UPDATE user:         │                    │
    │                       │  - is_active=TRUE     │                    │
    │                       │  - api_key_hash       │                    │
    │                       │  - clear token        │                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  Success              │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  send_welcome_email(api_key)               │
    │                       ├────────────────────────────────────────────>│
    │                       │                       │                    │
    │                       │                       │  Get OAuth token   │
    │                       │                       │  Send welcome msg  │
    │                       │                       │  with API key      │
    │                       │                       │                    │
    │                       │  email_sent=True      │                    │
    │                       │<────────────────────────────────────────────┤
    │                       │                       │                    │
    │  200 OK               │                       │                    │
    │  {api_key, message}   │                       │                    │
    │<──────────────────────┤                       │                    │
    │                       │                       │                    │
    │  [Welcome email arrives with API key copy]                         │
    │<────────────────────────────────────────────────────────────────────┤
    │                       │                       │                    │

```

## 🔑 API Key Reset Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      API KEY RESET FLOW                              │
└─────────────────────────────────────────────────────────────────────┘

   User                    API                  Database           Email System
    │                       │                       │                    │
    │  POST /auth/key/reset │                       │                    │
    ├──────────────────────>│                       │                    │
    │    {email}            │                       │                    │
    │                       │                       │                    │
    │                       │  Find user by email   │                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  User found           │                    │
    │                       │  Check: is_active     │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  Generate new API key │                    │
    │                       │  (bcrypt hash)        │                    │
    │                       │                       │                    │
    │                       │  UPDATE user:         │                    │
    │                       │  - api_key_hash       │                    │
    │                       │  (old key invalidated)│                    │
    │                       ├──────────────────────>│                    │
    │                       │                       │                    │
    │                       │  Success              │                    │
    │                       │<──────────────────────┤                    │
    │                       │                       │                    │
    │                       │  send_api_key_email(new_key)               │
    │                       ├────────────────────────────────────────────>│
    │                       │                       │                    │
    │                       │                       │  Get OAuth token   │
    │                       │                       │  Send reset email  │
    │                       │                       │  with new key      │
    │                       │                       │                    │
    │                       │  email_sent=True      │                    │
    │                       │<────────────────────────────────────────────┤
    │                       │                       │                    │
    │  200 OK               │                       │                    │
    │  {api_key, message}   │                       │                    │
    │<──────────────────────┤                       │                    │
    │                       │                       │                    │
    │  [Email arrives with new API key]                                  │
    │<────────────────────────────────────────────────────────────────────┤
    │                       │                       │                    │

```

## 🔐 Microsoft Graph API Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                  OAUTH2 TOKEN ACQUISITION                            │
└─────────────────────────────────────────────────────────────────────┘

  email_utils.py            Azure AD             Microsoft Graph
       │                       │                       │
       │  _get_access_token()  │                       │
       │                       │                       │
       │  Check token cache    │                       │
       │  (valid for 1 hour?)  │                       │
       │                       │                       │
       │  ┌─────────────────┐  │                       │
       │  │ Token expired   │  │                       │
       │  │ or not cached   │  │                       │
       │  └─────────────────┘  │                       │
       │                       │                       │
       │  POST /oauth2/v2.0/token                      │
       ├──────────────────────>│                       │
       │  {                    │                       │
       │    client_id,         │                       │
       │    client_secret,     │                       │
       │    grant_type,        │                       │
       │    scope              │                       │
       │  }                    │                       │
       │                       │                       │
       │                       │  Validate credentials │
       │                       │  Check permissions    │
       │                       │                       │
       │  200 OK               │                       │
       │  {                    │                       │
       │    access_token,      │                       │
       │    expires_in: 3600   │                       │
       │  }                    │                       │
       │<──────────────────────┤                       │
       │                       │                       │
       │  Cache token          │                       │
       │  (expires_at = now    │                       │
       │   + 3540 seconds)     │                       │
       │                       │                       │
       │  POST /users/{email}/sendMail                 │
       ├───────────────────────────────────────────────>│
       │  Authorization: Bearer {token}                │
       │  {                                            │
       │    message: {                                 │
       │      subject,                                 │
       │      body,                                    │
       │      toRecipients                             │
       │    }                                          │
       │  }                                            │
       │                       │                       │
       │                       │  Send email           │
       │                       │                       │
       │  202 Accepted         │                       │
       │<───────────────────────────────────────────────┤
       │                       │                       │
       │  return True          │                       │
       │                       │                       │

```

## 📊 Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SYSTEM COMPONENTS                                │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   FastAPI App    │
│   (app.py)       │
└────────┬─────────┘
         │
         ├─────────────┬──────────────┬────────────────┐
         │             │              │                │
         v             v              v                v
┌────────────┐  ┌────────────┐  ┌──────────┐  ┌─────────────┐
│ router_    │  │ router_    │  │ router_  │  │  middleware │
│ auth.py    │  │ search.py  │  │ etl.py   │  │  jwt_auth   │
└─────┬──────┘  └────────────┘  └──────────┘  └─────────────┘
      │
      ├─────────────┬──────────────┬────────────────┐
      │             │              │                │
      v             v              v                v
┌────────────┐  ┌────────────┐  ┌──────────┐  ┌─────────────┐
│ email_     │  │ security_  │  │ jwt_     │  │   dbconfig  │
│ utils.py   │  │ utils.py   │  │ utils.py │  │             │
└─────┬──────┘  └────────────┘  └──────────┘  └──────┬──────┘
      │                                                │
      │                                                │
      v                                                v
┌────────────────────────────┐              ┌────────────────┐
│  Microsoft Graph API       │              │  PostgreSQL    │
│  (Email Service)           │              │  Database      │
│                            │              │                │
│  • OAuth2 Authentication   │              │  • tbl_users   │
│  • sendMail endpoint       │              │  • tbl_wanted  │
│  • Token caching           │              │  • tbl_logs    │
└────────────────────────────┘              └────────────────┘

```

## 🔄 Email State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                    USER ACCOUNT STATES                               │
└─────────────────────────────────────────────────────────────────────┘

           ┌─────────────────────┐
           │   Initial State     │
           │   (No account)      │
           └──────────┬──────────┘
                      │
                      │ POST /auth/register
                      │ (Email sent)
                      v
           ┌─────────────────────┐
           │   Registered        │
           │   is_active=FALSE   │
           │   has activation    │
           │   token (48hr TTL)  │
           └──────────┬──────────┘
                      │
                      │ GET /auth/activate?token=xxx
                      │ (Welcome email sent)
                      v
           ┌─────────────────────┐
           │   Active            │
           │   is_active=TRUE    │
           │   has API key hash  │
           │   can request tokens│
           └──────────┬──────────┘
                      │
                      │ POST /auth/key/reset
                      │ (Reset email sent)
                      │
                      │ (Same state, new key)
                      │
                      └──────────────┐
                                     │
                                     v
                          ┌─────────────────────┐
                          │   Active (new key)  │
                          │   Old key invalid   │
                          │   All old tokens    │
                          │   invalid           │
                          └─────────────────────┘

```

## 📈 Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│               EMAIL SENDING ERROR HANDLING                           │
└─────────────────────────────────────────────────────────────────────┘

  send_activation_email()
          │
          v
  ┌─────────────────┐
  │ Check config    │
  │ is_configured()?│
  └────────┬────────┘
           │
           ├──NO──> Log warning
           │        Return False
           │        Continue (graceful degradation)
           │
           v
  ┌─────────────────┐
  │ Get OAuth token │
  │ (with caching)  │
  └────────┬────────┘
           │
           ├──FAIL──> Log error
           │          Return False
           │          User sees: "Email disabled"
           │
           v
  ┌─────────────────┐
  │ POST to Graph   │
  │ /sendMail       │
  └────────┬────────┘
           │
           ├──FAIL──> Log error with details
           │          Return False
           │          User sees: "Check email" anyway
           │
           v
  ┌─────────────────┐
  │ Success!        │
  │ Log success     │
  │ Return True     │
  └─────────────────┘

```

## 🎯 Token Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    JWT TOKEN LIFECYCLE                               │
└─────────────────────────────────────────────────────────────────────┘

  User has API Key (from email)
          │
          v
  POST /auth/token
  {api_key: "xxx"}
          │
          v
  ┌─────────────────┐
  │ Find user       │
  │ Verify key hash │
  │ (bcrypt check)  │
  └────────┬────────┘
           │
           v
  ┌─────────────────┐
  │ Generate JWT    │
  │ - user_id       │
  │ - role          │
  │ - exp: 1 hour   │
  │ Signed with     │
  │ secret key      │
  └────────┬────────┘
           │
           v
  Return JWT token
          │
          │
  User stores token
          │
          v
  ┌─────────────────┐
  │ Make API calls  │
  │ Authorization:  │
  │ Bearer {token}  │
  └────────┬────────┘
           │
           ├───────────────────────┐
           v                       v
  ┌─────────────────┐    ┌─────────────────┐
  │ Valid token     │    │ Expired/Invalid │
  │ (< 1 hour old)  │    │ (> 1 hour old)  │
  │                 │    │                 │
  │ → Process req   │    │ → 401 Error     │
  │ → Return data   │    │ → Get new token │
  └─────────────────┘    └─────────────────┘

```

---

**Legend:**
- `│ ├ └ ┌ ┐ ─ v >` : Flow direction
- `┌─────┐` : Process/State
- `─>` : Action/Event
- `<─` : Return/Response

These diagrams show the complete flow of email integration with your authentication system!
