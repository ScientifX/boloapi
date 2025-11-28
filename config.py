"""
Configuration Management
Loads all environment variables for the application.
Works in both development (with .env file) and production (Railway/cloud env vars).

Development setup:
    1. Create a .env file in project root
    2. Add variables like: API_DB_HOST=localhost
    3. python-dotenv will load them automatically

Production setup:
    1. Set environment variables in Railway dashboard
    2. No .env file needed - Railway injects env vars directly
"""
import os
from typing import Optional

# Load .env file for local development only
# In production (Railway), this does nothing and environment variables are already set
try:
    from dotenv import load_dotenv
    load_dotenv()  # Loads .env file if it exists
except ImportError:
    # python-dotenv not installed - that's OK for production
    pass

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DB_CONFIG = { 
    "host": os.getenv('API_DB_HOST'),
    "port": os.getenv('API_DB_PORT'),
    "database": os.getenv('API_DB_DATABASE'),
    "user": os.getenv('API_DB_USER'),
    "password": os.getenv('API_DB_PASSWORD'),
    "options": "-c search_path=base,public"  # Look in base schema first, then public
}

# ============================================================================
# JWT CONFIGURATION
# ============================================================================

API_JWT_SECRET_KEY = os.getenv('API_JWT_SECRET_KEY')
API_JWT_ALGORITHM = os.getenv('API_JWT_ALGORITHM')
API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv('API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES')

# ============================================================================
# EMAIL CONFIGURATION (Microsoft Graph API)
# ============================================================================

# Microsoft Azure AD App Registration
API_AZURE_CLIENT_ID = os.getenv('API_AZURE_CLIENT_ID')
API_AZURE_CLIENT_SECRET = os.getenv('API_AZURE_CLIENT_SECRET')
API_AZURE_TENANT_ID = os.getenv('API_AZURE_TENANT_ID')

# Email settings
API_EMAIL_FROM_ADDRESS = os.getenv('API_EMAIL_FROM_ADDRESS') 
API_EMAIL_FROM_NAME = os.getenv('API_EMAIL_FROM_NAME') 

# Application URL (for email links)
API_APP_BASE_URL = os.getenv('API_APP_BASE_URL')  # Default for dev

# ============================================================================
# API CONFIGURATION
# ============================================================================

APP_GLOBALS = {
    "app_name": "BoloDoc",
    "company_name": "Scientifics.io",
    "business_email": "contact@scientifics.io",
    "legal_email": "legal@scientifics.io",
    "privacy_email": "privacy@scientifics.io",
    "security_email": "security@scientifics.io",
    "support_email": "engage@scientifics.io",
    "api_version" : "2.0.0", 
    "api_description" : "A Comprehensive FBI Wanted Persons Search API", 
    "year": 2025
    }


# Rate limiting
RATE_LIMIT_DEFAULT = "10/minute"

# ============================================================================
# LEMONSQUEEZY CONFIGURATION
# ============================================================================

API_LEMONSQUEEZY_API_KEY = os.getenv('API_LEMONSQUEEZY_API_KEY')
API_LEMONSQUEEZY_STORE_ID = os.getenv('API_LEMONSQUEEZY_STORE_ID')
API_LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv('API_LEMONSQUEEZY_WEBHOOK_SECRET')

# Product variant IDs
API_LEMONSQUEEZY_VARIANT_MONTHLY = os.getenv('API_LEMONSQUEEZY_VARIANT_MONTHLY')
API_LEMONSQUEEZY_VARIANT_QUARTERLY = os.getenv('API_LEMONSQUEEZY_VARIANT_QUARTERLY')
API_LEMONSQUEEZY_VARIANT_ANNUAL = os.getenv('API_LEMONSQUEEZY_VARIANT_ANNUAL')

# Test mode - enables simulated webhook endpoints for local testing
# Set to 'true' to enable, remove or set to 'false' for production
BILLING_TEST_MODE = os.getenv('API_BILLING_TEST_MODE', 'false').lower() == 'true'

