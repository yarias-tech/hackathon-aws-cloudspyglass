# Advisor 413 Error Logging Bugfix Design

## Overview

When the AI Architecture Advisor sends a request that exceeds the AI provider's context window or body size limit, the API returns HTTP 413. The backend's `run_analysis` catch-all handler logs only the wrapper message from `CloudSpyglassError` (via `str(exc)`) and discards the `details` field containing the provider's actual diagnostic message. Additionally, the default token budget of 120,000 tokens exceeds what many providers support, making 413 errors a common occurrence with large scans.

The fix addresses both problems: (1) improve error logging to include the `details` field when present, and (2) lower the default token budget to 30,000 tokens to stay within typical provider limits.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a `CloudSpyglassError` with a non-null `details` field is caught by `run_analysis`, or the default token budget exceeds provider limits
- **Property (P)**: The desired behavior — error logs include both the wrapper message and the `details` field; the default token budget is 30,000
- **Preservation**: Existing retry logic, timeout handling, successful analysis flow, and user-provided `AI_API_MAX_TOKENS` values must remain unchanged
- **`run_analysis`**: The background task method in `backend/services/advisor_service.py` that orchestrates the full AI analysis pipeline
- **`_call_ai_with_retry`**: The retry method that catches `APIStatusError` and wraps 4xx errors into `CloudSpyglassError` with a `details` field
- **`ContextSerializer.serialize`**: Method in `backend/services/context_serializer.py` that reads `AI_API_MAX_TOKENS` env var (defaulting to 120,000)

## Bug Details

### Bug Condition

The bug manifests in two scenarios:

1. When `_call_ai_with_retry` catches a 4xx `APIStatusError` (non-429), it creates a `CloudSpyglassError` with `details=str(exc.message)`. This exception propagates to the `except Exception` block in `run_analysis`, which logs only `str(exc)` — the wrapper `message` field — and drops the `details` field entirely.

2. When `AI_API_MAX_TOKENS` is not set, `ContextSerializer.serialize` defaults to 120,000 tokens, which exceeds the limits of many providers (Groq: 8K-32K, some OpenRouter models: 8K-128K), making HTTP 413 errors likely for large scans.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type (Exception raised during run_analysis, OR env configuration)
  OUTPUT: boolean
  
  -- Logging bug condition
  IF input IS CloudSpyglassError
    RETURN input.details IS NOT NULL
           AND log_output DOES NOT CONTAIN input.details
  
  -- Default budget bug condition
  IF input IS env_config
    RETURN "AI_API_MAX_TOKENS" NOT IN environment
           AND default_value == 120000
           AND provider_max_context < 120000
END FUNCTION
```

### Examples

- **413 with details lost**: `_call_ai_with_retry` raises `CloudSpyglassError(message="AI API rejected the request with status 413.", details="Maximum context length exceeded: 131072 tokens > 32768 max")`. `run_analysis` logs: `"Analysis xyz failed: AI API rejected the request with status 413."` — the details string is never logged.
- **Large scan with default budget**: A scan discovers 500 resources. `ContextSerializer` uses 120,000 token budget, producing a ~480KB payload. The Groq model has a 32K context limit. The API returns 413.
- **Non-CloudSpyglassError with details**: A generic `Exception("connection reset")` is caught — no `details` attribute exists. Current logging of `str(exc)` is sufficient.
- **CloudSpyglassError with null details**: `CloudSpyglassError(message="timeout", details=None)` — logging `str(exc)` captures the full message. No additional logging needed.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Successful AI analysis responses must continue to be parsed and stored normally
- 429 (rate limit) errors must continue to trigger retry with exponential backoff (1s, 2s, 4s)
- 5xx (server) errors must continue to trigger retry with exponential backoff
- Timeout errors must continue to raise immediately without retry
- When `AI_API_MAX_TOKENS` is explicitly set via environment variable, the system must use that value
- The `_call_ai_with_retry` method's creation of `CloudSpyglassError` with `details` must remain unchanged
- The state machine transitions (idle → in_progress → completed/failed) must remain unchanged

**Scope:**
All inputs that do NOT involve a `CloudSpyglassError` with a non-null `details` field reaching the `run_analysis` catch block, and all configurations where `AI_API_MAX_TOKENS` is explicitly set, should be completely unaffected by this fix. This includes:
- Successful completions
- Rate-limited requests (retried automatically)
- Server errors (retried automatically)
- Timeouts (raised directly as `CloudSpyglassError`)
- Explicitly configured token budgets

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **Insufficient logging in `run_analysis` catch-all**: The `except Exception as exc` block calls `logger.error("Analysis %s failed: %s", task_id, exc)`. For `CloudSpyglassError` instances, `str(exc)` returns only the `message` field (inherited from `Exception.__init__(message)`). The `details` field, which contains the provider's actual error text, is never accessed or logged.

2. **Overly generous default token budget**: In `context_serializer.py`, line `int(os.environ.get("AI_API_MAX_TOKENS", "120000"))` sets a default of 120,000 tokens. Many AI providers (especially via Groq and OpenRouter) have much lower limits. The context serializer dutifully truncates to fit this budget, but the budget itself exceeds what the provider accepts.

## Correctness Properties

Property 1: Bug Condition - Error Details Are Logged

_For any_ exception caught in `run_analysis` where the exception is a `CloudSpyglassError` with a non-null `details` field, the fixed logging SHALL include both the wrapper message (`str(exc)`) and the `details` field content in the log output at ERROR level.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition - Default Token Budget Is Safe

_For any_ execution where `AI_API_MAX_TOKENS` is not set in the environment, the `ContextSerializer.serialize` method SHALL use a default of 30,000 tokens for the `max_tokens` parameter.

**Validates: Requirements 2.3**

Property 3: Preservation - Retry and Timeout Behavior Unchanged

_For any_ input that triggers rate limiting (429), server errors (5xx), or timeouts, the fixed code SHALL produce exactly the same retry/raise behavior as the original code, preserving exponential backoff and immediate timeout raising.

**Validates: Requirements 3.2, 3.3, 3.4**

Property 4: Preservation - Successful Analysis Unchanged

_For any_ input where the AI API returns a successful response, the fixed code SHALL continue to parse and store results identically to the original code.

**Validates: Requirements 3.1**

Property 5: Preservation - Explicit Token Budget Honored

_For any_ configuration where `AI_API_MAX_TOKENS` is explicitly set via environment variable, the fixed code SHALL use the user-provided value, identical to the original behavior.

**Validates: Requirements 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/services/advisor_service.py`

