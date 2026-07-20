# Requirements Document

## Introduction

CloudSpyglass is a single-container web application (React frontend + FastAPI backend) that provides individual developers and small teams with a quick visual overview of their AWS infrastructure. It renders an interactive node-graph diagram of scanned AWS resources and their relationships, without requiring a full observability platform setup.

## Glossary

- **CloudSpyglass**: The overall web application system comprising a React frontend and FastAPI backend
- **Scanner**: The backend service responsible for discovering AWS resources via boto3 API calls
- **Relationship_Resolver**: The backend service that analyzes scanned resources and identifies connections between them
- **Credential_Manager**: The backend service that stores and manages AWS credentials in-memory
- **Diagram_Renderer**: The frontend component that renders the interactive node-graph using React Flow
- **Detail_Panel**: The frontend slide-in panel displaying full resource metadata
- **Filter_Engine**: The frontend/backend component that applies tag and resource-type filters to diagram data
- **Export_Service**: The backend service that generates PDF, PNG, or SVG exports of the diagram
- **Scan_Result**: A JSON object containing all discovered resources, their metadata, and resolved relationships
- **Resource_Node**: A visual element in the diagram representing a single AWS resource
- **Relationship_Edge**: A visual connection between two Resource_Nodes representing a detected relationship
- **Account_ID**: The 12-digit AWS account identifier associated with scanned credentials
- **Icon_Server**: The backend endpoint that serves official AWS service SVG icons and the application logo from the assets/ directory

## Requirements

### Requirement 1: AWS Credential Submission

**User Story:** As a developer, I want to configure my AWS credentials directly from the web UI, so that I can start scanning infrastructure without terminal or environment variable configuration.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL provide a Settings page with input fields for Access Key ID (text input, maximum 128 characters), Secret Access Key (masked input, maximum 128 characters), Session Token (optional, masked input, maximum 1024 characters), and default AWS region (selectable from the list of valid AWS region codes)
2. WHEN the user submits credentials, THE Credential_Manager SHALL receive them via a POST /api/credentials endpoint over HTTPS
3. WHEN credentials are received, THE Credential_Manager SHALL store them in-memory only and SHALL NOT persist them to disk
4. WHEN credentials are stored, THE Credential_Manager SHALL use them for all subsequent boto3 sessions, replacing any previously stored credentials
5. IF no credentials are explicitly provided via the UI, THEN THE Credential_Manager SHALL fall back to the standard boto3 credential chain (environment variables, shared config, instance profile)
6. IF the user submits credentials with Access Key ID or Secret Access Key empty, THEN THE Credential_Manager SHALL reject the submission and THE CloudSpyglass SHALL display an error message indicating which required fields are missing

### Requirement 2: Credential Validation and Status Display

**User Story:** As a developer, I want to see whether my credentials are valid and which account they belong to, so that I can confirm I'm scanning the correct infrastructure.

#### Acceptance Criteria

1. WHEN credentials are submitted, THE Credential_Manager SHALL validate them by calling AWS STS GetCallerIdentity and SHALL complete the validation within 10 seconds
2. WHEN validation succeeds, THE CloudSpyglass SHALL display the connected Account_ID, credential source (UI-provided or boto3 chain), and session expiry time on the Settings page; IF the credentials are long-term IAM user keys with no expiry, THEN THE CloudSpyglass SHALL display the expiry field as "No expiration"
3. IF credentials are invalid, expired, or the STS call fails due to a network error, THEN THE CloudSpyglass SHALL display an error message indicating the failure reason (e.g., invalid credentials, expired session, or unreachable endpoint)
4. WHEN the user clicks the disconnect button, THE Credential_Manager SHALL clear all stored credentials from memory
5. WHEN credentials are cleared, THE CloudSpyglass SHALL remove the Account_ID, credential source, and expiry information from the Settings page and SHALL disable the disconnect button
6. WHILE credential validation is in progress, THE CloudSpyglass SHALL display a loading indicator on the Settings page and SHALL disable the submit button

### Requirement 3: Multi-Region Resource Scanning

