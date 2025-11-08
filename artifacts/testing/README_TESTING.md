# Role-Based Access Control Testing Suite

Comprehensive testing framework for JWT authentication and role-based access control in the FBI Wanted API.

## Overview

This testing suite provides:
1. **Authentication Tests** - User registration, activation, token generation
2. **Role-Based Tests** - Access control verification for PUBLIC, BASIC, PREMIUM, and ADMIN roles

## Files

- `test_auth_modular.py` - Modular authentication tests
- `test_roles.py` - Role-based access control tests
- `test_driver.py` - Driver for authentication tests only
- `test_driver_extended.py` - Driver for both auth and role tests
- `README_TESTING.md` - This file

## Quick Start

### 1. Setup Test Users

Before running role tests, you need to create test users with different roles in your database:

```sql
-- Create test users with different roles (already hashed API keys)
INSERT INTO tbl_users (email, role, api_key_hash, is_active) VALUES
  ('public@test.com', 'public', '$2b$12$...', TRUE),
  ('basic@test.com', 'basic', '$2b$12$...', TRUE),
  ('premium@test.com', 'premium', '$2b$12$...', TRUE),
  ('admin@test.com', 'admin', '$2b$12$...', TRUE);
```

### 2. Configure API Keys

Edit `test_roles.py` and update the `TEST_KEYS` dictionary with your actual API keys:

```python
TEST_KEYS = {
    "PUBLIC": None,  # No key for public
    "BASIC": "basic_key_9H3dF7nM2kL4xW6pR8vT",  # Replace with actual key
    "PREMIUM": "premium_key_5X2nK8mP4wL9vR3hT6jZ",  # Replace with actual key
    "ADMIN": "admin_key_7M4pR9wX2nH5kL8vT3jQ"  # Replace with actual key
}
```

### 3. Run Tests

**Interactive Mode:**
```bash
python test_driver_extended.py
```

**Command Line Mode:**
```bash
# Run full test suite (auth + all roles)
python test_driver_extended.py --full

# Run authentication tests only
python test_driver_extended.py --auth

# Run all role tests
python test_driver_extended.py --roles

# Test specific role
python test_driver_extended.py --role BASIC
python test_driver_extended.py --role PREMIUM
python test_driver_extended.py --role ADMIN
```

**Programmatic Usage:**
```python
from test_roles import run_role_test, run_all_role_tests

# Test single role
result = run_role_test("BASIC")

# Test all roles
results = run_all_role_tests()
```

## Role Specifications

### PUBLIC Role
- **Access:** None (all protected endpoints should return 401)
- **Search:** Denied
- **Result Limit:** N/A
- **Data Field:** N/A
- **ETL Endpoints:** Denied

### BASIC Role
- **Access:** Simple search only
- **Search:** Simple search (wildcard-based)
- **Result Limit:** Maximum 25 results
- **Data Field:** Returns `full_data`
- **ETL Endpoints:** Denied
- **Advanced Search:** Denied

### PREMIUM Role
- **Access:** Simple + Advanced search
- **Search:** Simple and Advanced search
- **Result Limit:** Maximum 5000 results
- **Data Field:** Returns `full_data_clean`
- **ETL Endpoints:** Denied
- **Advanced Search:** Allowed

### ADMIN Role
- **Access:** All endpoints
- **Search:** Simple and Advanced search
- **Result Limit:** Maximum 5000 results
- **Data Field:** Returns `full_data_clean`
- **ETL Endpoints:** Allowed (extract, load, full_refresh)
- **Advanced Search:** Allowed

## Test Categories

### Authentication Tests

1. **register** - Test user registration
2. **duplicate_register** - Test duplicate registration handling
3. **activation** - Test account activation
4. **token_generation** - Test JWT token generation
5. **protected_no_token** - Test protected endpoint without token (should fail)
6. **protected_with_token** - Test protected endpoint with valid token
7. **invalid_token** - Test with invalid token (should fail)
8. **key_reset** - Test API key reset
9. **old_token_after_reset** - Test old token after reset (should fail)
10. **new_token_after_reset** - Test new token after reset

### Role-Based Access Tests

Each role test suite includes:

1. **Simple Search Access** - Can the role access simple search?
2. **Advanced Search Access** - Can the role access advanced search?
3. **Data Field Validation** - Does the role receive the correct data field?
4. **Result Limit Enforcement** - Are result limits properly enforced?
5. **ETL Extract Access** - Can the role access ETL extract endpoint?
6. **ETL Load Access** - Can the role access ETL load endpoint?

