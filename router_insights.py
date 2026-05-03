"""
Insights Router
Provides the Insights page: pre-built analytical query templates for no-code users.
Organised into four analytical categories: Descriptive, Diagnostic, Predictive, Prescriptive.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import APP_GLOBALS
from auth import UserRole
from auth_jwt import require_browser_auth

logger = logging.getLogger(__name__)

rate_max = "3000/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

router = APIRouter(prefix="/v1/auth", tags=["Insights"])

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(APP_GLOBALS)

# Role-based limits matching router_search.py behaviour
_ROLE_MAX_LIMIT = {
    "basic":   25,
    "premium": 5000,
    "admin":   5000,
}

_ROLE_FORMATS = {
    "basic":   ["json"],
    "premium": ["json", "csv", "txt", "xml"],
    "admin":   ["json", "csv", "txt", "xml"],
}


@router.get(
    "/insights",
    response_class=HTMLResponse,
    summary="Insights Page",
    description="Pre-built analytical query templates organised by category.",
    include_in_schema=False
)
@limiter.limit(rate_max)
async def insights_page(
    request: Request,
    current_user: Optional[dict] = Depends(require_browser_auth(UserRole.BASIC))
):
    """
    Insights Dashboard.
    Requires authentication - redirects to login if not authenticated.
    """
    if not current_user:
        return RedirectResponse(
            url="/v1/auth/login?next=/v1/auth/insights",
            status_code=303
        )

    user_role = (request.state.user_role or "basic").lower()
    max_limit        = _ROLE_MAX_LIMIT.get(user_role, 25)
    available_formats = _ROLE_FORMATS.get(user_role, ["json"])

    return templates.TemplateResponse(
        "auth/insights.html",
        {
            "request":          request,
            "user_authenticated": request.state.user_authenticated,
            "user_email":       request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user_role":        user_role,
            "max_limit":        max_limit,
            "available_formats": available_formats,
        }
    )
