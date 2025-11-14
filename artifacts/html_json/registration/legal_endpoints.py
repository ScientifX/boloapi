# Add these endpoints to app.py

@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit(rate_max)
async def terms_of_service(request: Request):
    """
    Display Terms of Service page.
    Opens in new tab when user clicks checkbox link during signup.
    """
    return templates.TemplateResponse(
        "legal/terms.html",
        {"request": request}
    )

@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit(rate_max)
async def privacy_policy(request: Request):
    """
    Display Privacy Policy page.
    Opens in new tab when user clicks checkbox link during signup.
    """
    return templates.TemplateResponse(
        "legal/privacy.html",
        {"request": request}
    )
