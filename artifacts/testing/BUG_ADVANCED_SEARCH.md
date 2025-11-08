# Router Search Bug - Advanced Search Endpoint

## The Bug

**Location:** `router_search.py` line 1171

**Problem:** The `/api/search/advanced` endpoint is incorrectly typed to accept `SimpleSearchRequest` when it should accept `AdvancedSearchRequest`.

```python
# CURRENT (WRONG):
async def advanced_search(
    request: Request, 
    search_request: SimpleSearchRequest,  # ❌ WRONG!
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC)) 
):
```

**Should be:**
```python
# CORRECT:
async def advanced_search(
    request: Request, 
    search_request: AdvancedSearchRequest,  # ✅ CORRECT!
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC)) 
):
```

## Why This Causes Problems

### 1. Validation Errors
`SimpleSearchRequest` has `extra='forbid'` in its config:
```python
model_config = ConfigDict(
    extra='forbid',  # Rejects unknown fields
    ...
)
```

### 2. Missing Fields
`SimpleSearchRequest` expects:
- `filters` (List[SimpleFilter])
- `logic` (LogicOperator)
- `limit` (Literal[25, 50, 100, 250, 500, 5000])
- `rules` (Literal["strict", "flex"])

But `AdvancedSearchRequest` sends:
- `groups` (List[FilterGroup])
- `group_logic` (LogicOperator)
- `limit` (Literal[25, 50, 100, 250, 500, 5000])

### 3. Code Mismatch
The function body expects `AdvancedSearchRequest` fields:
```python
for group in search_request.groups:  # ❌ groups doesn't exist in SimpleSearchRequest
    rule_clauses = []
    for rule in group.rules:
        # ...
```

## The Error You See

When you try to use the advanced search endpoint:

```
422 Unprocessable Entity
{
    "detail": [
        {
            "type": "extra_forbidden",
            "loc": ["body", "groups"],
            "msg": "Extra inputs are not allowed"
        },
        {
            "type": "extra_forbidden",
            "loc": ["body", "group_logic"],
            "msg": "Extra inputs are not allowed"
        },
        {
            "type": "missing",
            "loc": ["body", "filters"],
            "msg": "Field required"
        }
    ]
}
```

## The Fix

### Step 1: Update router_search.py

Change line 1171 from:
```python
search_request: SimpleSearchRequest,
```

To:
```python
search_request: AdvancedSearchRequest,
```

### Step 2: Verify AdvancedSearchRequest Definition

Make sure `AdvancedSearchRequest` is defined in router_search.py (it should be around line 566):

```python
class AdvancedSearchRequest(BaseModel):
    """
    Advanced search request with grouped conditions.
    """
    model_config = ConfigDict(
        extra='forbid',
        ...
    )
    groups: List[FilterGroup] = Field(
        ..., 
        min_items=1,
        description="List of filter groups to apply"
    )
    group_logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="How to combine multiple groups (AND/OR)"
    )
    limit: Literal[25, 50, 100, 250, 500, 5000] = Field(
        default=50,
        description="Maximum number of results to return (default: 50)"
    )
```

### Step 3: Test the Fix

After fixing, test with:

```python
# Advanced search request
POST /api/search/advanced
{
    "groups": [
        {
            "condition": "AND",
            "rules": [
                {"field": "sex", "operator": "equals", "value": "Male"},
                {"field": "age_min", "operator": "gte", "value": 25}
            ]
        }
    ],
    "group_logic": "AND",
    "limit": 50
}
```

Should return 200 OK with results.

## Impact

### Current State
- ❌ Advanced search is completely broken
- ❌ Returns 422 validation error for all requests
- ❌ Cannot use grouped conditions
- ❌ Cannot use advanced operators (between, gte, lte, etc.)

### After Fix
- ✅ Advanced search works as designed
- ✅ Accepts grouped conditions with AND/OR logic
- ✅ Supports all advanced operators
- ✅ Role-based tests will pass

## Workaround (Temporary)

Until the bug is fixed, the test suite will:
1. Detect the 422 "Extra inputs" error
2. Report it as an "ENDPOINT BUG"
3. Mark the test as failed with bug note
4. Continue with other tests

The test output will show:
```
⚠️  BUG DETECTED: Advanced search endpoint has wrong request type
    router_search.py line 1171 should use AdvancedSearchRequest, not SimpleSearchRequest
    This causes Pydantic validation to reject 'groups' and 'group_logic' fields
```

## Related Files

- `router_search.py` line 1171 - The bug location
- `router_search.py` lines 566-615 - AdvancedSearchRequest definition
- `router_search.py` lines 736-795 - SimpleSearchRequest definition
- `test_roles.py` - Test suite that detects this bug

## How This Happened

Likely scenarios:
1. Copy-paste error from simple search endpoint
2. Incomplete refactoring
3. Meant to be fixed but forgot
4. Documentation updated but code wasn't

## Priority

**🔴 HIGH PRIORITY** - This breaks a major feature (advanced search)

### Affects:
- PREMIUM users (primary use case for advanced search)
- ADMIN users (also use advanced search)
- Any API consumer trying to use complex queries

### Doesn't Affect:
- PUBLIC users (don't have search access anyway)
- BASIC users (only have simple search access)

## Testing After Fix

Run the role-based test suite:
```bash
python test_driver_extended.py --roles
```

Look for:
- ✅ PREMIUM advanced_search_access should PASS
- ✅ ADMIN advanced_search_access should PASS
- ✅ BASIC advanced_search_denied should PASS (403 Forbidden)
- ✅ PUBLIC advanced_search should fail (401 Unauthorized)

## One-Line Fix

In `router_search.py` line 1171, change:
```python
search_request: SimpleSearchRequest,
```
To:
```python
search_request: AdvancedSearchRequest,
```

That's it! One word change. 🎯
