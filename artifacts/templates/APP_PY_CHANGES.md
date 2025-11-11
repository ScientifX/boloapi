# app.py Changes Required

## What to Change

Only **2 small changes** needed in your existing `app.py`:

### Change 1: Add Import
Add `StaticFiles` to your FastAPI imports:

```python
# BEFORE:
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

# AFTER:
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles  # <-- ADD THIS LINE
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
```

### Change 2: Mount Static Files
Add this line right after `app = FastAPI(...)`:

```python
# BEFORE:
app = FastAPI(
    title="Bolo API",
    description="Bolo API",
    version="2.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# AFTER:
app = FastAPI(
    title="Bolo API",
    description="Bolo API",
    version="2.0.0"
)

# Mount static files (CSS, images, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")  # <-- ADD THIS LINE

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

## That's It!

Those 2 changes enable:
- CSS file serving from `/static/css/main.css`
- Logo serving from `/static/images/logo.png`
- Any future static assets (JS, fonts, etc.)

## Complete Updated Section

Here's the complete section with both changes:

```python
import httpx, json, re

# FastAPI setup
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles  # ← ADDED
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Rate limiting libraries
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from lookups import COUNTRIES, STATES
from auth import (
    UserRole, 
    get_current_role, 
    set_user_role, 
    require_role, 
    MANUAL_TEST_ROLE,
    SESSION_ROLE_KEY, 
    ROLE_HIERARCHY
)

import router_etl
import router_search
import router_auth 

templates = Jinja2Templates(directory="templates")

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Initialize rate limiter
rate_max = "10/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

app = FastAPI(
    title="Bolo API",
    description="Bolo API",
    version="2.0.0"
)

# Mount static files (CSS, images, etc.)  ← ADDED
app.mount("/static", StaticFiles(directory="static"), name="static")  # ← ADDED

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ... rest of your app.py continues unchanged ...
```

## Testing

After making these changes, test that static files work:

```bash
# Start server
uvicorn app:app --reload

# Test CSS loads
curl http://localhost:8000/static/css/main.css

# Test logo (after you add it)
curl http://localhost:8000/static/images/logo.png

# Should get file content, not 404
```

## Notes

- The `directory="static"` refers to `/static/` folder in your project root
- Files are served at `/static/*` URL path
- Templates automatically use `url_for('static', path='/css/main.css')` to reference static files
- No need to change any templates - they're already set up correctly

Done! Those 2 lines are all you need to add to your existing `app.py`.
