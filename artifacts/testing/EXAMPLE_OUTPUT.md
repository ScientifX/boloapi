# Example Output - Enhanced Comprehensive Summary

This document shows what the enhanced summary output looks like after running the role-based tests.

## Individual Role Summary (Example: BASIC Role)

```
===========================================================================
 BASIC ROLE SUMMARY: 8/8 tests passed
===========================================================================

  PASSED:
    ✓ simple_search_access              (status=200)
    ✓ data_field_full_data              (status=200, field=full_data)
    ✓ limit_25_allowed                  (status=200, limit accepted)
    ✓ limit_50_denied                   (status=403, correctly denied)
    ✓ limit_5000_denied                 (status=403, correctly denied)
    ✓ advanced_search_denied            (status=403, correctly denied)
    ✓ etl_extract_denied                (status=403, correctly denied)
    ✓ etl_load_denied                   (status=403, correctly denied)
```

## Individual Role Summary with Failures (Example)

```
===========================================================================
 BASIC ROLE SUMMARY: 6/8 tests passed
===========================================================================

  PASSED:
    ✓ simple_search_access              (status=200)
    ✓ data_field_full_data              (status=200, field=full_data)
    ✓ limit_25_allowed                  (status=200, limit accepted)
    ✓ limit_50_denied                   (status=403, correctly denied)
    ✓ advanced_search_denied            (status=403, correctly denied)
    ✓ etl_extract_denied                (status=403, correctly denied)

  FAILED:
    ✗ limit_5000_denied                 (status=200, should have been denied)
    ✗ etl_load_denied                   (failed to get token)
```

## Grand Summary - All Roles

```
██████████████████████████████████████████████████████████████████████
██                                                                  ██
██                  GRAND SUMMARY - ALL ROLES                      ██
██                                                                  ██
██████████████████████████████████████████████████████████████████████

✓ PUBLIC: 4/4 tests passed (100.0%)

✓ BASIC: 8/8 tests passed (100.0%)

✓ PREMIUM: 8/8 tests passed (100.0%)

✓ ADMIN: 6/6 tests passed (100.0%)

======================================================================
OVERALL: 26/26 tests passed (100.0%)
======================================================================

======================================================================
 PASSED TESTS SUMMARY
======================================================================
  ✓ PUBLIC   - simple_search             (status=401, correctly denied)
  ✓ PUBLIC   - advanced_search           (status=401, correctly denied)
  ✓ PUBLIC   - etl_extract               (status=401, correctly denied)
  ✓ PUBLIC   - etl_load                  (status=401, correctly denied)
  ✓ BASIC    - simple_search_access      (status=200, results=15)
  ✓ BASIC    - data_field_full_data      (status=200, field=full_data, matches expected)
  ✓ BASIC    - limit_25_allowed          (status=200, limit accepted)
  ✓ BASIC    - limit_50_denied           (status=403, correctly denied)
  ✓ BASIC    - limit_5000_denied         (status=403, correctly denied)
  ✓ BASIC    - advanced_search_denied    (status=403, correctly denied)
  ✓ BASIC    - etl_extract_denied        (status=403, correctly denied)
  ✓ BASIC    - etl_load_denied           (status=403, correctly denied)
  ✓ PREMIUM  - simple_search_access      (status=200, results=15)
  ✓ PREMIUM  - advanced_search_access    (status=200, results=8)
  ✓ PREMIUM  - data_field_full_data_clean (status=200, field=full_data_clean, matches expected)
  ✓ PREMIUM  - limit_25_allowed          (status=200, limit accepted)
  ✓ PREMIUM  - limit_500_allowed         (status=200, limit accepted)
  ✓ PREMIUM  - limit_5000_allowed        (status=200, limit accepted)
  ✓ PREMIUM  - etl_extract_denied        (status=403, correctly denied)
  ✓ PREMIUM  - etl_load_denied           (status=403, correctly denied)
  ✓ ADMIN    - simple_search_access      (status=200, results=15)
  ✓ ADMIN    - advanced_search_access    (status=200, results=8)
  ✓ ADMIN    - data_field_full_data_clean (status=200, field=full_data_clean, matches expected)
  ✓ ADMIN    - limit_5000_allowed        (status=200, limit accepted)
  ✓ ADMIN    - etl_extract_access        (status=200)
  ✓ ADMIN    - etl_load_access           (status=200)

======================================================================
 STATISTICS
======================================================================
  Total Tests Run:    26
  Passed:             26 (100.0%)
  Failed:             0 (0.0%)

  Breakdown by Role:
    PUBLIC  : 4 passed, 0 failed out of 4 total
    BASIC   : 8 passed, 0 failed out of 8 total
    PREMIUM : 8 passed, 0 failed out of 8 total
    ADMIN   : 6 passed, 0 failed out of 6 total

======================================================================
```

## Grand Summary with Failures (Example)

