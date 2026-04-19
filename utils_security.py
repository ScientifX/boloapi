"""
Security utilities for password/API key hashing and token generation
Uses bcrypt for hashing and secrets for cryptographically secure random generation

Password strength validation uses a layered approach:
  Tier 1 (sync): length, character classes, repeated/sequential patterns,
                 email-local-part match, common-password blocklist.
  Tier 3 (async): Have I Been Pwned k-anonymity breach check.
                  Fails open on network/service errors.
"""
import hashlib
import logging
import secrets
import string
import bcrypt
import httpx
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Password policy constants
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
PASSWORD_SPECIAL_CHARS = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
HIBP_API_URL = "https://api.pwnedpasswords.com/range/"
HIBP_TIMEOUT_SECONDS = 3.0

# Focused common-password blocklist for fast-path rejection.
# HIBP catches a much wider net on the network side; this list handles
# the obvious offenders without requiring a network round-trip.
_COMMON_PASSWORDS = frozenset([
    # Top breached/leaked variants
    "password", "password1", "password12", "password123", "password1234",
    "passw0rd", "passw0rd1", "p@ssword", "p@ssword1", "p@ssw0rd", "p@ssw0rd1",
    "12345678", "123456789", "1234567890", "123123123", "111111111",
    "qwerty123", "qwerty1234", "qwertyuiop", "qwertyqwerty", "qwerty12345",
    "iloveyou", "iloveyou1", "iloveyou123",
    "welcome", "welcome1", "welcome12", "welcome123", "welcome1234",
    "admin", "admin123", "admin1234", "administrator", "root", "root1234",
    "letmein", "letmein1", "letmein123", "letmein1234",
    "monkey", "monkey123", "dragon", "dragon123",
    "abc12345", "abcd1234", "abcdefgh", "abcd12345", "abcdef123",
    # Tech/developer favorites
    "testing1234", "testing123", "test1234", "test12345", "test123456",
    "changeme", "changeme1", "changeme123", "changeme1234",
    "secret123", "secret1234", "secret12345",
    "superman1", "superman123", "batman123", "batman1234",
    "trustno1", "trustno12", "trustno123",
    # Season + year (evergreen attacker patterns)
    "summer2024", "summer2025", "summer2026",
    "spring2024", "spring2025", "spring2026",
    "autumn2024", "autumn2025", "autumn2026",
    "winter2024", "winter2025", "winter2026",
    "fall2024", "fall2025", "fall2026",
    # Product/brand specific
    "bolodoc", "bolodoc1", "bolodoc12", "bolodoc123", "bolodoc1234",
    "scientifics", "scientifics1", "scientifics123",
])

# Keyboard and alphabetic sequences used to detect walk-patterns.
_SEQUENCES = (
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
)
_SEQUENTIAL_RUN_LENGTH = 4
_REPEATED_RUN_LENGTH = 3

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

def _has_repeated_run(password: str, max_run: int = _REPEATED_RUN_LENGTH) -> bool:
    """
    Return True if the password contains `max_run` or more of the same character
    repeated consecutively (for example: 'aaa', '1111', '...').
    """
    if len(password) < max_run:
        return False
    run = 1
    for i in range(1, len(password)):
        if password[i] == password[i - 1]:
            run += 1
            if run >= max_run:
                return True
        else:
            run = 1
    return False


def _has_sequential_run(password: str, min_seq: int = _SEQUENTIAL_RUN_LENGTH) -> bool:
    """
    Return True if the password contains a sequential run of `min_seq` or more
    characters drawn from the alphabet, the digit sequence, or a keyboard row
    (forward or reverse). Case-insensitive.
    """
    if len(password) < min_seq:
        return False
    pwd_lower = password.lower()
    for seq in _SEQUENCES:
        rev = seq[::-1]
        for source in (seq, rev):
            for i in range(len(source) - min_seq + 1):
                if source[i:i + min_seq] in pwd_lower:
                    return True
    return False


def _contains_email_local_part(password: str, email: Optional[str]) -> bool:
    """
    Return True if the password contains the local part of the email
    (the portion before '@'). Case-insensitive. Requires at least 3 chars
    in the local part to be considered significant.
    """
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].lower().strip()
    if len(local) < 3:
        return False
    return local in password.lower()


