# Requirements Document

## Introduction

The AI Architecture Advisor feature integrates an external AI API into CloudSpyglass to provide intelligent architecture recommendations based on scanned AWS infrastructure data. The AI assumes the role of a Cloud Architect and analyzes the discovered resources and relationships to produce actionable suggestions across three pillars: Security, Cost Optimization, and Performance.

## Glossary

- **Advisor_Service**: The backend service responsible for orchestrating calls to the external AI API, preparing infrastructure context, and returning structured suggestions to the frontend.
- **AI_API_Client**: The component that handles HTTP communication with the external AI API, including authentication, request formatting, and response parsing.
- **ScanResult**: The output of a CloudSpyglass infrastructure scan containing resources, relationships, failures, and metadata.
- **Suggestion**: A single architecture recommendation returned by the AI, categorized by pillar and containing a description, affected resources, severity, and remediation guidance.
- **Pillar**: One of the three advisory categories: Security, Cost_Optimization, or Performance.
- **Advisor_Request**: The payload sent to the external AI API containing serialized infrastructure data and the Cloud Architect system prompt.
- **Advisor_Response**: The structured response from the AI API containing categorized architecture suggestions.
- **Severity**: The urgency level of a suggestion: critical, high, medium, or low.
- **Cloud_Architect_Prompt**: The system prompt instructing the AI API to assume the Cloud Architect skill and evaluate infrastructure against AWS Well-Architected best practices.

## Requirements

### Requirement 1: Trigger Architecture Analysis

**User Story:** As a cloud architect, I want to request AI-powered architecture analysis of my scanned infrastructure, so that I can identify improvements across security, cost, and performance.

#### Acceptance Criteria

1. WHEN a user requests architecture analysis, THE Advisor_Service SHALL accept the request only if a ScanResult with status "completed" exists for the current account.
2. IF no ScanResult with status "completed" exists for the current account, THEN THE Advisor_Service SHALL return an error indicating that a scan must be completed before requesting analysis.
3. WHEN a user requests architecture analysis, THE Advisor_Service SHALL allow the user to select one or more Pillars from the set (Security, Cost_Optimization, Performance).
4. WHEN no specific Pillars are selected, THE Advisor_Service SHALL analyze all three Pillars by default.
5. IF a user requests architecture analysis with a Pillar value not in the set (Security, Cost_Optimization, Performance), THEN THE Advisor_Service SHALL reject the request with an error indicating the invalid Pillar value.

### Requirement 2: Prepare Infrastructure Context for AI

**User Story:** As a system component, I want to serialize the scanned infrastructure data into a format suitable for the AI API, so that the AI can understand and analyze the architecture.

#### Acceptance Criteria

1. WHEN preparing an Advisor_Request, THE Advisor_Service SHALL include all resources from the ScanResult with their ARN, resource_type, name, region, tags, and attributes.
2. WHEN preparing an Advisor_Request, THE Advisor_Service SHALL include all relationships from the ScanResult with their source_arn, target_arn, category, and derived_from fields.
3. WHEN preparing an Advisor_Request, THE Advisor_Service SHALL include the Cloud_Architect_Prompt as the system message and the selected Pillars to analyze as part of the user message.
4. IF the serialized infrastructure data exceeds the configured maximum token budget (read from the AI_API_MAX_TOKENS environment variable, defaulting to 120000 tokens), THEN THE Advisor_Service SHALL truncate resource attributes in the following priority order — retaining IAM policies, security group rules, and encryption configuration attributes first; then network configuration attributes; then all remaining attributes — while preserving all ARNs, resource_types, names, regions, tags, and relationships intact.
5. IF the ScanResult contains zero resources, THEN THE Advisor_Service SHALL return an error indicating that the scan contains no resources to analyze.
6. WHEN preparing an Advisor_Request, THE Advisor_Service SHALL exclude resources where is_external is true or is_unresolved is true from the serialized payload.

### Requirement 3: Communicate with External AI API

**User Story:** As a system component, I want to call the external AI API with proper authentication and error handling, so that the system reliably obtains architecture suggestions.

#### Acceptance Criteria

1. THE AI_API_Client SHALL authenticate with the external AI API using an API key stored in environment variables (never hardcoded).
2. WHEN sending a request to the AI API, THE AI_API_Client SHALL include the Cloud_Architect_Prompt as the system message and the serialized infrastructure data as the user message.
3. WHEN the AI API returns an HTTP 2xx response, THE AI_API_Client SHALL parse the response body into a structured Advisor_Response.
4. IF the AI API returns a rate-limit error (HTTP 429), THEN THE AI_API_Client SHALL retry the request with exponential backoff starting at 1 second, up to 3 attempts.
5. IF the AI API returns a server error (HTTP 5xx), THEN THE AI_API_Client SHALL retry the request with exponential backoff starting at 1 second, up to 3 attempts.
6. IF the AI API is unreachable or times out after 60 seconds, THEN THE AI_API_Client SHALL return an error indicating the AI service is temporarily unavailable.
7. IF all retry attempts are exhausted, THEN THE AI_API_Client SHALL return an error with the HTTP status code and failure reason from the last attempt.
8. IF the AI API returns a client error (HTTP 4xx other than 429), THEN THE AI_API_Client SHALL immediately return an error indicating the request was rejected, without retrying.

