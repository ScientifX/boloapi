"""
ADD THESE ROUTES TO YOUR app.py FILE

Location: Add after your existing routes, before the validation functions section.
Look for the comment "# Validation functions" in your app.py and add this code BEFORE it.
"""

# ============================================================================
# STATIC CONTENT PAGES (More permissive rate limiting)
# ============================================================================

@app.get("/about", response_class=HTMLResponse, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
async def about_page(request: Request):
    """About Scientifics.io and the FBI Wanted API"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/about.html",
        {
            "request": request,
            "current_role": current_role.value
        }
    )

@app.get("/privacy", response_class=HTMLResponse, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
async def privacy_page(request: Request):
    """Privacy Policy"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/privacy.html",
        {
            "request": request,
            "current_role": current_role.value,
            "last_updated": "November 2024"  # Update this date as needed
        }
    )

@app.get("/terms", response_class=HTMLResponse, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
async def terms_page(request: Request):
    """Terms of Service"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/terms.html",
        {
            "request": request,
            "current_role": current_role.value,
            "last_updated": "November 2024"  # Update this date as needed
        }
    )

@app.get("/contact", response_class=HTMLResponse, tags=["Static Pages"])
@limiter.limit("30/minute")  # More permissive
async def contact_page(request: Request):
    """Contact Information"""
    current_role = get_current_role(request)
    return templates.TemplateResponse(
        "static/contact.html",
        {
            "request": request,
            "current_role": current_role.value,
            "support_email": "support@scientifics.io",  # CHANGE TO YOUR EMAIL
            "business_email": "contact@scientifics.io"  # CHANGE TO YOUR EMAIL
        }
    )
