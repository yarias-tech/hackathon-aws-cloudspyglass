# Implementation Plan: CloudSpyglass

## Overview

CloudSpyglass is implemented as a two-tier application: a Python/FastAPI backend for AWS scanning, relationship resolution, and data persistence, and a TypeScript/React frontend for interactive diagram rendering. The implementation proceeds bottom-up — starting with shared types and infrastructure, then backend services, then API routes, then frontend components, and finally integration wiring.

## Tasks

- [x] 1. Project scaffolding and shared types
  - [x] 1.1 Set up backend project structure
    - Create `backend/` directory with `main.py`, `services/`, `routes/`, `models/`, `tests/` directories
    - Set up `pyproject.toml` with dependencies: fastapi, uvicorn, boto3, pydantic, pytest, pytest-asyncio, hypothesis, moto, httpx
    - Create `backend/models/` with all Pydantic models (CredentialSubmission, CredentialStatus, ValidationResult, Resource, Relationship, ScanResult, ScanRequest, RegionFailure, DiagramNode, DiagramEdge, DiagramData, TagFilter, FilterCriteria, FilteredResult, TagSuggestion, ExportFormat, ExportRequest, ExportResult, AutoRefreshInterval, AppSettings, ErrorResponse)
    - Create `backend/exceptions.py` with CloudSpyglassError base class and FastAPI exception handler
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 1.2 Set up frontend project structure
    - Initialize Vite + React 19 + TypeScript project in `frontend/`
    - Install dependencies: @xyflow/react 12, dagre, react-router-dom 7, jspdf, html2canvas
    - Install dev dependencies: vitest, @testing-library/react, fast-check, @testing-library/jest-dom, msw
    - Create `src/types/` with TypeScript interfaces: resources.ts, credentials.ts, filters.ts, diagram.ts, export.ts, settings.ts, errors.ts
    - Create shared `src/api/apiClient.ts` utility for standardized error handling
    - _Requirements: 5.1, 14.1_

  - [x] 1.3 Set up Docker Compose for development
    - Create `docker-compose.yml` with frontend (:5173) and backend (:8000) services
    - Create `Dockerfile` multi-stage build (Nginx on :8080 proxying /api/ to uvicorn)
    - Create `nginx.conf` for production proxying
    - _Requirements: All (infrastructure)_

- [x] 2. Backend credential management
  - [x] 2.1 Implement CredentialManager service
    - Create `backend/services/credential_manager.py`
    - Implement `set_credentials()` with in-memory storage, whitespace validation, and boto3 session creation
    - Implement `validate_credentials()` calling STS GetCallerIdentity with 10-second timeout
    - Implement `get_boto3_session()` returning session configured with latest credentials
    - Implement `clear_credentials()` removing all stored state
    - Implement `get_status()` returning CredentialStatus model
    - Support fallback to boto3 credential chain when no UI credentials are provided
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.4_

  - [x] 2.2 Write property tests for credential validation (Property 1)
    - **Property 1: Credential submission validation**
    - Test that empty/whitespace-only access_key_id or secret_access_key are rejected, non-empty are accepted
    - **Validates: Requirements 1.2, 1.6**

  - [x] 2.3 Write property tests for credential replacement (Property 2)
    - **Property 2: Credential replacement**
    - Test that sequential credential submissions always result in latest credentials being active
    - **Validates: Requirements 1.4**

  - [x] 2.4 Write property tests for credential error categorization (Property 3)
    - **Property 3: Credential error categorization**
    - Test that all validation failures produce properly structured error responses with descriptive messages
    - **Validates: Requirements 2.3**

  - [x] 2.5 Implement credential API routes
    - Create `backend/routes/credentials.py`
    - POST `/api/credentials` — submit and validate credentials
    - GET `/api/credentials/status` — return current credential status
    - DELETE `/api/credentials` — clear stored credentials
    - _Requirements: 1.2, 2.1, 2.4, 2.5_

