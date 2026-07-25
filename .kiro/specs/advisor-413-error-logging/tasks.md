# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - CloudSpyglassError Details Lost in Logging
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope property to cases where `CloudSpyglassError` has a non-null `details` field and is caught in `run_analysis`
  - Test file: `backend/tests/test_advisor_413_bug_condition.py`
  - Use Hypothesis to generate `CloudSpyglassError` instances with varying non-null `details` strings
  - Mock the analysis pipeline to raise `CloudSpyglassError(error_code="AI_CLIENT_ERROR", message="AI API rejected the request with status 413.", details=<generated_details>)`
  - Capture log output from `run_analysis` using `caplog` or a log handler
  - Assert that `details` content IS present in the captured log output (this assertion will FAIL on unfixed code, confirming the bug)
  - Also verify: default token budget is 120,000 when `AI_API_MAX_TOKENS` is unset (confirms problematic default exists)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists: details are NOT logged, default budget is too high)
  - Document counterexamples found (e.g., `CloudSpyglassError(..., details="Maximum context length exceeded: 131072 > 32768")` — details not in log output)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Retry, Timeout, Success, and Explicit Budget Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `backend/tests/test_advisor_413_preservation.py`
  - Observe on UNFIXED code:
    - Successful AI responses are parsed and stored correctly (state transitions to COMPLETED)
    - 429 errors trigger exponential backoff retries (1s, 2s, 4s) up to 3 attempts
    - 5xx errors trigger exponential backoff retries (1s, 2s, 4s) up to 3 attempts
    - Timeout errors raise immediately without retry (state transitions to FAILED)
    - Explicit `AI_API_MAX_TOKENS=8000` env var is honored by `ContextSerializer.serialize`
  - Write property-based tests using Hypothesis:
    - For all successful AI response strings, `run_analysis` stores results and transitions to COMPLETED
    - For all 429 errors, retry logic applies backoff delays correctly
    - For all 5xx status codes (500-599), retry logic applies backoff delays correctly
    - For all timeout scenarios, error is raised immediately without retry
    - For all explicit `AI_API_MAX_TOKENS` integer values, `ContextSerializer.serialize` uses that value
  - Verify tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for Advisor 413 Error — Lost Details Logging and Excessive Default Token Budget

  - [x] 3.1 Implement enhanced error logging in `run_analysis`
    - In `backend/services/advisor_service.py`, modify the `except Exception as exc` block in `run_analysis`
    - Check if `exc` is a `CloudSpyglassError` and has a non-null `details` attribute
    - If so, log both the wrapper message and the `details` field: `logger.error("Analysis %s failed: %s | Details: %s", task_id, exc, exc.details)`
    - Also include details in `self._error`: `self._error = f"{exc} | Details: {exc.details}"` when details is present
    - For non-CloudSpyglassError exceptions or those without details, preserve current behavior: `self._error = str(exc)`
    - _Bug_Condition: isBugCondition(exc) where isinstance(exc, CloudSpyglassError) AND exc.details IS NOT NULL_
    - _Expected_Behavior: log output contains exc.details AND self._error contains exc.details_
    - _Preservation: Non-CloudSpyglassError exceptions and CloudSpyglassError with null details log as before_
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Lower default token budget in `ContextSerializer`
    - In `backend/services/context_serializer.py`, change `os.environ.get("AI_API_MAX_TOKENS", "120000")` to `os.environ.get("AI_API_MAX_TOKENS", "30000")`
    - This ensures the default budget stays within typical provider limits
    - _Bug_Condition: "AI_API_MAX_TOKENS" not in environment AND default_value == 120000_
    - _Expected_Behavior: default_value == 30000 when env var is unset_
    - _Preservation: When AI_API_MAX_TOKENS is explicitly set, that value is used unchanged_
    - _Requirements: 2.3, 3.5_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - CloudSpyglassError Details Are Logged
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (details in log output, default budget = 30000)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run: `docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_advisor_413_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Retry, Timeout, Success, and Explicit Budget Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run: `docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_advisor_413_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_advisor_413_bug_condition.py backend/tests/test_advisor_413_preservation.py -v`
  - Ensure all tests pass, ask the user if questions arise.