### Requirement 4: Structure Architecture Suggestions

**User Story:** As a cloud architect, I want architecture suggestions returned in a consistent, structured format, so that I can quickly understand and prioritize recommendations.

#### Acceptance Criteria

1. THE Advisor_Service SHALL return each Suggestion with the following fields: pillar, title (maximum 120 characters), description (maximum 1000 characters), severity, affected_resources (list of 0 to 50 ARNs), and remediation (maximum 2000 characters).
2. THE Advisor_Service SHALL categorize each Suggestion under exactly one Pillar (Security, Cost_Optimization, or Performance).
3. THE Advisor_Service SHALL assign a Severity level (critical, high, medium, low) to each Suggestion.
4. THE Advisor_Service SHALL sort Suggestions within each Pillar by Severity in descending order (critical first), and by title in ascending alphabetical order when Suggestions share the same Severity.
5. WHEN the AI API response cannot be parsed into the expected Advisor_Response structure, THE Advisor_Service SHALL return an error indicating the response format was invalid and SHALL discard the entire response.
6. IF the AI API returns a valid response containing zero Suggestions for a requested Pillar, THEN THE Advisor_Service SHALL return an empty list for that Pillar in the Advisor_Response.
7. IF a parsed Suggestion has a title, description, or remediation field exceeding its maximum character limit, THEN THE Advisor_Service SHALL truncate the field at the maximum length.

### Requirement 5: Security Pillar Analysis

**User Story:** As a cloud architect, I want the AI to identify security vulnerabilities in my infrastructure, so that I can remediate risks before they are exploited.

#### Acceptance Criteria

1. WHEN analyzing the Security pillar, THE Advisor_Service SHALL instruct the AI to evaluate: IAM policies with wildcard actions or wildcard resources, security groups with ingress rules allowing 0.0.0.0/0 or ::/0, missing encryption at rest, missing encryption in transit, resources with public accessibility enabled, and resources without access logging configured.
2. WHEN a Security suggestion references specific resources, THE Advisor_Service SHALL include the ARNs of those resources in the affected_resources field, with a maximum of 50 ARNs per Suggestion.
3. WHEN a Security suggestion has Severity critical, THE Advisor_Service SHALL include a remediation field containing at least 1 and at most 10 actionable steps describing how to resolve the vulnerability.
4. WHEN a Security suggestion has Severity high, medium, or low, THE Advisor_Service SHALL include a remediation field containing at least 1 actionable step describing how to resolve the vulnerability.

### Requirement 6: Cost Optimization Pillar Analysis

**User Story:** As a cloud architect, I want the AI to identify cost optimization opportunities, so that I can reduce unnecessary AWS spending.

#### Acceptance Criteria

1. WHEN analyzing the Cost_Optimization pillar, THE Advisor_Service SHALL instruct the AI to evaluate: idle or underutilized resources, oversized instance types, missing S3 lifecycle policies, unattached EBS volumes, unused Elastic IPs, and missing reserved instance or savings plan opportunities.
2. WHEN a Cost_Optimization suggestion references specific resources, THE Advisor_Service SHALL include the ARNs of those resources in the affected_resources field.
3. WHEN a Cost_Optimization suggestion identifies a potential savings, THE Advisor_Service SHALL include an estimated_impact field containing a human-readable text description of the potential cost reduction (e.g., estimated percentage savings or monthly dollar range) so that the cloud architect can prioritize actions.
4. WHEN a Cost_Optimization suggestion identifies a resource incurring cost with zero utilization (e.g., unattached EBS volumes, unused Elastic IPs), THE Advisor_Service SHALL assign Severity of high or critical.

### Requirement 7: Performance Pillar Analysis

**User Story:** As a cloud architect, I want the AI to identify performance bottlenecks and improvements, so that I can optimize my infrastructure for better reliability and speed.

#### Acceptance Criteria

