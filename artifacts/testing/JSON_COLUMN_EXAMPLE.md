# JSON Column - Example Output

## What You'll See in the Markdown Report

### Example 1: Failed Tests Table (Detailed Results by Role)

```markdown
#### ❌ Failed Tests

| Test | Issue | Details | JSON Returned |
|------|-------|---------|---------------|
| `advanced_search_denied` | Authorization | Status: 422<br>❌ Validation error | `{"detail": [{"type": "extra_forbidden", "loc": ["body", "groups"], "msg": "Extra inputs are not allowed"}, {"type": "extra_forbidden", "loc": ["body", "group_logic"], "msg": "Extra inputs are not allowed"}, {"type": "missing", "loc": ["body", "filters"], "msg": "Field required"}]}` |
| `limit_50_denied` | Authorization | Status: 200<br>❌ Succeeded when should have failed | `{"query": {"filters": [{"field": "sex", "value": "Male"}], "logic": "AND", "limit": 50}, "role": "basic", "data_field": "full_data", "resultcount": 45, "items": "[45 items - truncated for brevity]"}` |
```

**Renders as:**

#### ❌ Failed Tests

| Test | Issue | Details | JSON Returned |
|------|-------|---------|---------------|
| `advanced_search_denied` | Authorization | Status: 422<br>❌ Validation error | `{"detail": [{"type": "extra_forbidden", "loc": ["body", "groups"], "msg": "Extra inputs are not allowed"}...]}` |
| `limit_50_denied` | Authorization | Status: 200<br>❌ Succeeded when should have failed | `{"query": {...}, "role": "basic", "resultcount": 45, "items": "[45 items - truncated]"}` |

---

### Example 2: All Failed Tests Table

```markdown
## ❌ All Failed Tests

| Priority | Role | Test | Issue | Recommended Action | JSON Returned |
|----------|------|------|-------|--------------------|--------------| 
| 🔴 High | **PUBLIC** | `etl_load` | Authentication failure | Check TEST_KEYS config | `N/A` |
| 🟠 Medium | **BASIC** | `advanced_search_denied` | Status: 422 | Review endpoint logic | `{"detail": [{"type": "extra_forbidden", "loc": ["body", "groups"], "msg": "Extra inputs are not allowed"}...]}` |
| 🟠 Medium | **BASIC** | `limit_50_denied` | Access control broken | Review role requirements | `{"query": {...}, "role": "basic", "resultcount": 45, "items": "[45 items - truncated]"}` |
```

**Renders as:**

## ❌ All Failed Tests

| Priority | Role | Test | Issue | Recommended Action | JSON Returned |
|----------|------|------|-------|--------------------|--------------| 
| 🔴 High | **PUBLIC** | `etl_load` | Authentication failure | Check TEST_KEYS config | `N/A` |
| 🟠 Medium | **BASIC** | `advanced_search_denied` | Status: 422 | Review endpoint logic | `{"detail": [{"type": "extra_forbidden"...}]}` |
| 🟠 Medium | **BASIC** | `limit_50_denied` | Access control broken | Review role requirements | `{"query": {...}, "role": "basic"}` |

---

## Key Features

### ✅ Automatic Truncation
- Large JSON (like search results with 'items') are truncated
- `"items": [45 items - truncated for brevity]` instead of 50KB of data
- JSON limited to ~400-500 chars in tables

### ✅ Error Details Visible
You can instantly see:
- **Validation errors**: `"Extra inputs are not allowed"`
- **Field mismatches**: `"Field required"` 
- **What was sent**: The query parameters
- **What was received**: Status, counts, errors

### ✅ N/A for Missing Data
If JSON wasn't captured (like auth failures before request is made), shows `N/A`

---

## Real-World Examples

### Advanced Search Bug
```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": ["body", "groups"],
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

**Diagnosis:** Endpoint expects `SimpleSearchRequest` but we're sending `AdvancedSearchRequest`. Instant diagnosis!

### Limit Enforcement Failure
```json
{
  "query": {
    "filters": [{"field": "sex", "value": "Male"}],
    "limit": 50
  },
  "role": "basic",
  "data_field": "full_data",
  "resultcount": 45,
  "items": "[45 items - truncated for brevity]"
}
```

**Diagnosis:** BASIC role requested limit=50 and got 45 results. Should have gotten 403 Forbidden!

### Authentication Failure
```json
N/A
```

**Diagnosis:** No JSON because we couldn't even get a token. Check TEST_KEYS.

---

## How It Helps Debug

### Before (No JSON Column)
```
❌ limit_50_denied - Status: 200, should have been denied
```
**You think:** "Why did it succeed? What happened?"
**You do:** Run test again, check logs, add print statements

### After (With JSON Column)
```
❌ limit_50_denied - Status: 200, should have been denied
   JSON: {"role": "basic", "resultcount": 45, "limit": 50}
```
**You see:** "Oh! It actually returned 45 results with limit 50. The role enforcement isn't working."
**You do:** Go directly to `validate_limit_for_role()` and fix it

---

## What Gets Truncated

### Large Arrays
**Before truncation:**
```json
{
  "items": [
    {"uid": "123", "title": "...", "full_data": {...}},
    {"uid": "456", "title": "...", "full_data": {...}},
    ... 45 more items ...
  ]
}
```

**After truncation:**
```json
{
  "items": "[47 items - truncated for brevity]"
}
```

### Long JSON
If JSON > 500 chars, truncated with `...`
```json
`{"detail": [{"type": "extra_forbidden", "loc": ["body", "groups"]...}` 
```

---

## Summary

You now get:
✅ Instant error diagnosis  
✅ No need to re-run failed tests  
✅ No log hunting  
✅ Clear evidence of what went wrong  
✅ Automatically truncated (no massive JSON dumps)

**Perfect for debugging!** 🎯
