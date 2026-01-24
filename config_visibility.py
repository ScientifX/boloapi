# =============================================================================
# DOCS VISIBILITY CONFIGURATION
# =============================================================================
# Controls which endpoints are visible in /docs based on user role
# Visibility levels: PUBLIC (anyone), BASIC, PREMIUM, ADMIN
# Each role sees their level and below in the docs:
#   - PUBLIC users see only PUBLIC endpoints
#   - BASIC users see PUBLIC + BASIC endpoints
#   - PREMIUM users see PUBLIC + BASIC + PREMIUM endpoints
#   - ADMIN users see all endpoints
# Generated from routes.xlsx
from auth import UserRole
from config_docs import register_visibility_override
DOCS_VISIBILITY_CONFIG = {
    # ----- Public Pages (visible to everyone) -----
    ("POST", "/v1/auth/token"): UserRole.PUBLIC,
    ("POST", "/v1/auth/reset_key"): UserRole.PUBLIC,
    
    # ----- Admin-only visibility -----
    # These endpoints are only visible in /docs for ADMIN users
    
    # Root app admin endpoint
    ("GET", "/routes"): UserRole.ADMIN,

    # Analytics endpoints - ADMIN only
    ("GET", "/v1/analytics/my_searches"): UserRole.ADMIN,
    ("GET", "/v1/analytics/my_stats"): UserRole.ADMIN,
    ("GET", "/v1/analytics/admin/overview"): UserRole.ADMIN,
    ("GET", "/v1/analytics/admin/users/{user_id}/searches"): UserRole.ADMIN,

    # Auth endpoints - all admin visibility
    ("GET", "/v1/auth/activate"): UserRole.ADMIN,
    ("GET", "/v1/auth/change_password"): UserRole.ADMIN,
    ("POST", "/v1/auth/change_password"): UserRole.ADMIN,
    ("GET", "/v1/auth/forgot_password"): UserRole.ADMIN,
    ("POST", "/v1/auth/forgot_password"): UserRole.ADMIN,
    ("GET", "/v1/auth/login"): UserRole.ADMIN,
    ("POST", "/v1/auth/login"): UserRole.ADMIN,
    ("GET", "/v1/auth/logout"): UserRole.ADMIN,
    ("GET", "/v1/auth/profile"): UserRole.ADMIN,
    ("PUT", "/v1/auth/profile"): UserRole.ADMIN,
    ("GET", "/v1/auth/profile/data"): UserRole.ADMIN,
    ("POST", "/v1/auth/register"): UserRole.ADMIN,
    ("GET", "/v1/auth/reset_password"): UserRole.ADMIN,
    ("POST", "/v1/auth/reset_password"): UserRole.ADMIN,
    ("GET", "/v1/auth/set_password"): UserRole.ADMIN,
    ("POST", "/v1/auth/set_password"): UserRole.ADMIN,
    ("GET", "/v1/auth/signup"): UserRole.ADMIN,
    
    # Billing endpoints - all admin visibility
    ("GET", "/v1/billing/"): UserRole.ADMIN,
    ("POST", "/v1/billing/cancel"): UserRole.ADMIN,
    ("POST", "/v1/billing/create_checkout"): UserRole.ADMIN,
    ("GET", "/v1/billing/history"): UserRole.ADMIN,
    ("GET", "/v1/billing/info"): UserRole.ADMIN,
    ("GET", "/v1/billing/portal"): UserRole.ADMIN,
    ("GET", "/v1/billing/subscription"): UserRole.ADMIN,
    ("POST", "/v1/billing/test/reset-user/{email}"): UserRole.ADMIN,
    ("POST", "/v1/billing/test/send-email"): UserRole.ADMIN,
    ("POST", "/v1/billing/test/simulate-webhook"): UserRole.ADMIN,
    ("GET", "/v1/billing/test/user-status/{email}"): UserRole.ADMIN,
    ("POST", "/v1/billing/webhook"): UserRole.ADMIN,
    ("GET", "/v1/billing/webhook/test"): UserRole.ADMIN,
    
    # ETL endpoints - all admin visibility
    ("GET", "/v1/etl/extract"): UserRole.ADMIN,
    ("GET", "/v1/etl/full_refresh"): UserRole.ADMIN,
    ("GET", "/v1/etl/load"): UserRole.ADMIN,
    ("GET", "/v1/etl/metadata"): UserRole.ADMIN,
    ("GET", "/v1/etl/process_notifications"): UserRole.ADMIN,
    ("POST", "/v1/etl/full_refresh_merge"): UserRole.ADMIN,
    ("GET", "/v1/etl/metadata_merge"): UserRole.ADMIN,
    
    # Search root - admin visibility
    ("GET", "/v1/search/"): UserRole.ADMIN,
    
    # ----- Basic visibility (BASIC and above see these) -----
    ("POST", "/v1/search/simple"): UserRole.BASIC,
    # Reference list endpoints - BASIC visibility
    ("GET", "/v1/search/list_field_offices"): UserRole.BASIC,
    ("GET", "/v1/search/list_languages"): UserRole.BASIC,
    ("GET", "/v1/search/list_nationality"): UserRole.BASIC,
    ("GET", "/v1/search/list_possible_countries"): UserRole.BASIC,
    ("GET", "/v1/search/list_possible_states"): UserRole.BASIC,
    ("GET", "/v1/search/list_race"): UserRole.BASIC,
    
    
    # ----- Premium visibility (PREMIUM and above see these) -----
    ("POST", "/v1/search/advanced"): UserRole.BASIC,
    ("GET", "/v1/search/top_missing"): UserRole.BASIC,
    ("GET", "/v1/search/category_top_reward"): UserRole.BASIC,
    ("GET", "/v1/search/category_top_ten"): UserRole.BASIC,
    ("GET", "/v1/search/top_terrorist"): UserRole.BASIC,
}

# Register all visibility overrides at startup
for (method, path), role in DOCS_VISIBILITY_CONFIG.items():
    register_visibility_override(method, path, visible_to=role)