def _is_common_password(password: str) -> bool:
    """
    Return True if the password matches an entry in the local common-password
    blocklist. Checks both the raw lowercased password and a stripped
    alphanumeric-only form so 'Password!123' still matches 'password123'.
    """
    pwd_lower = password.lower()
    if pwd_lower in _COMMON_PASSWORDS:
        return True
    stripped = "".join(c for c in pwd_lower if c.isalnum())
    if stripped and stripped in _COMMON_PASSWORDS:
        return True
    return False


def validate_password_strength(
    password: str,
    email: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Synchronous Tier 1 password strength validation.

    Policy:
      - Minimum 12 characters, maximum 128 characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one special character
      - No 3+ consecutive repeated characters
      - No 4+ sequential characters (alphabet, digits, keyboard rows)
      - Does not contain the email local part (when email is provided)
      - Is not on the common-password blocklist

    For breach-database checks, call `check_password_breached()` in addition.

    Args:
        password: Password to validate.
        email: Optional email address. When provided, the password cannot
               contain the portion before the '@'.

    Returns:
        Tuple of (is_valid, error_message). error_message is empty on success.
    """
    if not password:
        return False, "Password is required"

    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters long"

    if len(password) > PASSWORD_MAX_LENGTH:
        return False, f"Password must be {PASSWORD_MAX_LENGTH} characters or fewer"

    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"

    if not any(c in PASSWORD_SPECIAL_CHARS for c in password):
        return False, "Password must contain at least one special character"

    if _has_repeated_run(password):
        return False, (
            f"Password cannot contain {_REPEATED_RUN_LENGTH} or more of the "
            "same character in a row"
        )

    if _has_sequential_run(password):
        return False, (
            "Password cannot contain sequential characters "
            "(for example: 1234, abcd, or keyboard rows)"
        )

    if _contains_email_local_part(password, email):
        return False, "Password cannot contain your email address"

    if _is_common_password(password):
        return False, "This password is too common. Please choose a different password"

    return True, ""


async def check_password_breached(
    password: str,
    timeout: float = HIBP_TIMEOUT_SECONDS
) -> Tuple[bool, str]:
    """
    Tier 3 breach check using the Have I Been Pwned Pwned Passwords API.

    Uses k-anonymity: only the first 5 characters of the SHA-1 hash are sent
    to HIBP; the full hash never leaves this server. HIBP returns a list of
    hash suffixes that share that prefix, and we compare locally.

    Fails OPEN: if the HIBP API is unreachable, times out, or returns an
    error, this function returns (False, "") so registration and password
    changes are not blocked by a third-party outage. The Tier 1 rules
    enforced by validate_password_strength() remain the floor.

    Args:
        password: Password to check against breach corpus.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of (is_breached, error_message). error_message is empty when
        the password is clean OR when the check failed open.
    """
    if not password:
        return False, ""

    try:
        sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix = sha1_hash[:5]
        suffix = sha1_hash[5:]

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{HIBP_API_URL}{prefix}",
                headers={
                    "Add-Padding": "true",
                    "User-Agent": "BoloDoc-PasswordCheck/1.0",
                },
            )
            response.raise_for_status()

        for line in response.text.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[0].strip().upper() == suffix:
                try:
                    count = int(parts[1].strip())
                except ValueError:
                    continue
                if count > 0:
                    logger.info(
                        f"HIBP breach match for password (count={count}); rejecting"
                    )
                    return True, (
                        "This password has appeared in known data breaches "
                        "and cannot be used. Please choose a different password"
                    )

        return False, ""

    except httpx.TimeoutException:
        logger.warning("HIBP breach check timed out; failing open")
        return False, ""
    except httpx.HTTPError as e:
        logger.warning(f"HIBP breach check HTTP error (failing open): {e}")
        return False, ""
    except Exception as e:
        logger.warning(f"HIBP breach check unexpected error (failing open): {e}")
        return False, ""


async def validate_password_full(
    password: str,
    email: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Run both Tier 1 (sync) and Tier 3 (async HIBP) password checks.

    Convenience wrapper for handlers that want a single call site. Tier 1
    runs first so malformed passwords are rejected without hitting the
    network.

    Args:
        password: Password to validate.
        email: Optional email address for local-part check.

    Returns:
        Tuple of (is_valid, error_message).
    """
    is_valid, error = validate_password_strength(password, email)
    if not is_valid:
        return False, error

    is_breached, breach_error = await check_password_breached(password)
    if is_breached:
        return False, breach_error

    return True, ""
