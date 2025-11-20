"""
Simple CAPTCHA Implementation
Generates random tokens and validates them via httpOnly cookies
"""
import secrets
import hashlib
from typing import Tuple, Optional
from fastapi import Request, Response


def generate_captcha_token() -> Tuple[str, str]:
    """
    Generate a random CAPTCHA token and its hash
    
    Returns:
        Tuple[str, str]: (plain_token, hashed_token)
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def set_captcha_cookie(response: Response, token_hash: str):
    """
    Set the CAPTCHA token hash in an httpOnly cookie
    
    Args:
        response: FastAPI Response object
        token_hash: Hashed CAPTCHA token
    """
    response.set_cookie(
        key="captcha_token",
        value=token_hash,
        httponly=True,
        max_age=300,  # 5 minutes
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )


def validate_captcha(request: Request, submitted_token: str, captcha_checked: bool) -> Tuple[bool, str]:
    """
    Validate CAPTCHA submission
    
    Args:
        request: FastAPI Request object
        submitted_token: Token submitted in form
        captcha_checked: Whether checkbox was checked
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    # Check if checkbox was checked
    if not captcha_checked:
        return False, "Please check the verification box"
    
    # Get stored token hash from cookie
    stored_hash = request.cookies.get("captcha_token")
    if not stored_hash:
        return False, "CAPTCHA token expired or missing"
    
    # Hash the submitted token and compare
    submitted_hash = hashlib.sha256(submitted_token.encode()).hexdigest()
    
    if submitted_hash != stored_hash:
        return False, "Invalid CAPTCHA token"
    
    return True, ""


def clear_captcha_cookie(response: Response):
    """
    Clear the CAPTCHA cookie after validation
    
    Args:
        response: FastAPI Response object
    """
    response.delete_cookie(
        key="captcha_token",
        path="/",
        samesite="lax"
    )