- [x] 3. Backend scanning service
  - [x] 3.1 Implement Scanner service
    - Create `backend/services/scanner.py`
    - Implement `scan()` method orchestrating multi-region parallel scanning
    - Implement `_scan_region()` with per-region 60-second timeout
    - Implement `_scan_resource_type()` for each supported resource type (EC2, SG, VPC, Subnet, S3, Lambda, RDS, IAM roles, ALB/NLB, ECS, SNS, SQS, DynamoDB, CloudFront, Route53, API Gateway)
    - Implement `_discover_enabled_regions()` via EC2 DescribeRegions
    - Implement exponential backoff retry logic: delay = min(2^(n-1), 30) seconds, max 5 retries
    - Implement total 10-minute scan timeout with cancellation of remaining regions
    - Enrich resources with tags, creation_date, iam_role, and service-specific attributes
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 3.2 Write property tests for region selection (Property 4)
    - **Property 4: Region selection scan targeting**
    - Test that Scanner targets exactly the specified regions, or discovers all if empty
    - **Validates: Requirements 3.1**

  - [x] 3.3 Write property tests for exponential backoff (Property 5)
    - **Property 5: Exponential backoff calculation**
    - Test that for retry n (1..5), delay = min(2^(n-1), 30)
    - **Validates: Requirements 3.4**

  - [x] 3.4 Write property tests for partial failure handling (Property 6)
    - **Property 6: Partial region failure handling**
    - Test that successful regions produce resources and failed regions produce failure entries
    - **Validates: Requirements 3.5**

  - [x] 3.5 Implement scan API routes
    - Create `backend/routes/scan.py`
    - POST `/api/scan` — trigger a new scan (reject if already in progress with SCAN_IN_PROGRESS)
    - GET `/api/scan/status` — return current scan progress
    - _Requirements: 3.1, 3.2_

- [x] 4. Checkpoint — Backend scanning verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Backend relationship resolution
  - [x] 5.1 Implement RelationshipResolver service
    - Create `backend/services/relationship_resolver.py`
    - Implement `resolve()` orchestrating all category resolvers
    - Implement `_resolve_network_relationships()` — SG attachments, VPC memberships, LB targets
    - Implement `_resolve_iam_relationships()` — role associations for Lambda, EC2, ECS
    - Implement `_resolve_event_relationships()` — event source mappings, S3 notifications
    - Implement `_resolve_data_relationships()` — RDS subnet group memberships
    - Implement `_classify_external()` — detect cross-account ARNs and non-AWS hostnames
    - Handle unresolved targets: record relationship and mark target as is_unresolved=True
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.2 Write property tests for network relationship detection (Property 7)
    - **Property 7: Network relationship detection**
    - Test that EC2→SG, EC2→VPC, EC2→Subnet, RDS→VPC, Lambda→VPC, LB→targets produce correct network relationships
    - **Validates: Requirements 4.1**

  - [x] 5.3 Write property tests for IAM relationship detection (Property 8)
    - **Property 8: IAM relationship detection**
    - Test that Lambda, EC2, ECS with IAM role associations produce iam category relationships
    - **Validates: Requirements 4.2**

  - [x] 5.4 Write property tests for event relationship detection (Property 9)
    - **Property 9: Event relationship detection**
    - Test that SQS→Lambda, SNS→Lambda, S3→Lambda/SQS/SNS produce event category relationships
    - **Validates: Requirements 4.3**

  - [x] 5.5 Write property tests for external component classification (Property 10)
    - **Property 10: External component classification**
    - Test that cross-account ARNs and non-*.amazonaws.com hostnames are classified as external
    - **Validates: Requirements 4.5**

  - [x] 5.6 Write property tests for unresolved target preservation (Property 11)
    - **Property 11: Unresolved target preservation**
    - Test that missing target ARNs still produce relationships with is_unresolved=True on target
    - **Validates: Requirements 4.7**

- [x] 6. Backend filter engine
  - [x] 6.1 Implement FilterEngine service
    - Create `backend/services/filter_engine.py`
    - Implement `apply_filters()` with AND logic for tags and OR logic for resource types
    - Filter edges: tag-filtered edges require both endpoints in filtered set; type-filtered edges require at least one endpoint in filtered set
    - Implement combined filter: intersection of tag AND type filters
    - Implement `get_tag_suggestions()` returning top 20 by descending frequency
    - _Requirements: 7.1, 7.3, 7.4, 7.6, 8.1, 8.2, 8.4, 8.5_

  - [x] 6.2 Write property tests for tag filter AND logic (Property 14)
    - **Property 14: Tag filter AND logic with edge filtering**
    - Test that filtered results contain only resources matching ALL tag criteria and edges where BOTH endpoints match
    - **Validates: Requirements 7.1, 7.3, 7.4**

  - [x] 6.3 Write property tests for tag autocomplete ordering (Property 15)
    - **Property 15: Tag autocomplete frequency ordering**
    - Test that suggestions return ≤20 entries ordered by descending frequency
    - **Validates: Requirements 7.2**

  - [x] 6.4 Write property tests for filter removal round-trip (Property 16)
    - **Property 16: Filter removal round-trip**
    - Test that applying then removing all filters produces original unfiltered result
    - **Validates: Requirements 7.6**

  - [x] 6.5 Write property tests for resource type filter options (Property 17)
    - **Property 17: Resource type filter available options**
    - Test that available type options equal the set of distinct resource_type values in scan data
    - **Validates: Requirements 8.1**

  - [x] 6.6 Write property tests for resource type OR logic (Property 18)
    - **Property 18: Resource type OR logic with edge visibility**
    - Test that filtered results contain resources matching ANY selected type, plus edges with at least one endpoint of selected type
    - **Validates: Requirements 8.2**

  - [x] 6.7 Write property tests for combined filter intersection (Property 19)
    - **Property 19: Combined filter intersection**
    - Test that combined tag + type filters produce intersection (ALL tags AND at least one type)
    - **Validates: Requirements 8.5**

  - [x] 6.8 Implement filter API routes
    - Create `backend/routes/filters.py`
    - GET `/api/tags/suggestions?prefix={prefix}` — return tag autocomplete suggestions
    - Create `backend/routes/diagrams.py`
    - GET `/api/diagrams/latest` — return latest diagram data
    - GET `/api/diagrams/latest/filtered` — return filtered diagram data (accepts FilterCriteria as query params)
    - _Requirements: 7.2, 5.1_