1. WHEN analyzing the Performance pillar, THE Advisor_Service SHALL instruct the AI to evaluate: single-AZ deployments lacking redundancy, missing caching layers (ElastiCache, CloudFront), suboptimal instance types for workload patterns, missing auto-scaling configurations, and database read replica opportunities.
2. WHEN a Performance suggestion references specific resources, THE Advisor_Service SHALL include the ARNs of those resources in the affected_resources field.
3. WHEN a Performance suggestion addresses single-AZ deployments lacking redundancy or missing auto-scaling configurations, THE Advisor_Service SHALL assign Severity of high or critical, as these represent reliability risks that can cause service outages.
4. WHEN a Performance suggestion addresses missing caching layers, suboptimal instance types, or database read replica opportunities, THE Advisor_Service SHALL assign Severity of medium or low, as these represent optimization opportunities rather than outage risks.
5. WHEN a Performance suggestion has Severity of high or critical, THE Advisor_Service SHALL include a remediation field describing specific steps to resolve the identified reliability risk.

### Requirement 8: API Endpoint for Architecture Advice

**User Story:** As a frontend developer, I want a REST API endpoint to request and retrieve architecture suggestions, so that the UI can display them to users.

#### Acceptance Criteria

1. THE Advisor_Service SHALL expose a POST endpoint at /api/advisor/analyze that accepts a JSON request body containing an optional list of Pillars (Security, Cost_Optimization, Performance) with a maximum of 3 items.
2. WHEN the POST /api/advisor/analyze endpoint receives a valid request, THE Advisor_Service SHALL return HTTP 202 (Accepted) with a response body containing a task identifier for the initiated analysis.
3. IF the POST /api/advisor/analyze request contains an unrecognized Pillar value, THEN THE Advisor_Service SHALL return HTTP 422 with an error message indicating which Pillar values are invalid.
4. THE Advisor_Service SHALL expose a GET endpoint at /api/advisor/status that returns the current analysis status (idle, in_progress, completed, failed) and the task identifier of the current or most recent analysis.
5. THE Advisor_Service SHALL expose a GET endpoint at /api/advisor/results that returns the most recent Advisor_Response.
6. IF the GET /api/advisor/results endpoint is called and no completed analysis exists, THEN THE Advisor_Service SHALL return HTTP 404 with an error message indicating no analysis results are available.
7. IF an analysis is already in progress, THEN THE Advisor_Service SHALL reject new POST /api/advisor/analyze requests with HTTP 409 (Conflict) and an error message indicating an analysis is already running.

### Requirement 9: Configuration Management

**User Story:** As a system administrator, I want to configure the AI API connection parameters, so that the feature can work with different AI providers or models.

#### Acceptance Criteria

1. THE Advisor_Service SHALL read the AI API base URL from an environment variable named AI_API_BASE_URL.
2. THE Advisor_Service SHALL read the AI API key from an environment variable named AI_API_KEY.
3. THE Advisor_Service SHALL read the AI model identifier from an environment variable named AI_API_MODEL.
4. IF any required configuration variable (AI_API_BASE_URL, AI_API_KEY, AI_API_MODEL) is missing or contains only whitespace when an analysis is requested, THEN THE Advisor_Service SHALL reject the request with an error indicating which specific variable is missing or empty.
5. IF AI_API_BASE_URL does not conform to a valid URL with the HTTPS scheme (scheme + host at minimum), THEN THE Advisor_Service SHALL reject the analysis request with an error indicating the URL is invalid.
6. THE Advisor_Service SHALL not log or expose the value of AI_API_KEY in error messages or responses.

### Requirement 10: Response Parsing and Validation

**User Story:** As a system component, I want to parse and validate the AI API response into structured suggestions, so that the frontend receives consistent data regardless of AI output variations.

#### Acceptance Criteria

1. WHEN the AI API returns a valid response, THE Advisor_Service SHALL parse the response body and extract individual Suggestions up to a maximum of 50 Suggestions per response, discarding any beyond that limit.
2. THE Advisor_Service SHALL validate that each parsed Suggestion contains all required fields (pillar, title, description, severity, affected_resources, remediation) and that the title does not exceed 200 characters, the description does not exceed 2000 characters, and the remediation does not exceed 2000 characters.
3. IF a parsed Suggestion contains an ARN not present in the original ScanResult, THEN THE Advisor_Service SHALL remove that ARN from the affected_resources list; IF all ARNs are removed, THE Advisor_Service SHALL retain the Suggestion with an empty affected_resources list.
4. IF the AI API response contains suggestions with an unrecognized Pillar value, THEN THE Advisor_Service SHALL discard those suggestions and log a warning.
5. IF a parsed Suggestion contains a Severity value other than critical, high, medium, or low, THEN THE Advisor_Service SHALL discard that Suggestion and log a warning.
6. THE Advisor_Service SHALL ensure that serializing and then deserializing any valid Advisor_Response produces a field-by-field equivalent object (round-trip property).
