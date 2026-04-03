"""
Feedback Router - Beta User Feedback Form
Provides a simple three-question feedback form available only when BETA_MODE is active.
Authenticated users may submit as many unique responses as they like; exact duplicate
content from the same user is rejected via a SHA-256 content hash stored in tbl_feedback.
Successful submissions trigger a formatted internal email to the support address.
"""
import hashlib
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import DB_CONFIG, APP_GLOBALS, BETA_MODE
from auth_jwt import require_browser_auth
from utils_captcha import (
    generate_captcha_token,
    set_captcha_cookie,
    validate_captcha,
    clear_captcha_cookie,
)
from utils_email import send_feedback_email

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(APP_GLOBALS)

router = APIRouter(prefix="/v1/feedback", tags=["Feedback"])


# ============================================================================
# DATABASE HELPER
# ============================================================================

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# HELPERS
# ============================================================================

def _build_content_hash(user_id: str, liked: str, disliked: str, improve: str) -> str:
    """
    SHA-256 of the concatenation of user_id and the three response fields
    (after stripping whitespace).  Identical content from the same user
    always produces the same hash, enabling duplicate detection.
    """
    raw = "|".join([
        user_id.strip(),
        (liked or "").strip(),
        (disliked or "").strip(),
        (improve or "").strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _store_feedback(user_id: str, user_email: str, liked: str, disliked: str,
                    improve: str, content_hash: str) -> bool:
    """
    Insert a feedback record.  Returns True on success, False on duplicate.
    Raises on unexpected DB errors.
    """
    sql = """
        INSERT INTO base.tbl_feedback
            (user_id, user_email, liked, disliked, improve, content_hash)
        VALUES
            (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, content_hash) DO NOTHING
        RETURNING feedback_id
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, user_email,
                              (liked or "").strip() or None,
                              (disliked or "").strip() or None,
                              (improve or "").strip() or None,
                              content_hash))
            result = cur.fetchone()
            conn.commit()
    return result is not None   # None means ON CONFLICT suppressed the insert


# ============================================================================
# ROUTES
# ============================================================================

@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def feedback_form(
    request: Request,
    current_user: Optional[dict] = Depends(require_browser_auth()),
):
    """
    Display the beta feedback form.
    Redirects to login if not authenticated, to home if beta mode is off.
    """
    if not current_user:
        return RedirectResponse(url="/v1/auth/login", status_code=303)

    if not BETA_MODE:
        return RedirectResponse(url="/", status_code=303)

    captcha_token, captcha_hash = generate_captcha_token()
    response = templates.TemplateResponse(
        "auth/feedback.html",
        {
            "request": request,
            "captcha_token": captcha_token,
            "error_message": None,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user_role": request.state.user_role,
        },
    )
    set_captcha_cookie(response, captcha_hash)
    return response


@router.post("/submit", response_class=HTMLResponse, include_in_schema=False)
async def feedback_submit(
    request: Request,
    current_user: Optional[dict] = Depends(require_browser_auth()),
    liked: str = Form(default=""),
    disliked: str = Form(default=""),
    improve: str = Form(default=""),
    captcha_token: str = Form(...),
    captcha_checked: bool = Form(default=False),
):
    """
    Process a feedback form submission.
    Validates captcha, checks for duplicate content, stores the record,
    and fires an internal notification email to the support address.
    On success redirects to the thank-you confirmation page.
    On error re-renders the form with an inline message.
    """
    if not current_user:
        return RedirectResponse(url="/v1/auth/login", status_code=303)

    if not BETA_MODE:
        return RedirectResponse(url="/", status_code=303)

    # ---- helper to re-render form with an error message ----
    def render_form_error(message: str):
        captcha_token_new, captcha_hash_new = generate_captcha_token()
        resp = templates.TemplateResponse(
            "auth/feedback.html",
            {
                "request": request,
                "captcha_token": captcha_token_new,
                "error_message": message,
                "liked": liked,
                "disliked": disliked,
                "improve": improve,
                "user_authenticated": request.state.user_authenticated,
                "user_email": request.state.user_email,
                "user_display_name": request.state.user_display_name,
                "user_role": request.state.user_role,
            },
            status_code=400,
        )
        set_captcha_cookie(resp, captcha_hash_new)
        return resp

    # ---- at least one field must be non-empty ----
    if not any([(liked or "").strip(), (disliked or "").strip(), (improve or "").strip()]):
        return render_form_error("Please fill in at least one feedback field before submitting.")

    # ---- captcha ----
    captcha_valid, captcha_error = validate_captcha(request, captcha_token, captcha_checked)
    if not captcha_valid:
        return render_form_error(captcha_error)

    # ---- duplicate detection ----
    user_id = current_user["user_id"]
    user_email = current_user.get("email", "")
    content_hash = _build_content_hash(user_id, liked, disliked, improve)

    try:
        stored = _store_feedback(user_id, user_email, liked, disliked, improve, content_hash)
    except Exception as exc:
        logger.error(f"[feedback] DB error for user {user_id}: {exc}")
        return render_form_error("An error occurred while saving your feedback. Please try again.")

    if not stored:
        # Exact duplicate
        return render_form_error(
            "This feedback appears identical to a previous submission from your account. "
            "Feel free to update your responses and submit again."
        )

    # ---- clear captcha cookie ----
    response_redirect = RedirectResponse(url="/v1/feedback/thanks", status_code=303)
    clear_captcha_cookie(response_redirect)

    # ---- send email (non-blocking best-effort) ----
    try:
        send_feedback_email(
            user_email=user_email,
            user_id=user_id,
            liked=liked,
            disliked=disliked,
            improve=improve,
        )
    except Exception as exc:
        logger.error(f"[feedback] Email send failed for user {user_id}: {exc}")
        # Do not fail the user-facing flow if email breaks

    return response_redirect


@router.get("/thanks", response_class=HTMLResponse, include_in_schema=False)
async def feedback_thanks(
    request: Request,
    current_user: Optional[dict] = Depends(require_browser_auth()),
):
    """Thank-you confirmation page shown after a successful submission."""
    if not current_user:
        return RedirectResponse(url="/v1/auth/login", status_code=303)

    if not BETA_MODE:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "auth/feedback_success.html",
        {
            "request": request,
            "user_authenticated": request.state.user_authenticated,
            "user_email": request.state.user_email,
            "user_display_name": request.state.user_display_name,
            "user_role": request.state.user_role,
        },
    )