- [x] 7. Backend scan storage
  - [x] 7.1 Implement ScanStorage service
    - Create `backend/services/scan_storage.py`
    - Implement `save()` with atomic write (write to temp file, then os.replace)
    - Implement `load()` with JSON parsing and Pydantic validation
    - Implement `exists()` check
    - Create `data/` directory if not exists
    - Handle corrupt/invalid files: discard and return None
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 7.2 Write property tests for persistence round-trip (Property 21)
    - **Property 21: Scan result persistence round-trip**
    - Test that serialize→deserialize produces equivalent ScanResult
    - **Validates: Requirements 10.1**

  - [x] 7.3 Write property tests for single file per account (Property 22)
    - **Property 22: Single file per account invariant**
    - Test that sequential saves for same account_id result in exactly one file
    - **Validates: Requirements 10.3**

  - [x] 7.4 Write property tests for write failure preservation (Property 23)
    - **Property 23: Write failure preserves previous file**
    - Test that failed writes leave the previous file unchanged
    - **Validates: Requirements 10.5**

  - [x] 7.5 Write property tests for corrupt file handling (Property 24)
    - **Property 24: Corrupt file graceful handling**
    - Test that invalid UTF-8, invalid JSON, or schema-violating content returns None
    - **Validates: Requirements 10.6**

- [x] 8. Backend export service
  - [x] 8.1 Implement ExportService
    - Create `backend/services/export_service.py`
    - Implement `export()` generating PDF, PNG, SVG from diagram data
    - Implement `_generate_filename()` with pattern {Account_ID}_{YYYYMMDD_HHmmss}.{format}
    - Implement `_check_size_limit()` rejecting exports exceeding 50 MB
    - Apply filter annotations when filters are active
    - Enforce 30-second export timeout
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 8.2 Write property tests for export filename format (Property 25)
    - **Property 25: Export filename format**
    - Test that generated filenames match {Account_ID}_{YYYYMMDD_HHmmss}.{format} pattern
    - **Validates: Requirements 11.3**

  - [x] 8.3 Write property tests for export size limit (Property 26)
    - **Property 26: Export size limit enforcement**
    - Test that exports exceeding 50 MB are rejected without producing a file
    - **Validates: Requirements 11.6**

  - [x] 8.4 Write property tests for filtered export annotation (Property 27)
    - **Property 27: Filtered export annotation**
    - Test that exports with active filters contain only filtered resources and include filter annotation
    - **Validates: Requirements 11.2**

  - [x] 8.5 Implement export API route
    - Create `backend/routes/export.py`
    - POST `/api/export` — trigger export with format and optional filters
    - _Requirements: 11.4_

- [x] 9. Backend icon and image serving
  - [x] 9.1 Implement image serving routes
    - Create `backend/routes/images.py`
    - GET `/api/images/icons/{service_type}` — serve SVG icon from assets/icons/
    - GET `/api/images/logo` — serve application logo from assets/logo/
    - Validate service_type against known resource types (return 400 for unknown)
    - Return 404 for valid service_type with missing file
    - Set correct Content-Type headers (image/svg+xml for SVG)
    - _Requirements: 13.1, 13.2, 13.3, 13.6, 13.7_

  - [x] 9.2 Write property tests for icon endpoint correctness (Property 28)
    - **Property 28: Icon endpoint correctness**
    - Test that valid service_type with existing SVG returns content with image/svg+xml
    - **Validates: Requirements 13.2**

  - [x] 9.3 Write property tests for icon error handling (Property 29)
    - **Property 29: Icon error handling**
    - Test that unknown service_type returns 400 and missing file returns 404, both with standard error structure
    - **Validates: Requirements 13.6, 13.7**