# ============================================================================
# PRICING CONFIGURATION
# ============================================================================

# Define your prices here (easier to update)
PRICE_MONTHLY = 9.99
PRICE_QUARTERLY = 19.99
PRICE_ANNUAL = 39.99

# Calculate savings automatically
SAVINGS_QUARTERLY = round((PRICE_MONTHLY * 3) - PRICE_QUARTERLY, 2)
SAVINGS_ANNUAL = round((PRICE_MONTHLY * 12) - PRICE_ANNUAL, 2)

PRICING = {
    'monthly': {
        'price': PRICE_MONTHLY,
        'currency': 'USD',
        'interval': 'month',
        'variant_id': API_LEMONSQUEEZY_VARIANT_MONTHLY
    },
    'quarterly': {
        'price': PRICE_QUARTERLY,
        'currency': 'USD',
        'interval': 'quarter',
        'variant_id': API_LEMONSQUEEZY_VARIANT_QUARTERLY,
        'savings': SAVINGS_QUARTERLY
    },
    'annual': {
        'price': PRICE_ANNUAL,
        'currency': 'USD',
        'interval': 'year',
        'variant_id': API_LEMONSQUEEZY_VARIANT_ANNUAL,
        'savings': SAVINGS_ANNUAL
    }
}

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_config() -> list[str]:
    """
    Validate that required configuration variables are set.
    Returns list of missing variables.
    
    Call this at application startup to fail fast if config is incomplete.
    """
    required_vars = {
        # Database (required)
        'API_DB_HOST': DB_CONFIG['host'],
        'API_DB_PORT': DB_CONFIG['port'],
        'API_DB_DATABASE': DB_CONFIG['database'],
        'API_DB_USER': DB_CONFIG['user'],
        'API_DB_PASSWORD': DB_CONFIG['password'],
        
        # Email (required)
        'API_AZURE_CLIENT_ID': API_AZURE_CLIENT_ID,
        'API_AZURE_CLIENT_SECRET': API_AZURE_CLIENT_SECRET,
        'API_AZURE_TENANT_ID': API_AZURE_TENANT_ID,
        'API_EMAIL_FROM_ADDRESS': API_EMAIL_FROM_ADDRESS,
        
        # Security (required)
        'API_JWT_SECRET_KEY': API_JWT_SECRET_KEY,
        'API_JWT_ALGORITHM': API_JWT_ALGORITHM,
        'API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES': int(os.getenv('API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES')),

        # LemonSqueezy (required for billing)
        'API_LEMONSQUEEZY_API_KEY': API_LEMONSQUEEZY_API_KEY,
        'API_LEMONSQUEEZY_STORE_ID': API_LEMONSQUEEZY_STORE_ID,
        'API_LEMONSQUEEZY_WEBHOOK_SECRET': API_LEMONSQUEEZY_WEBHOOK_SECRET

        }
    
    missing = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing.append(var_name)
    
    return missing

def get_config_summary() -> dict:
    """
    Get a summary of configuration status (safe for logging).
    Does NOT include sensitive values.
    """
    return {
        "database": {
            "host": DB_CONFIG['host'],
            "port": DB_CONFIG['port'],
            "database": DB_CONFIG['database'],
            "configured": bool(DB_CONFIG['host'] and DB_CONFIG['database'])
        },
        "email": {
            "provider": "Microsoft Graph API",
            "from_address": API_EMAIL_FROM_ADDRESS,
            "configured": bool(API_AZURE_CLIENT_ID and API_AZURE_CLIENT_SECRET)
        },
        "app": {
            "base_url": API_APP_BASE_URL,
            "jwt_expiry_minutes": API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        },
        "billing": {
            "test_mode": BILLING_TEST_MODE,
            "variants_configured": bool(
                API_LEMONSQUEEZY_VARIANT_MONTHLY and 
                API_LEMONSQUEEZY_VARIANT_QUARTERLY and 
                API_LEMONSQUEEZY_VARIANT_ANNUAL
            )
        }
    }
