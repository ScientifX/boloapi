@router.post(
    "/register",
    summary="Register New User",
    description="""
    Register a new user account with email.
    
    **Process:**
    1. Submit a valid email address
    2. Receive confirmation with user_id
    3. Check your email for activation link
    4. Click link to activate and receive API key
    
    **Note:** If email already exists and is inactive, a new activation email will be sent.
    If already active, you'll be informed to use the existing account.
    
    **Email:** Activation email will be sent if email is configured. Otherwise, activation token 
    will be provided in response for testing purposes.
    
    **Content Negotiation:**
    - Browser requests: Returns HTML page with success/error message
    - API requests (Accept: application/json): Returns JSON response
    """
)
@limiter.limit(rate_max)
async def register(request: Request, register_req: RegisterRequest) -> Response:
    """
    Register a new user account.
    Sends activation email with secure token if email is configured.
    Returns HTML for browsers, JSON for API clients (content negotiation).
    """
    try:
        email = register_req.email
        
        # Check if user already exists
        existing_user = get_user_by_email(email)
        
        if existing_user:
            if existing_user['is_active']:
                return render_error(
                    request=request,
                    template_name="auth/register_error.html",
                    error_message="Email already registered and active. Use /auth/token to get access token or /auth/key/reset to reset your API key.",
                    error_type="already_registered",
                    context={"email": email, "app_base_url": EmailConfig.APP_BASE_URL},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            else:
                # User exists but not activated - resend activation
                user_id = existing_user['user_id']
                activation_token = generate_activation_token()
                activation_expires = datetime.now(timezone.utc) + timedelta(hours=1)
                
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE tbl_users 
                            SET activation_token = %s,
                                activation_expires_at = %s,
                                updated_at = NOW()
                            WHERE user_id = %s
                            """,
                            (activation_token, activation_expires.replace(tzinfo=None), user_id)
                        )
                        conn.commit()
                
                # Send activation email if configured
                email_sent = False
                if EmailConfig.is_configured():
                    try:
                        email_sent = send_activation_email(email, activation_token)
                        if email_sent:
                            logger.info(f"Activation email resent to {email}")
                        else:
                            logger.warning(f"Failed to send activation email to {email}")
                    except Exception as e:
                        logger.error(f"Error sending activation email to {email}: {str(e)}")
                else:
                    logger.warning("Email not configured - activation email not sent")
                
                # Prepare response with content negotiation
                template_context = {
                    "request": request,
                    "user_id": str(user_id),
                    "email": email,
                    "email_sent": email_sent,
                    "activation_token": activation_token if not email_sent else None,
                    "app_base_url": EmailConfig.APP_BASE_URL,
                    "is_resend": True
                }
                
                json_data = {
                    "message": "Activation email resent" if email_sent else "Registration record updated (email disabled)",
                    "user_id": str(user_id),
                    "email": email,
                    "note": "Check your email for the activation link." if email_sent else f"Email not configured. For testing, activate at: /auth/activate?token={activation_token}",
                    "email_sent": email_sent
                }
                
                return render_or_json(
                    request=request,
                    template_name="auth/register_success.html",
                    context=template_context,
                    json_data=json_data,
                    status_code=status.HTTP_200_OK
                )
        
        # Create new user
        api_key, api_key_hash = generate_api_key_and_hash()
        activation_token = generate_activation_token()
        activation_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO tbl_users (
                        email, role, api_key_hash, activation_token, activation_expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING user_id
                    """,
                    (email, UserRole.BASIC.value, api_key_hash, activation_token, activation_expires.replace(tzinfo=None))
                )
                result = cur.fetchone()
                user_id = result['user_id']
                conn.commit()
        
        logger.info(f"New user registered: {email} (user_id: {user_id})")
        
        # Send activation email if configured
        email_sent = False
        if EmailConfig.is_configured():
            try:
                email_sent = send_activation_email(email, activation_token)
                if email_sent:
                    logger.info(f"Activation email sent to {email}")
                else:
                    logger.warning(f"Failed to send activation email to {email}")
            except Exception as e:
                logger.error(f"Error sending activation email to {email}: {str(e)}")
        else:
            logger.warning("Email not configured - activation email not sent")
        
        # Prepare response with content negotiation
        template_context = {
            "request": request,
            "user_id": str(user_id),
            "email": email,
            "email_sent": email_sent,
            "activation_token": activation_token if not email_sent else None,
            "app_base_url": EmailConfig.APP_BASE_URL,
            "is_resend": False
        }
        
        json_data = {
            "message": "Registration successful. Check your email for activation link." if email_sent else "Registration successful (email disabled)",
            "user_id": str(user_id),
            "email": email,
            "note": (
                "📧 STEP 1: Check your email for the ACTIVATION link and click it. "
                "📧 STEP 2: After clicking, you'll receive a WELCOME email with your API key. "
                "Use the API key from the WELCOME email (not the activation email)."
            ) if email_sent else f"For testing, activate at: /auth/activate?token={activation_token}",
            "email_sent": email_sent
        }
        
        return render_or_json(
            request=request,
            template_name="auth/register_success.html",
            context=template_context,
            json_data=json_data,
            status_code=status.HTTP_201_CREATED
        )
        
    except HTTPException as e:
        # Convert HTTPException to rendered error
        return render_error(
            request=request,
            template_name="auth/register_error.html",
            error_message=e.detail,
            error_type="Registration Error",
            context={"app_base_url": EmailConfig.APP_BASE_URL},
            status_code=e.status_code
        )
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return render_error(
            request=request,
            template_name="auth/register_error.html",
            error_message=f"Registration failed: {str(e)}",
            error_type="Server Error",
            context={"app_base_url": EmailConfig.APP_BASE_URL},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