**User Story:** As a developer, I want to scan my AWS resources across multiple regions, so that I get a complete picture of my infrastructure regardless of where resources are deployed.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL provide an optional region selection list on the Settings page where the user can select one or more AWS regions to scan; IF no regions are selected, THEN THE Scanner SHALL discover all enabled regions via the EC2 DescribeRegions API and scan all of them
2. WHEN a scan is initiated, THE Scanner SHALL query AWS APIs across each selected region (or all enabled regions if none are selected) using read-only boto3 calls, with a per-region timeout of 60 seconds and a total scan timeout of 10 minutes
3. THE Scanner SHALL support scanning these resource types: EC2 instances, Security Groups, VPCs, Subnets, S3 buckets, Lambda functions, RDS instances and clusters, IAM roles, ALB and NLB, ECS clusters and services, SNS topics, SQS queues, DynamoDB tables, CloudFront distributions, Route53 hosted zones, and API Gateway REST APIs
4. WHEN an API call is throttled, THE Scanner SHALL retry with exponential backoff starting at 1 second, doubling each attempt, up to a maximum of 5 retry attempts and a maximum delay of 30 seconds per retry
5. IF scanning fails for one or more regions, THEN THE Scanner SHALL return successful results from other regions along with a failures list where each entry includes the region name, the resource type that failed, the error message, and a timestamp
6. THE Scanner SHALL enrich each resource with metadata including tags, creation date (where available from the AWS API), IAM role associations, and service-specific attributes (instance type, runtime, engine version, storage class)
7. IF the total scan timeout of 10 minutes is reached before all regions complete, THEN THE Scanner SHALL cancel remaining in-progress region scans and return results collected up to that point along with a failures entry for each timed-out region

### Requirement 4: Resource Relationship Resolution

**User Story:** As a developer, I want to see how my AWS resources are connected to each other, so that I can understand dependencies and data flows across my infrastructure.

#### Acceptance Criteria

1. WHEN a scan completes, THE Relationship_Resolver SHALL analyze resource configurations to detect network relationships: Security Group attachments (EC2 to SG), VPC memberships (EC2, RDS, Lambda to VPC and Subnet), and load balancer targets (ALB and NLB to EC2 and ECS)
2. WHEN a scan completes, THE Relationship_Resolver SHALL detect IAM relationships: role associations between Lambda, EC2, ECS and their assigned IAM Roles
3. WHEN a scan completes, THE Relationship_Resolver SHALL detect event relationships: event source mappings (SQS and SNS to Lambda) and S3 event notifications (S3 to Lambda, SQS, and SNS)
4. WHEN a scan completes, THE Relationship_Resolver SHALL detect data relationships: RDS subnet group memberships (RDS to Subnets)
5. WHEN a resource configuration contains an ARN with an Account_ID different from the scanned account or references a hostname outside AWS service domains (not matching *.amazonaws.com), THE Relationship_Resolver SHALL mark the target as an external component
6. THE Relationship_Resolver SHALL persist each detected relationship as a record containing: source resource ARN, target resource ARN, relationship category (network, IAM, event, or data), and the configuration property from which the relationship was derived
7. IF a relationship references a resource ARN that was not found in the current scan results, THEN THE Relationship_Resolver SHALL still record the relationship and mark the missing target resource as unresolved

### Requirement 5: Interactive Diagram Rendering

**User Story:** As a developer, I want to see my infrastructure as an interactive node-graph diagram, so that I can visually understand the topology and relationships between resources.

#### Acceptance Criteria

1. THE Diagram_Renderer SHALL render each AWS resource as a Resource_Node displaying its name, resource type, and the official AWS service SVG icon
2. THE Icon_Server SHALL serve SVG icons from the icons/ directory via GET /api/icons/{service_type} and the Diagram_Renderer SHALL load icons from this endpoint
3. THE Diagram_Renderer SHALL render Relationship_Edges between connected Resource_Nodes, color-coded by category: solid blue for network, dashed green for IAM, dotted orange with animation for event relationships, and solid gray for data relationships
4. THE Diagram_Renderer SHALL apply automatic layout using the Dagre algorithm with top-to-bottom rank direction for node positioning
5. THE Diagram_Renderer SHALL support pan and zoom within the range of 0.25x to 4.0x magnification, with an initial zoom level that fits all nodes within the visible viewport
6. WHEN a resource is identified as an external component, THE Diagram_Renderer SHALL render its Resource_Node with a dashed border style
7. WHEN no scan data exists, THE Diagram_Renderer SHALL display an empty state with a call-to-action prompting the user to configure credentials and run a scan
8. WHEN the user hovers over a Relationship_Edge, THE Diagram_Renderer SHALL display a tooltip within 200 milliseconds showing the interaction type, source resource, target resource, and configuration property
9. IF an icon fails to load from the Icon_Server, THEN THE Diagram_Renderer SHALL display a generic placeholder icon within the Resource_Node
10. THE Diagram_Renderer SHALL complete initial rendering of a Scan_Result containing up to 500 Resource_Nodes within 5 seconds

### Requirement 6: Resource Detail Panel

**User Story:** As a developer, I want to click on any resource in the diagram and see its full metadata, so that I can inspect configuration details without leaving the visualization.

#### Acceptance Criteria