**Function**: `run_analysis`

**Specific Changes**:
1. **Enhanced error logging**: In the `except Exception as exc` block, check if `exc` is a `CloudSpyglassError` with a non-null `details` attribute. If so, log the details separately or append them to the log message.
   - Before: `logger.error("Analysis %s failed: %s", task_id, exc)`
   - After: Log both `str(exc)` and `exc.details` when `details` is present

2. **Store details in `_error` field**: Also store the details in `self._error` so downstream consumers have access to the full diagnostic information.
   - Before: `self._error = str(exc)`
   - After: Include details when the exception is a `CloudSpyglassError` with non-null details

**File**: `backend/services/context_serializer.py`

**Function**: `serialize`

**Specific Changes**:
3. **Lower default token budget**: Change the default from `"120000"` to `"30000"` in `os.environ.get("AI_API_MAX_TOKENS", "120000")`.
   - Before: `int(os.environ.get("AI_API_MAX_TOKENS", "120000"))`
   - After: `int(os.environ.get("AI_API_MAX_TOKENS", "30000"))`

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that create a `CloudSpyglassError` with a non-null `details` field, raise it in `run_analysis`, and capture log output to verify the `details` content is absent. Also verify the default token budget value.

**Test Cases**:
1. **Missing details in log**: Create `CloudSpyglassError(message="AI API rejected with 413", details="Max context exceeded: 131072 > 32768")`, simulate it being caught in `run_analysis`, assert log output does NOT contain the details string (will fail on unfixed code — confirming the bug)
2. **Default token budget too high**: Call `ContextSerializer.serialize` without `AI_API_MAX_TOKENS` set, assert the effective budget is 120,000 (confirms the problematic default exists)
3. **Error field missing details**: After a failed analysis with a details-bearing exception, check `get_status()` or `_error` — details will be absent from the stored error string

**Expected Counterexamples**:
- Log output contains only "AI API rejected the request with status 413." without the provider's diagnostic message
- Default token budget is 120,000, confirming it exceeds common provider limits

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL exc WHERE isinstance(exc, CloudSpyglassError) AND exc.details IS NOT NULL DO
  run_analysis_fixed(raises=exc)
  ASSERT exc.details IN captured_log_output
  ASSERT exc.details IN service._error OR service._error CONTAINS exc.details
END FOR

FOR ALL env WHERE "AI_API_MAX_TOKENS" NOT IN env DO
  result := ContextSerializer().serialize(scan_result, pillars)
  ASSERT effective_max_tokens == 30000
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT run_analysis_original(input) == run_analysis_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for successful completions, retries, and timeouts, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Successful analysis preservation**: Verify that successful AI responses continue to be parsed and stored correctly after the fix
2. **Rate limit retry preservation**: Verify that 429 errors still trigger exponential backoff retries identically
3. **Server error retry preservation**: Verify that 5xx errors still trigger exponential backoff retries identically
4. **Timeout preservation**: Verify that timeouts still raise immediately without retry
5. **Explicit token budget preservation**: Verify that when `AI_API_MAX_TOKENS` is set to any value, that value is used regardless of the new default

### Unit Tests

- Test that `run_analysis` logs `details` when catching a `CloudSpyglassError` with non-null details
- Test that `run_analysis` logs normally when catching a `CloudSpyglassError` with null details
- Test that `run_analysis` logs normally when catching a non-`CloudSpyglassError` exception
- Test that `ContextSerializer.serialize` uses 30,000 as default when env var is unset
- Test that `ContextSerializer.serialize` uses env var value when `AI_API_MAX_TOKENS` is set

### Property-Based Tests

- Generate random `CloudSpyglassError` instances with varying `details` values (null, empty, long strings) and verify logging behavior is correct for each
- Generate random `AI_API_MAX_TOKENS` env var values (including unset) and verify the correct budget is used
- Generate random successful/failed analysis scenarios and verify state machine transitions are preserved

### Integration Tests

- Test full analysis flow where AI API returns 413: verify logs contain the provider's error message
- Test full analysis flow where AI API returns 200: verify results are stored correctly
- Test analysis with explicit `AI_API_MAX_TOKENS=8000`: verify context serializer uses 8000 tokens