```
██████████████████████████████████████████████████████████████████████
██                                                                  ██
██                  GRAND SUMMARY - ALL ROLES                      ██
██                                                                  ██
██████████████████████████████████████████████████████████████████████

⚠ PUBLIC: 3/4 tests passed (75.0%)

⚠ BASIC: 6/8 tests passed (75.0%)

✓ PREMIUM: 8/8 tests passed (100.0%)

⚠ ADMIN: 5/6 tests passed (83.3%)

======================================================================
OVERALL: 22/26 tests passed (84.6%)
======================================================================

======================================================================
 PASSED TESTS SUMMARY
======================================================================
  ✓ PUBLIC   - simple_search             (status=401, correctly denied)
  ✓ PUBLIC   - advanced_search           (status=401, correctly denied)
  ✓ PUBLIC   - etl_extract               (status=401, correctly denied)
  ✓ BASIC    - simple_search_access      (status=200, results=15)
  ✓ BASIC    - data_field_full_data      (status=200, field=full_data, matches expected)
  ✓ BASIC    - limit_25_allowed          (status=200, limit accepted)
  ✓ BASIC    - advanced_search_denied    (status=403, correctly denied)
  ✓ BASIC    - etl_extract_denied        (status=403, correctly denied)
  ✓ BASIC    - etl_load_denied           (status=403, correctly denied)
  ✓ PREMIUM  - simple_search_access      (status=200, results=15)
  ✓ PREMIUM  - advanced_search_access    (status=200, results=8)
  ✓ PREMIUM  - data_field_full_data_clean (status=200, field=full_data_clean, matches expected)
  ✓ PREMIUM  - limit_25_allowed          (status=200, limit accepted)
  ✓ PREMIUM  - limit_500_allowed         (status=200, limit accepted)
  ✓ PREMIUM  - limit_5000_allowed        (status=200, limit accepted)
  ✓ PREMIUM  - etl_extract_denied        (status=403, correctly denied)
  ✓ PREMIUM  - etl_load_denied           (status=403, correctly denied)
  ✓ ADMIN    - simple_search_access      (status=200, results=15)
  ✓ ADMIN    - advanced_search_access    (status=200, results=8)
  ✓ ADMIN    - data_field_full_data_clean (status=200, field=full_data_clean, matches expected)
  ✓ ADMIN    - limit_5000_allowed        (status=200, limit accepted)
  ✓ ADMIN    - etl_extract_access        (status=200)

======================================================================
 FAILED TESTS SUMMARY
======================================================================
  ✗ PUBLIC   - etl_load                  (FAILED TO GET TOKEN)
  ✗ BASIC    - limit_50_denied           (status=200, (succeeded when should have failed))
  ✗ BASIC    - limit_5000_denied         (status=500, (unexpected status))
  ✗ ADMIN    - etl_load_access           (status=403, (forbidden - role insufficient))

======================================================================
 STATISTICS
======================================================================
  Total Tests Run:    26
  Passed:             22 (84.6%)
  Failed:             4 (15.4%)

  Breakdown by Role:
    PUBLIC  : 3 passed, 1 failed out of 4 total
    BASIC   : 6 passed, 2 failed out of 8 total
    PREMIUM : 8 passed, 0 failed out of 8 total
    ADMIN   : 5 passed, 1 failed out of 6 total

======================================================================
```

## Key Features of Enhanced Summary

### 1. Role-Specific Breakdowns
Each role shows:
- List of **PASSED** tests with reasons (status codes, what was validated)
- List of **FAILED** tests with detailed failure reasons

### 2. Comprehensive Pass/Fail Lists
- **PASSED TESTS SUMMARY**: Every successful test with details
- **FAILED TESTS SUMMARY**: Every failed test with explanations

### 3. Detailed Failure Reasons
Failed tests show specific reasons:
- `FAILED TO GET TOKEN` - Authentication issue
- `status=200, should have been denied` - Test succeeded when it should have failed
- `status=403, (forbidden - role insufficient)` - Role doesn't have permission
- `status=401, (unauthorized - token issue)` - Token problem
- `status=500, (unexpected status)` - Server error
- `got full_data, expected full_data_clean` - Data field mismatch

### 4. Statistical Breakdown
- Overall pass/fail percentage
- Per-role statistics
- Total counts

### 5. Success Indicators
- `✓` Green checkmark for passing tests
- `✗` Red X for failing tests
- `⚠` Warning triangle for roles with failures

## What Each Reason Means

### Passed Test Reasons
- `status=200` - Request succeeded
- `status=401/403, correctly denied` - Properly blocked unauthorized access
- `field=full_data` - Got the correct data field
- `results=15` - Number of records returned
- `matches expected` - Field matches what was expected for this role
- `limit accepted` - Result limit was properly enforced

### Failed Test Reasons
- `FAILED TO GET TOKEN` - Could not authenticate (check API key in TEST_KEYS)
- `status=200, should have been denied` - Got access when shouldn't have (role enforcement broken)
- `status=403, (forbidden - role insufficient)` - Got 403 when should have been 200 (role too low)
- `status=401, (unauthorized - token issue)` - Authentication failed (check JWT token)
- `status=500, (unexpected status)` - Server error (check API logs)
- `got X, expected Y` - Wrong data field returned (role-based field selection broken)
- `unexpected` - Status code not in expected range

## Using This Information

### When All Tests Pass
You can be confident that:
- Authentication is working correctly
- Role-based access control is properly enforced
- Result limits are being respected
- Correct data fields are being returned

### When Tests Fail
The detailed reasons help you:
1. **Identify root cause** - Is it auth, authorization, or logic?
2. **Locate the problem** - Which role/endpoint combination is broken?
3. **Understand impact** - How many features are affected?
4. **Prioritize fixes** - Critical vs minor issues

### Common Failure Patterns

**All roles fail with "FAILED TO GET TOKEN"**
→ Check TEST_KEYS configuration and database setup

**BASIC can access PREMIUM features**
→ Check role requirements in endpoint dependencies

**Wrong data fields returned**
→ Check get_data_field_for_role() function

**Limit enforcement not working**
→ Check validate_limit_for_role() function

**403 when should get 200**
→ Role hierarchy issue in has_role() function
