# Enhanced Summary - Quick Reference

## What's New

The test suite now provides **comprehensive pass/fail summaries** with detailed reasons for each test result.

## Summary Levels

### 1. Individual Role Summaries
After each role test suite, you'll see:

```
BASIC ROLE SUMMARY: 8/8 tests passed

  PASSED:
    ✓ test_name                (reason why it passed)
    
  FAILED:
    ✗ test_name                (reason why it failed)
```

### 2. Grand Summary
After all roles are tested:

```
GRAND SUMMARY - ALL ROLES

✓/⚠ Each role's pass/fail percentage

PASSED TESTS SUMMARY
  ✓ ROLE - test_name          (details)

FAILED TESTS SUMMARY  
  ✗ ROLE - test_name          (specific failure reason)

STATISTICS
  - Total/Passed/Failed counts
  - Per-role breakdown
```

## Understanding Test Results

### Success Indicators

| Indicator | Meaning |
|-----------|---------|
| ✓ | Test passed |
| ✗ | Test failed |
| ⚠ | Role has some failures |

### Pass Reasons

| Reason | What It Means |
|--------|---------------|
| `status=200` | Request succeeded as expected |
| `status=401/403, correctly denied` | Properly blocked unauthorized access |
| `field=full_data` | Returned correct data field for role |
| `results=15` | Successfully returned N records |
| `matches expected` | Field matches role requirements |
| `limit accepted` | Result limit properly enforced |

### Fail Reasons

| Reason | What It Means | What To Check |
|--------|---------------|---------------|
| `FAILED TO GET TOKEN` | Cannot authenticate | TEST_KEYS config, database user |
| `status=200, should have been denied` | Got access when shouldn't | Role enforcement in endpoints |
| `status=403, (forbidden)` | Denied when should succeed | Role requirements too high |
| `status=401, (unauthorized)` | Token invalid/expired | JWT generation, token validity |
| `status=500, (unexpected)` | Server error | API logs, database connection |
| `got X, expected Y` | Wrong data field | get_data_field_for_role() |
| `unexpected` | Status code out of range | Endpoint logic |

## Quick Troubleshooting

### Problem: All tests fail with "FAILED TO GET TOKEN"

**Solution:**
1. Verify TEST_KEYS in `test_roles.py`
2. Check users exist in database
3. Verify API keys match database hashes
4. Ensure users are active (`is_active = TRUE`)

### Problem: BASIC can do PREMIUM things

**Solution:**
1. Check `require_jwt_role()` calls in endpoints
2. Verify role requirements match documentation
3. Review `has_role()` hierarchy logic

### Problem: Wrong data fields returned

**Solution:**
1. Check `get_data_field_for_role()` function
2. Verify database view returns correct fields
3. Confirm role-to-field mapping

### Problem: Limit enforcement not working

**Solution:**
1. Check `validate_limit_for_role()` function
2. Verify max limits per role
3. Test with boundary values

## Reading the Output

### Example 1: All Passed ✓
```
BASIC ROLE SUMMARY: 8/8 tests passed

  PASSED:
    ✓ simple_search_access              (status=200)
    ✓ limit_25_allowed                  (status=200, limit accepted)
    ✓ limit_50_denied                   (status=403, correctly denied)
```

**Interpretation:** BASIC role is working perfectly. Can access what it should, denied what it shouldn't.

### Example 2: Access Control Broken ✗
```
BASIC ROLE SUMMARY: 7/8 tests passed

  PASSED:
    ✓ simple_search_access              (status=200)
    
  FAILED:
    ✗ advanced_search_denied            (status=200, should have been denied)
```

**Interpretation:** BASIC users can access advanced search when they shouldn't. Check role requirements on `/api/search/advanced` endpoint.

### Example 3: Authentication Issue ✗
```
PREMIUM ROLE SUMMARY: 0/8 tests passed

  FAILED:
    ✗ simple_search_access              (FAILED TO GET TOKEN)
    ✗ advanced_search_access            (FAILED TO GET TOKEN)
```

**Interpretation:** Cannot get token for PREMIUM role. Check TEST_KEYS has correct API key for PREMIUM user.

### Example 4: Data Field Mismatch ✗
```
PREMIUM ROLE SUMMARY: 7/8 tests passed

  PASSED:
    ✓ simple_search_access              (status=200)
    
  FAILED:
    ✗ data_field_full_data_clean        (got full_data, expected full_data_clean)
```

**Interpretation:** PREMIUM should receive `full_data_clean` but getting `full_data` instead. Check `get_data_field_for_role()` logic.

## Command Line Usage

```bash
# Run all roles, see comprehensive summary
python test_driver_extended.py --roles

# Run specific role
python test_driver_extended.py --role BASIC

# Interactive mode
python test_driver_extended.py
```

## Programmatic Usage

```python
from test_roles import run_all_role_tests

# Run all tests and get detailed results
results = run_all_role_tests()

# Access specific role results
basic_results = results["BASIC"]
print(f"BASIC: {basic_results['passed']}/{basic_results['total']}")

# Check individual tests
for test_name, test_result in basic_results["results"]:
    if not test_result.get("success"):
        print(f"Failed: {test_name}")
        print(f"Reason: {test_result}")
```

## What to Look For

### ✅ Healthy System
- All roles show 100% pass rate
- PASSED section for each role is comprehensive
- No FAILED sections
- Overall percentage is 100%

### ⚠️ Needs Attention  
- Any role below 100%
- FAILED TESTS SUMMARY section appears
- Status codes don't match expectations
- "should have been denied" appears
- Token generation failures

### 🚨 Critical Issues
- Multiple roles failing same tests
- All tests fail with token errors
- Status 500 errors appearing
- Role boundaries completely broken

## Next Steps After Test Failure

1. **Read the failure reason** - It tells you what went wrong
2. **Check the affected component** - Auth, authorization, or logic?
3. **Review the code** - Look at the endpoint or function mentioned
4. **Verify configuration** - Are TEST_KEYS and database correct?
5. **Check logs** - Look at FastAPI/database logs for errors
6. **Fix and retest** - Make changes and run tests again

## Pro Tips

💡 **Run tests after every deployment** to catch regressions

💡 **Compare before/after** when making role-related changes

💡 **Use individual role tests** during development for faster iteration

💡 **Check FAILED section first** for quickest debugging

💡 **Look for patterns** - Multiple similar failures indicate systemic issues

💡 **Save test output** to track progress over time