## Expected Test Results

### PUBLIC Role Tests (4 tests)
- ✓ Simple search denied (401)
- ✓ Advanced search denied (401)
- ✓ ETL extract denied (401)
- ✓ ETL load denied (401)

### BASIC Role Tests (8 tests)
- ✓ Simple search access allowed
- ✓ Returns `full_data` field
- ✓ Limit 25 allowed
- ✓ Limit 50 denied (403)
- ✓ Limit 5000 denied (403)
- ✓ Advanced search denied (403)
- ✓ ETL extract denied (403)
- ✓ ETL load denied (403)

### PREMIUM Role Tests (8 tests)
- ✓ Simple search access allowed
- ✓ Advanced search access allowed
- ✓ Returns `full_data_clean` field
- ✓ Limit 25 allowed
- ✓ Limit 500 allowed
- ✓ Limit 5000 allowed
- ✓ ETL extract denied (403)
- ✓ ETL load denied (403)

### ADMIN Role Tests (6 tests)
- ✓ Simple search access allowed
- ✓ Advanced search access allowed
- ✓ Returns `full_data_clean` field
- ✓ Limit 5000 allowed
- ✓ ETL extract access allowed
- ✓ ETL load access allowed

## Customizing Tests

### Add Custom Role Tests

Edit `test_roles.py` and add new test functions:

```python
def test_custom_scenario(role: str) -> Dict[str, Any]:
    """Your custom test"""
    print_section(f"Custom Test - {role}")
    
    token = get_token_for_role(role)
    # Your test logic here
    
    return {"success": True, "data": "..."}
```

### Modify Test Expectations

Update the role test suites in `test_roles.py`:

```python
def test_basic_role() -> Dict[str, Any]:
    """Modify BASIC role test expectations"""
    results = []
    
    # Add or modify tests
    results.append(("your_test", your_test_function("BASIC")))
    
    # ... rest of tests
    
    return {"role": "BASIC", "results": results}
```

## Troubleshooting

### "Could not get token for role X"
- Verify API key is correct in `TEST_KEYS`
- Check that user exists in database and is active
- Ensure API key hash matches in database

### "Connection refused" errors
- Verify FastAPI server is running on `http://localhost:8000`
- Check `BASE_URL` in test files matches your server

### Tests fail with unexpected status codes
- Review endpoint role requirements in `router_search.py` and `router_etl.py`
- Verify JWT authentication is properly configured
- Check database user roles match expected values

### Test data issues
- Update `EXISTING_EMAIL` and `EXISTING_API_KEY` in driver scripts
- Generate fresh test users if needed
- Clear test data between runs if necessary

## Advanced Usage

### Generate API Keys for Test Users

Use the security utilities to generate keys:

```python
from security_utils import generate_api_key_and_hash

# Generate for each role
for role in ["basic", "premium", "admin"]:
    api_key, api_key_hash = generate_api_key_and_hash()
    print(f"{role.upper()}_KEY = \"{api_key}\"")
    print(f"{role.upper()}_HASH = \"{api_key_hash}\"")
    print()
```

Then insert into database:

```sql
INSERT INTO tbl_users (email, role, api_key_hash, is_active)
VALUES ('basic@test.com', 'basic', 'HASH_FROM_ABOVE', TRUE);
```

### Run Specific Test Sequences

```python
from test_roles import (
    test_simple_search_access,
    test_simple_search_limits
)

# Test just search access for all roles
for role in ["PUBLIC", "BASIC", "PREMIUM", "ADMIN"]:
    result = test_simple_search_access(role, should_succeed=(role != "PUBLIC"))
    print(f"{role}: {result}")

# Test limit enforcement for BASIC
for limit in [25, 50, 100, 5000]:
    result = test_simple_search_limits("BASIC", limit, should_succeed=(limit == 25))
    print(f"Limit {limit}: {result}")
```

## Notes

- All tests return detailed JSON responses from the API
- Tests include both positive (should succeed) and negative (should fail) scenarios
- Role hierarchy: PUBLIC < BASIC < PREMIUM < ADMIN
- JWT tokens expire after 1 hour - tests will regenerate as needed
- Rate limiting may affect rapid test execution

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the source code comments in test files
3. Verify your API server configuration matches test expectations