1. WHEN the user clicks a Resource_Node, THE Detail_Panel SHALL slide in from the right as an overlay displaying the resource type, ARN, region, all tags (up to 50), creation date, IAM role, and service-specific attributes, and SHALL omit sections for metadata fields that are not applicable to the selected resource type
2. WHILE the Detail_Panel is loading metadata, THE Detail_Panel SHALL display a loading indicator, and IF loading does not complete within 10 seconds, THEN THE Detail_Panel SHALL treat the request as failed
3. IF metadata retrieval fails, THEN THE Detail_Panel SHALL display an error message indicating the failure reason, consistent with the CloudSpyglass error response structure
4. WHEN the user presses the Escape key or clicks the close button, THE Detail_Panel SHALL close and return focus to the Diagram_Renderer
5. WHEN the user clicks a different Resource_Node while the Detail_Panel is already open, THE Detail_Panel SHALL replace its content with the metadata of the newly selected resource

### Requirement 7: Tag-Based Filtering

**User Story:** As a developer, I want to filter the diagram by resource tags, so that I can focus on specific groups of resources relevant to my current task.

#### Acceptance Criteria

1. THE Filter_Engine SHALL accept up to 10 tag key-value pairs (key max 128 characters, value max 256 characters) and apply AND logic to filter resources
2. THE Filter_Engine SHALL provide autocomplete suggestions showing the 20 most frequently occurring tag keys and values found in the current scan data, ordered by descending frequency
3. WHEN tag filters are applied, THE Diagram_Renderer SHALL display only resources matching all specified tag criteria and the Relationship_Edges that connect two matching resources
4. WHEN filters are active, THE CloudSpyglass SHALL display the filtered resource count alongside the total resource count
5. IF no resources match the applied tag filters, THEN THE Diagram_Renderer SHALL display an empty state message indicating that no resources match the current filter criteria
6. WHEN all tag filters are removed, THE Diagram_Renderer SHALL restore the full unfiltered diagram view within 3 seconds

### Requirement 8: Resource Type Filtering

**User Story:** As a developer, I want to filter the diagram by resource type, so that I can isolate specific service categories in the visualization.

#### Acceptance Criteria

1. THE Filter_Engine SHALL present all resource types found in the current Scan_Result as selectable options and SHALL accept one or more selections, applying OR logic across selected types
2. WHEN resource type filters are applied, THE Diagram_Renderer SHALL display only resources matching any of the selected types and any Relationship_Edge where at least one endpoint is a visible resource of a selected type
3. WHEN filters change, THE Diagram_Renderer SHALL re-render the diagram within 3 seconds for scan results containing up to 500 resources
4. WHEN no resource type filters are selected, THE Diagram_Renderer SHALL display all resources from the current Scan_Result
5. WHEN both resource type filters and tag filters are active simultaneously, THE Filter_Engine SHALL apply AND logic between the two filter categories, displaying only resources that match at least one selected resource type AND satisfy all active tag criteria

### Requirement 9: Auto-Refresh Scanning

**User Story:** As a developer, I want my infrastructure diagram to refresh automatically on a schedule, so that I see near-current state without manual intervention.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL support configurable auto-refresh intervals: 1 minute, 5 minutes, 15 minutes, 30 minutes, 60 minutes, or manual-only, with manual-only as the default until the user selects an interval
2. WHEN the auto-refresh interval elapses, THE CloudSpyglass SHALL trigger a new scan (POST /api/scan), retrieve the latest diagram data (GET /api/diagrams/latest), and update the Diagram_Renderer
3. IF the auto-refresh interval elapses while a scan is already in progress, THEN THE CloudSpyglass SHALL skip the scheduled scan and wait for the next interval
4. IF an auto-refresh scan fails, THEN THE CloudSpyglass SHALL retain the current diagram data, display an error message indicating the failure reason, and continue the auto-refresh timer for the next scheduled interval
5. WHILE a refresh is in progress, THE CloudSpyglass SHALL display a non-blocking visual indicator distinguishable from the idle state
6. THE CloudSpyglass SHALL provide a manual refresh button that is always available regardless of auto-refresh configuration
7. WHEN the user triggers a manual refresh, THE CloudSpyglass SHALL reset the auto-refresh timer to begin counting from zero

### Requirement 10: Scan Result Storage

**User Story:** As a developer, I want my latest scan results persisted to disk, so that the diagram is available immediately when I reopen the application.

#### Acceptance Criteria

1. WHEN a scan completes, THE CloudSpyglass SHALL store the Scan_Result as a UTF-8 encoded JSON file at the path data/{Account_ID}.json, creating the data/ directory if it does not exist
2. WHEN a new scan completes for the same account, THE CloudSpyglass SHALL write the Scan_Result to a temporary file in the data/ directory and then atomically replace the previous data/{Account_ID}.json file to prevent partial writes
3. THE CloudSpyglass SHALL maintain exactly one Scan_Result file per Account_ID
4. WHEN the application starts and a data/{Account_ID}.json file exists, THE CloudSpyglass SHALL load the persisted Scan_Result and render the diagram without requiring a new scan
5. IF writing the Scan_Result file fails, THEN THE CloudSpyglass SHALL retain the previous file unchanged and display an error message indicating the storage failure reason
6. IF loading a persisted Scan_Result file fails due to missing or unparseable content, THEN THE CloudSpyglass SHALL discard the corrupt file and display the empty state prompting the user to run a new scan

