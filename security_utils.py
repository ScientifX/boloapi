"""
Security utilities for password/API key hashing and token generation
Uses bcrypt for hashing and secrets for cryptographically secure random generation
"""
import secrets
import string
import bcrypt
from typing import Tuple

def generate_api_key(length: int = 32) -> str:
    """
    Generate a cryptographically secure API key.
    
    Args:
        length: Length of the API key (default: 32)
        
    Returns:
        Random alphanumeric string suitable for use as an API key
    """
    alphabet = string.ascii_letters + string.digits
    api_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return api_key

def generate_activation_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure activation token.
    
    Args:
        length: Length of the token in bytes (default: 32)
        
    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(length)

def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using bcrypt.
    
    Args:
        api_key: The plaintext API key to hash
        
    Returns:
        Bcrypt hash of the API key as string
    """
    # Generate salt and hash the API key
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(api_key.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_api_key(plaintext_key: str, hashed_key: str) -> bool:
    """
    Verify a plaintext API key against its hash.
    
    Args:
        plaintext_key: The plaintext API key to verify
        hashed_key: The stored bcrypt hash
        
    Returns:
        True if the key matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plaintext_key.encode('utf-8'),
            hashed_key.encode('utf-8')
        )
    except Exception:
        return False

def generate_api_key_and_hash() -> Tuple[str, str]:
    """
    Generate a new API key and its hash in one operation.
    Useful for registration where you need both the plaintext (to show user)
    and the hash (to store in database).
    
    Returns:
        Tuple of (plaintext_api_key, hashed_api_key)
    """
    api_key = generate_api_key()
    hashed = hash_api_key(api_key)
    return api_key, hashed

# Email validation helper
def is_valid_email(email: str) -> bool:
    """
    Basic email validation.
    For production, consider using email-validator library.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email format is valid, False otherwise
    """
    import re
    
    # Basic email regex pattern
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
    
    if not email or len(email) > 255:
        return False
    
    return re.match(pattern, email) is not None

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: The plaintext password to hash
        
    Returns:
        Bcrypt hash of the password as string
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plaintext_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against its hash.
    
    Args:
        plaintext_password: The plaintext password to verify
        hashed_password: The stored bcrypt hash
        
    Returns:
        True if the password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plaintext_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.
    
    Requirements:
    - At least 8 characters
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter
    - Contains at least one number
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    # Optional: Check for common passwords
    common_passwords = ['password', '12345678', 'password123', 'qwerty123']
    if password.lower() in common_passwords:
        return False, "Password is too common. Please choose a stronger password"
    
    return True, ""
