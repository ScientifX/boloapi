@router.get(
    "/signup",
    summary="Sign Up Page",
    description="""
    Display the registration form for new users.
    
    **For Human Users:**
    - Visit this page in a browser to see the registration form
    - Fill in your email address (twice for confirmation)
    - Accept the terms of service
    - Submit to create your account
    
    **Form Features:**
    - Client-side validation
    - Real-time feedback
    - AJAX submission with jQuery modal dialogs
    - Prevents double submission
    
    **API Clients:**
    Use POST /auth/register directly with JSON
    """
)
@limiter.limit(rate_max)
async def signup_page(request: Request):
    """
    Render the signup form page for browser users.
    This is a GET endpoint that shows the HTML form.
    The form submits to POST /auth/register.
    """
    return templates.TemplateResponse(
        "auth/signup.html",
        {"request": request}
    )