- [x] 10. Backend settings and error handling
  - [x] 10.1 Implement settings API routes
    - Create `backend/routes/settings.py`
    - GET `/api/settings` — return current AppSettings
    - PUT `/api/settings` — update auto-refresh interval and selected regions
    - _Requirements: 12.1, 12.2_

  - [x] 10.2 Write property tests for error response structure (Property 30)
    - **Property 30: Error response structure invariant**
    - Test that all error responses contain exactly: error_code (UPPER_SNAKE_CASE), message (≤500 chars), details (string|null), timestamp (ISO 8601 UTC), recoverable (boolean)
    - **Validates: Requirements 14.1**

  - [x] 10.3 Write property tests for error recoverability classification (Property 31)
    - **Property 31: Error recoverability classification**
    - Test that transient errors (timeout, throttle) have recoverable=true and permanent errors (invalid input, auth failure) have recoverable=false
    - **Validates: Requirements 14.2, 14.3**

- [x] 11. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Frontend diagram rendering
  - [x] 12.1 Implement DiagramCanvas and layout engine
    - Create `src/components/DiagramCanvas.tsx` wrapping @xyflow/react ReactFlow
    - Implement dagre layout with top-to-bottom rank direction
    - Configure pan and zoom (0.25x to 4.0x range, fitView on initial load)
    - Handle empty state (no scan data) with EmptyState component
    - _Requirements: 5.4, 5.5, 5.7_

  - [x] 12.2 Implement ResourceNode custom node
    - Create `src/components/ResourceNode.tsx` with icon, name, and type display
    - Load icons from `/api/images/icons/{service_type}`
    - Display dashed border for external components
    - Show placeholder icon on load failure
    - _Requirements: 5.1, 5.6, 5.9_

  - [x] 12.3 Implement RelationshipEdge custom edge
    - Create `src/components/RelationshipEdge.tsx` with category-based styling
    - Blue solid for network, green dashed for iam, orange dotted animated for event, gray solid for data
    - Implement tooltip on hover (within 200ms) showing interaction type, source, target, derived_from
    - _Requirements: 5.3, 5.8_

  - [x] 12.4 Write property tests for edge styling (Property 12)
    - **Property 12: Edge styling by category**
    - Test that each relationship category maps to correct color/style/animation
    - **Validates: Requirements 5.3**

- [x] 13. Frontend detail panel
  - [x] 13.1 Implement DetailPanel component
    - Create `src/components/DetailPanel.tsx` as a slide-in overlay from the right
    - Display: resource type, ARN, region, tags, creation_date, iam_role, service-specific attributes
    - Omit sections for non-applicable metadata fields
    - Handle loading state with indicator, 10-second timeout
    - Handle error state with standard error message
    - Close on Escape key or close button, returning focus to diagram
    - Replace content when different node is clicked while panel is open
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 13.2 Write property tests for detail panel metadata completeness (Property 13)
    - **Property 13: Detail panel metadata completeness**
    - Test that all applicable fields are shown and non-applicable fields are omitted per resource type
    - **Validates: Requirements 6.1**

- [x] 14. Frontend filter components
  - [x] 14.1 Implement FilterBar, TagFilterInput, and TypeFilterSelect
    - Create `src/components/FilterBar.tsx` containing tag and type filter controls
    - Create `src/components/TagFilterInput.tsx` with autocomplete (fetches from /api/tags/suggestions)
    - Create `src/components/TypeFilterSelect.tsx` as multi-select of resource types from scan data
    - Display filtered count vs total count when filters are active
    - Show empty state when no resources match filters
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 8.1, 8.3_

  - [x] 14.2 Write frontend property tests for filter logic (Properties 14, 16, 17, 18, 19)
    - **Property 14: Tag filter AND logic with edge filtering**
    - **Property 16: Filter removal round-trip**
    - **Property 17: Resource type filter available options**
    - **Property 18: Resource type OR logic with edge visibility**
    - **Property 19: Combined filter intersection**
    - Create `src/__tests__/properties/filter.property.test.ts`
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.6, 8.1, 8.2, 8.5**

  - [x] 14.3 Write frontend property tests for tag suggestions (Property 15)
    - **Property 15: Tag autocomplete frequency ordering**
    - Create `src/__tests__/properties/tag-suggestions.property.test.ts`
    - **Validates: Requirements 7.2**

