# CloudSpyglass — Product Summary

CloudSpyglass is an AWS infrastructure visualization tool. It scans a user's AWS account across multiple regions, discovers resources and their relationships, and renders an interactive architecture diagram in the browser.

## Core Capabilities

- **Credential management**: Users provide AWS credentials (or rely on the default boto3 credential chain) to authenticate against their account.
- **Multi-region scanning**: Discovers EC2, VPC, S3, Lambda, RDS, IAM, ECS, ALB/NLB, SNS, SQS, DynamoDB, CloudFront, Route53, API Gateway, and more.
- **Relationship resolution**: Identifies network, IAM, event-driven, and data relationships between resources. Detects cross-account and external references.
- **Interactive diagram**: Renders a pan-and-zoom flow diagram using React Flow with dagre auto-layout.
- **Filtering**: Tag-based (AND logic) and resource-type (OR logic) filters with autocomplete.
- **Export**: PDF, PNG, and SVG export of diagrams.
- **Persistence**: Scan results are stored locally as JSON files (one per account).
- **Auto-refresh**: Configurable periodic re-scan with non-blocking UI updates.

## Users

Developers, SREs, and cloud architects who need a quick visual understanding of their AWS infrastructure without manually navigating the AWS Console.
