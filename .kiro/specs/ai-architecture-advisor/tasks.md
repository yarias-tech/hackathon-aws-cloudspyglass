# Implementation Plan: AI Architecture Advisor

## Overview

This plan implements the AI Architecture Advisor feature in CloudSpyglass, adding AI-powered infrastructure analysis capabilities. The implementation follows the existing FastAPI + Pydantic backend pattern and React 19 + TypeScript frontend pattern. Tasks are ordered to build foundational models and services first, then wire up API routes and UI components, finishing with end-to-end integration.

## Tasks

- [x] 1. AI Credential Models and Manager Service (Backend)
  - [x] 1.1 Create `backend/models/ai_credentials.py` with AiCredentialSubmission, AiCredentialStatus, AiValidationResult Pydantic models
    - Include field constraints: base_url max 512 chars, api_key max 512 chars, model max 256 chars
    - AiCredentialStatus includes connected, source (Literal["custom", "environment", "none"]), model, validated_at
    - _Requirements: 9.1, 9.2, 9.3, 9.5_
  - [x] 1.2 Create `backend/services/ai_credential_manager.py` with AiCredentialManager class
    - Implement set_credentials, clear_credentials, get_status, get_client, get_model methods
    - Implement HTTPS-only validation for base_url (reject if not starting with `https://`)
    - Implement health check validation via `client.models.list()` on credential save
    - Implement fallback to environment variables (AI_API_BASE_URL, AI_API_KEY, AI_API_MODEL) when no custom credentials set
    - Never log or expose the api_key value
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - [x] 1.3 Add `openai>=1.0.0` to pyproject.toml dependencies
    - _Requirements: 3.1_
  - [ ]* 1.4 Write unit tests for AiCredentialManager
    - Test HTTPS enforcement (reject http:// URLs)
    - Test whitespace rejection for api_key and model
    - Test credential priority (UI overrides env, clearing reverts to env)
    - Test get_client() returning correct configuration
    - **Property 8: HTTPS-Only Enforcement for AI Base URL**
    - **Validates: Requirements 9.5**
    - _Requirements: 9.4, 9.5_

- [x] 2. AI Credentials API Route (Backend)
  - [x] 2.1 Create `backend/routes/ai_credentials.py` with POST /api/ai-credentials, GET /api/ai-credentials/status, DELETE /api/ai-credentials endpoints
    - POST validates submission and calls set_credentials
    - GET returns current credential status
    - DELETE clears custom credentials and reverts to env fallback
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 2.2 Add ai_credential_manager singleton to `backend/dependencies.py` and register router in `backend/main.py`
    - Follow existing pattern of importing from services and creating singleton instance
    - _Requirements: 9.1_
  - [ ]* 2.3 Write integration tests for AI credentials endpoints
    - POST with valid HTTPS URL returns 200
    - POST with HTTP URL returns 400
    - POST with empty/whitespace fields returns 400
    - GET status returns correct source
    - DELETE clears and reverts to env source
    - _Requirements: 9.4, 9.5_

- [x] 3. Checkpoint - Core credentials working
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Context Serializer (Backend)
  - [x] 4.1 Create `backend/services/context_serializer.py` with ContextSerializer class
    - Implement serialize method accepting ScanResult, pillars list, and max_tokens
    - Implement filtering of is_external and is_unresolved resources
    - Implement resource serialization (ARN, resource_type, name, region, tags, attributes)
    - Implement relationship serialization (source_arn, target_arn, category, derived_from)
    - _Requirements: 2.1, 2.2, 2.6_
  - [x] 4.2 Implement token budget enforcement and priority-based truncation
    - Use character-based estimation (1 token ≈ 4 chars)
    - Read max tokens from AI_API_MAX_TOKENS env var (default 120000)
    - Truncation priority: IAM/security/encryption > network > other attributes
    - Always preserve ARNs, resource_types, names, regions, tags, and relationships
    - Raise error when zero resources remain after filtering
    - _Requirements: 2.4, 2.5_
  - [ ]* 4.3 Write unit tests and property tests for ContextSerializer
    - Test serialization correctness
    - Test external/unresolved filtering
    - Test truncation priority preservation
    - Test zero-resources error
    - **Property 2: Context Serializer Excludes External and Unresolved Resources**
    - **Property 3: Context Serializer Preserves Structural Fields Under Truncation**
    - **Validates: Requirements 2.4, 2.6**
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

- [x] 5. Response Parser and Advisor Models (Backend)
  - [x] 5.1 Create `backend/models/advisor.py` with Suggestion, AdvisorResponse, AdvisorStatus, AnalyzeRequest models
    - Suggestion includes: pillar, title (max 200), description (max 2000), severity, affected_resources (max 50), remediation (max 2000), estimated_impact
    - AnalyzeRequest includes optional pillars list (max 3 items) with Literal validation
    - _Requirements: 4.1, 4.2, 4.3, 10.2_
  - [x] 5.2 Create `backend/services/response_parser.py` with ResponseParser class
    - Implement JSON parsing from AI response content
    - Implement field validation (required fields, type checking)
    - Implement field truncation (title: 200, description: 2000, remediation: 2000 chars)
    - Implement ARN validation against scan_result (remove invalid ARNs, keep suggestion with empty list)
    - Implement discard logic for unrecognized pillar/severity (with logging)
    - Implement 50 suggestion cap
    - Implement sorting: severity descending then title ascending within same severity
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 4.4, 4.7_
  - [ ]* 5.3 Write unit tests and property tests for ResponseParser
    - Test valid response parsing
    - Test field truncation
    - Test invalid ARN removal
    - Test unrecognized pillar/severity discard
    - Test max 50 cap enforcement
    - Test sorting order verification
    - **Property 1: Advisor Response Serialization Round-Trip**
    - **Property 4: Response Parser Enforces Suggestion Cap**
    - **Property 5: Response Parser Removes Invalid ARNs**
    - **Property 6: Suggestions Sorted by Severity then Title**
    - **Property 7: Field Truncation Enforces Maximum Lengths**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.6, 4.4**
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 4.4_

- [x] 6. Cloud Architect Prompt and Advisor Service Core (Backend)
  - [x] 6.1 Create `backend/services/prompts.py` with CLOUD_ARCHITECT_SYSTEM_PROMPT and build_user_message function
    - Include pillar-specific evaluation criteria in prompts
    - Security: IAM wildcard policies, open security groups, missing encryption, public accessibility, missing access logging
    - Cost_Optimization: idle resources, oversized instances, missing lifecycle policies, unattached EBS, unused EIPs, missing RI/savings plans
    - Performance: single-AZ deployments, missing caching, suboptimal instances, missing auto-scaling, read replica opportunities
    - _Requirements: 5.1, 6.1, 7.1_
  - [x] 6.2 Create `backend/services/advisor_service.py` with AdvisorService class
    - Implement state management (idle, in_progress, completed, failed)
    - Implement start_analysis: validate scan exists with completed status, reject concurrent requests (409), validate pillars, default to all pillars, launch background task
    - Implement run_analysis: call AI via client.chat.completions.create with system + user messages
    - Implement retry logic: exponential backoff (1s, 2s, 4s) for 429/5xx, no retry for other 4xx
    - Implement 60-second timeout
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 8.7_
  - [ ]* 6.3 Write unit tests for AdvisorService
    - Test rejects when no completed scan exists
    - Test rejects concurrent in_progress analysis
    - Test retry logic on 429/5xx, no retry on 4xx
    - Test timeout handling
    - Test state transitions (idle → in_progress → completed/failed)
    - Test default to all pillars when none specified
    - _Requirements: 1.1, 1.2, 1.5, 3.4, 3.5, 3.6, 3.8, 8.7_

- [x] 7. Checkpoint - Backend services complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Advisor API Endpoints (Backend)
  - [x] 8.1 Create `backend/routes/advisor.py` with POST /api/advisor/analyze, GET /api/advisor/status, GET /api/advisor/results endpoints
    - POST returns 202 with task_id on success
    - POST returns 409 when analysis in progress
    - POST returns 422 for invalid pillar values
    - POST returns 400 for missing scan/missing config
    - GET /status returns current analysis state
    - GET /results returns AdvisorResponse or 404
    - Run analysis as background task (asyncio.create_task or BackgroundTasks)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - [x] 8.2 Add advisor_service singleton to `backend/dependencies.py` and register advisor router in `backend/main.py`
    - _Requirements: 8.1_
  - [ ]* 8.3 Write integration tests for advisor endpoints
    - Test full flow POST → status → results
    - Test error codes (409, 422, 400, 404)
    - Mock OpenAI SDK to avoid real API calls
    - _Requirements: 8.2, 8.3, 8.6, 8.7_

- [x] 9. AI Credentials UI Section on Settings Page (Frontend)
  - [x] 9.1 Create `frontend/src/types/aiCredentials.ts` with AiCredentialSubmission and AiCredentialStatus types
    - _Requirements: 9.1, 9.2, 9.3_
  - [x] 9.2 Add collapsible "Define your own A.I. API credentials" section to SettingsPage
    - Add toggle button to show/hide credential form
    - Add form fields: Base URL (text), Model (text), API Key (password)
    - Add "Validate & Save" submit button with loading state
    - Display status badge when configured (masked key, model name)
    - Add "Reset to defaults" button that calls DELETE endpoint
    - Fetch AI credential status on mount
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [ ]* 9.3 Write component tests for AI credentials UI
    - Test form renders, submits, displays status
    - Test toggle behavior, error states
    - _Requirements: 9.4, 9.5_

- [x] 10. Advisor UI Panel (Frontend)
  - [x] 10.1 Create `frontend/src/types/advisor.ts` with Pillar, Severity, Suggestion, AdvisorResponse, AdvisorStatus, AnalyzeRequest types
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 10.2 Create `frontend/src/components/AdvisorPanel.tsx` component
    - Implement pillar selector (checkboxes for Security, Cost_Optimization, Performance)
    - Implement "Analyze Architecture" button with disabled states (no scan, analysis in progress)
    - Implement status polling during in_progress state
    - Implement results display: tabbed/accordion by pillar with suggestion cards
    - Implement severity color coding (critical=red, high=orange, medium=yellow, low=blue)
    - _Requirements: 1.3, 4.2, 4.3, 4.4, 8.1, 8.4_
  - [x] 10.3 Add Advisor page/route to App.tsx router and navigation link in NavHeader
    - _Requirements: 8.1_
  - [ ]* 10.4 Write component tests for AdvisorPanel
    - Test pillar selection and button states
    - Test status polling and transitions
    - Test results rendering with mock data
    - _Requirements: 4.4, 8.4_

- [x] 11. End-to-End Integration and Wiring (Full Stack)
  - [x] 11.1 Add env var placeholders to docker-compose.dev.yml (AI_API_BASE_URL, AI_API_KEY, AI_API_MODEL, AI_API_MAX_TOKENS)
    - _Requirements: 9.1, 9.2, 9.3_
  - [x] 11.2 Verify dependencies.py has ai_credential_manager and advisor_service singletons correctly wired
    - Confirm advisor_service receives ai_credential_manager, scan_storage, and response_parser dependencies
    - _Requirements: 8.1, 9.1_
  - [ ]* 11.3 Write integration test: full flow with mocked AI API
    - Configure creds → scan → analyze → results
    - Test credential fallback (no custom creds → env vars used)
    - _Requirements: 1.1, 3.1, 9.1, 10.6_

- [x] 12. Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI + Pydantic) and the frontend uses TypeScript (React 19 + Vite)
- Property test libraries: hypothesis (backend), fast-check (frontend)
- All OpenAI SDK calls should be mocked in tests to avoid real API costs

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "5.1"] },
    { "id": 2, "tasks": ["1.4", "2.1", "4.1", "5.2", "9.1", "10.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.2", "5.3", "6.1", "9.2", "10.2"] },
    { "id": 4, "tasks": ["4.3", "6.2", "9.3", "10.3"] },
    { "id": 5, "tasks": ["6.3", "8.1", "10.4"] },
    { "id": 6, "tasks": ["8.2", "8.3"] },
    { "id": 7, "tasks": ["11.1", "11.2"] },
    { "id": 8, "tasks": ["11.3"] }
  ]
}
```