- [x] 15. Frontend pages and navigation
  - [x] 15.1 Implement DiagramPage
    - Create `src/pages/DiagramPage.tsx` as main route (/)
    - Integrate DiagramCanvas, FilterBar, ExportMenu, ScanControls, DetailPanel
    - Fetch diagram data from GET /api/diagrams/latest
    - Apply client-side filter state management
    - _Requirements: 5.1, 7.1, 8.1_

  - [x] 15.2 Implement SettingsPage
    - Create `src/pages/SettingsPage.tsx` at route /settings
    - Include CredentialForm, RegionSelector, auto-refresh interval selector
    - Display credential status (Connected/Disconnected/Expired), Account_ID, expiry
    - Loading indicator during credential validation, disabled submit button
    - Disconnect button with credential clearing
    - _Requirements: 1.1, 2.2, 2.5, 2.6, 3.1, 12.1, 12.3, 12.4, 12.5_

  - [x] 15.3 Implement NavHeader, AppLogo, and routing
    - Create `src/components/NavHeader.tsx` with logo and navigation links
    - Create `src/components/AppLogo.tsx` loading logo from /api/images/logo
    - Configure react-router-dom routes: / (DiagramPage), /settings (SettingsPage)
    - _Requirements: 13.4, 13.5_

- [x] 16. Frontend scan controls and auto-refresh
  - [x] 16.1 Implement ScanControls and auto-refresh logic
    - Create `src/components/ScanControls.tsx` with manual refresh button
    - Implement auto-refresh timer based on AppSettings.auto_refresh_interval
    - Skip scheduled scan if one is already in progress
    - Reset timer on manual refresh
    - Display non-blocking refresh indicator while scan is in progress
    - Retain current diagram on refresh failure, show error
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 16.2 Write property tests for diagram state preservation on refresh failure (Property 20)
    - **Property 20: Diagram state preservation on refresh failure**
    - Test that failed auto-refresh leaves diagram data unchanged
    - **Validates: Requirements 9.4**

- [x] 17. Frontend export
  - [x] 17.1 Implement ExportMenu component
    - Create `src/components/ExportMenu.tsx` with PDF, PNG, SVG format selection
    - Trigger POST /api/export with format and current filter criteria
    - Handle export errors and display appropriate messages
    - _Requirements: 11.1, 11.2_

- [x] 18. Checkpoint — Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Integration wiring and end-to-end
  - [x] 19.1 Wire backend FastAPI application
    - Create `backend/main.py` with all route registrations, CORS middleware, exception handlers
    - Register all routers: credentials, scan, diagrams, filters, export, settings, images
    - Inject service dependencies (CredentialManager, Scanner, ScanStorage, FilterEngine, ExportService, RelationshipResolver)
    - _Requirements: All backend_

  - [ ] 19.2 Wire frontend App entry point
    - Create `src/App.tsx` with router configuration and global error boundary
    - Create `src/components/ErrorBanner.tsx` for global error display
    - Create `src/components/LoadingSpinner.tsx` shared loading indicator
    - Ensure all pages and components are integrated
    - _Requirements: All frontend_

  - [ ]* 19.3 Write backend integration tests
    - Test full scan flow with moto (credential submission → scan → relationship resolution → storage)
    - Test API endpoint contracts with httpx TestClient
    - Test file atomicity under concurrent writes
    - _Requirements: 3.2, 4.1, 10.2_

  - [ ]* 19.4 Write frontend integration tests
    - Test page-level flows with MSW (mock service worker)
    - Test credential submission → scan → diagram rendering flow
    - Test filter interaction flow
    - _Requirements: 5.1, 7.1, 8.1_

- [ ] 20. Final checkpoint — All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (31 properties from design)
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.12+ with FastAPI, pytest + hypothesis for property tests
- Frontend uses TypeScript with React 19, Vitest + fast-check for property tests
- Development: Docker Compose (frontend :5173, backend :8000)
- Production: Single multi-stage Docker image (Nginx :8080 → uvicorn :8000)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "7.1", "9.1", "10.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "7.2", "7.3", "7.4", "7.5", "9.2", "9.3", "10.2", "10.3"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5"] },
    { "id": 5, "tasks": ["5.1", "6.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "8.4", "8.5"] },
    { "id": 9, "tasks": ["12.1", "12.2", "12.3", "13.1", "14.1"] },
    { "id": 10, "tasks": ["12.4", "13.2", "14.2", "14.3", "15.1", "15.2", "15.3"] },
    { "id": 11, "tasks": ["16.1", "17.1"] },
    { "id": 12, "tasks": ["16.2"] },
    { "id": 13, "tasks": ["19.1", "19.2"] },
    { "id": 14, "tasks": ["19.3", "19.4"] }
  ]
}
```