### Requirement 11: Diagram Export

**User Story:** As a developer, I want to export the current diagram view, so that I can share infrastructure visualizations in documentation or presentations.

#### Acceptance Criteria

1. THE Export_Service SHALL support exporting the current diagram view in PDF, PNG (at 300 DPI), and SVG formats
2. WHEN filters are active during export, THE Export_Service SHALL export only the filtered view and include the active filter criteria as a text annotation in the header or footer area of the exported document
3. THE Export_Service SHALL name exported files using the format {Account_ID}_{timestamp}.{format}, where timestamp follows the pattern YYYYMMDD_HHmmss in UTC
4. THE Export_Service SHALL save exported files to a server-side mounted volume via an API endpoint and complete the export operation within 30 seconds
5. IF the export operation fails due to rendering error, insufficient disk space, or timeout, THEN THE Export_Service SHALL return an error response indicating the failure reason without producing a partial or corrupted file
6. THE Export_Service SHALL reject export requests that would produce an output file exceeding 50 MB and return an error response indicating the size limit

### Requirement 12: Settings Configuration

**User Story:** As a developer, I want a centralized settings page, so that I can manage credentials and application preferences in one place.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL provide a Settings page with a selection control for configuring the auto-refresh interval, offering the options: 1 minute, 5 minutes, 15 minutes, 30 minutes, 60 minutes, or manual-only
2. WHEN the user changes the auto-refresh interval, THE CloudSpyglass SHALL apply the new interval immediately to the next refresh cycle and display a confirmation indicating the setting was saved
3. THE CloudSpyglass SHALL display the current Account_ID (12-digit identifier) and credential status on the Settings page, where status is one of: "Connected", "Disconnected", or "Expired"
4. THE CloudSpyglass SHALL provide a connect action that navigates the user to the credential submission form, and a disconnect action that triggers credential clearing via the Credential_Manager
5. IF the user triggers the disconnect action, THEN THE CloudSpyglass SHALL update the credential status to "Disconnected" and clear the displayed Account_ID within 2 seconds

### Requirement 13: Image and Icon Serving

**User Story:** As a developer, I want the diagram to display official AWS service icons and the application to show its logo, so that I can quickly identify resource types visually and the application has consistent branding.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL organize all static images under a centralized assets/ directory at the project root with subdirectories: assets/icons/ for AWS service SVG icons and assets/logo/ for the application logo file(s)
2. THE Icon_Server SHALL serve SVG icon files from assets/icons/ via GET /api/images/icons/{service_type}, where {service_type} corresponds to one of the resource types supported by the Scanner (e.g., ec2, lambda, s3, rds, vpc, subnet, security_group, alb, nlb, ecs, sns, sqs, dynamodb, cloudfront, route53, apigateway, iam_role), and SHALL return the response with Content-Type image/svg+xml
3. THE Icon_Server SHALL serve the application logo from assets/logo/ via GET /api/images/logo and SHALL return the response with the appropriate Content-Type based on the file format (e.g., image/svg+xml, image/png)
4. THE Diagram_Renderer SHALL NOT bundle icons or logo into the frontend build and SHALL load all images from the Icon_Server endpoints
5. THE CloudSpyglass frontend SHALL display the application logo in the navigation header, loaded from the GET /api/images/logo endpoint
6. IF a requested icon is not found in the assets/icons/ directory, THEN THE Icon_Server SHALL return a 404 response conforming to the standard error response structure defined in Requirement 14
7. IF the {service_type} parameter does not match any known resource type, THEN THE Icon_Server SHALL return a 400 response indicating the requested service type is not recognized

### Requirement 14: Consistent Error Responses

**User Story:** As a developer, I want all API errors to follow a consistent structure, so that the frontend can reliably parse and display error information.

#### Acceptance Criteria

1. THE CloudSpyglass SHALL return all API error responses as a JSON object with the fields: error_code (a string in UPPER_SNAKE_CASE format identifying the error category), message (a human-readable string of at most 500 characters describing the error), details (a nullable string providing additional context), timestamp (a string in ISO 8601 UTC format), and recoverable (a boolean)
2. IF an error is caused by a transient condition such as a network timeout, AWS API throttling, or temporary service unavailability, THEN THE CloudSpyglass SHALL set the recoverable field to true
3. IF an error is caused by a permanent condition such as invalid input, missing required fields, or authentication failure, THEN THE CloudSpyglass SHALL set the recoverable field to false
