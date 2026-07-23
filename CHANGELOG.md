# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.0.0] - 2026-07-23

Transforms CloudSpyglass from a flat flow-chart diagram tool into a hierarchical architecture diagram visualizer. Introduces nested containers (Cloud → Account → Region → VPC → Subnet), boundary service placement, viewport culling for performance, and expanded resource scanning.

### Added

#### Backend — Hierarchy Builder Service

- New `HierarchyBuilder` service that constructs a nested container tree (Cloud → Account → Region → VPC → AZ → Subnet) from scanned resources ([`0f5c36a`](../../commit/0f5c36a))
- Hierarchy Pydantic models (`HierarchyTree`, `ContainerMetadata`, `BoundaryServicePlacement`) for API responses ([`f3febf3`](../../commit/f3febf3))
- `ArchitectureIconResolver` service mapping resource types to AWS architecture icon keys ([`bfcf2c3`](../../commit/bfcf2c3))
- Diagrams endpoint now returns full hierarchy tree for unfiltered views and pruned hierarchy for filtered views ([`8c829aa`](../../commit/8c829aa))
- Integration tests for the diagrams endpoint covering hierarchy data ([`4ed70ea`](../../commit/4ed70ea))
- Unit and property-based tests for `HierarchyBuilder`: nesting order, subnet classification, resource placement priority, container metadata completeness, and external resource sub-grouping ([`410cddc`](../../commit/410cddc))

#### Backend — New Resource Type Scanners

- Auto Scaling Groups (`asg`) scanner with launch config, desired/min/max capacity, and instance health ([`1d11abb`](../../commit/1d11abb))
- Target Groups (`target_group`) scanner with target type, health checks, and registered targets ([`1d11abb`](../../commit/1d11abb))

#### Backend — Enhanced Relationship Detection

- ALB/NLB → Target EC2 instances and Lambda functions via Target Group health descriptions ([`45c2207`](../../commit/45c2207))
- ALB/NLB → S3 access logs bucket relationship when access logging is enabled ([`45c2207`](../../commit/45c2207))
- NAT Gateway → Elastic IP allocation relationships ([`45c2207`](../../commit/45c2207))
- ECS → ALB/NLB relationships via service load balancer configuration ([`45c2207`](../../commit/45c2207))
- Target Group → EC2/Lambda target and VPC relationships ([`45c2207`](../../commit/45c2207))
- CloudFront → ALB/NLB origins resolved by DNS name matching instead of hardcoded ARNs ([`45c2207`](../../commit/45c2207))
- DNS-based resolution utility for matching CloudFront origins, S3 website endpoints, and load balancer DNS names to scanned resources ([`45c2207`](../../commit/45c2207))

#### Frontend — Hierarchical Layout Engine

- New `HierarchyLayoutEngine` computing nested container positions with configurable padding, resource grid spacing, and minimum dimensions ([`2a101ad`](../../commit/2a101ad))
- TypeScript hierarchy types (`ContainerMetadata`, `BoundaryServicePlacement`, `HierarchyTree`) ([`b05a450`](../../commit/b05a450))
- Property-based tests: no sibling overlap, minimum parent padding, minimum container dimensions, boundary service positioning, and boundary service spacing ([`750de5f`](../../commit/750de5f))

#### Frontend — Container & Boundary Components

- `ContainerNode` component rendering nested VPC/Region/Subnet containers with collapse/expand behavior and resource badge counts ([`214ca34`](../../commit/214ca34))
- `BoundaryServiceNode` component for IGW, NAT Gateway, WAF, and VPN placement at container edges ([`7b9e658`](../../commit/7b9e658))
- `ExternalResourcesContainer` component grouping resources outside VPC boundaries ([`22ad3f7`](../../commit/22ad3f7))
- Unit and property-based tests for all container components ([`0fe18f6`](../../commit/0fe18f6))

#### Frontend — Performance Optimizations

- Viewport culling: nodes outside the visible viewport are not rendered to DOM, improving performance on large diagrams (200+ nodes) ([`7549f6d`](../../commit/7549f6d))
- Layout timeout with progress indicator preventing UI freeze on complex hierarchy calculations ([`53fa5cf`](../../commit/53fa5cf))
- Property-based test verifying viewport culling node bounds are respected ([`6d34888`](../../commit/6d34888))

### Changed

- `DiagramData` API response now includes a `hierarchy` field (`HierarchyTree | null`) enabling hierarchical diagram rendering ([`6dc5fd6`](../../commit/6dc5fd6))
- `FilterCriteria` model extended with `tag_filter_operator` field supporting AND/OR logic for tag filters ([`ce93e8b`](../../commit/ce93e8b))
- `FilterEngine.apply_filters()` accepts a new `tag_filter_operator` parameter controlling whether tag filters use AND (match all) or OR (match any) logic ([`ce93e8b`](../../commit/ce93e8b))
- `FilterBar` component now shows an AND/OR operator toggle when multiple tag filters are active ([`ce93e8b`](../../commit/ce93e8b))
- `DiagramCanvas` updated to use hierarchical layout when hierarchy data is present, falling back to flat dagre layout otherwise ([`9795699`](../../commit/9795699))
- `ResourceNode` rendering updated with architecture icon integration and improved visual styling ([`930e2f3`](../../commit/930e2f3))
- Edge rendering enhanced with category-based styling (network, IAM, event, data) using distinct colors and dash patterns ([`36a4a26`](../../commit/36a4a26))
- `NODE_HEIGHT` increased from 60 to 120 in `HierarchyLayoutEngine` to prevent resource overlap inside containers ([`40d9c8e`](../../commit/40d9c8e))
- Export route now passes `tag_filter_operator` to the filter engine for consistent behavior between diagram view and exported files ([`backend/routes/export.py`](../../commit/45c2207))

### Fixed

- Filter hierarchy pruning now recursively visits all children before deciding container visibility, fixing cases where deeply nested containers with matching resources were incorrectly removed ([`3659bf8`](../../commit/3659bf8))
- Hierarchical layout preserves nested container structure (Cloud → Account → Region → VPC → Subnet) when filters are active, instead of flattening to a disconnected node list ([`4d6c982`](../../commit/4d6c982))
- Container `cursorY` positioning now uses the exact grid calculation from `getGridPositions`, fixing overlap between sibling containers when resource grids have varying heights ([`14fe462`](../../commit/14fe462))
- Scan process now correctly discovers relationships for ElastiCache, Target Groups, and Auto Scaling Groups that were previously missing from diagrams ([`45c2207`](../../commit/45c2207))
- Tag filter AND/OR selector properly wired to backend API ([#12](../../pull/12)) ([`ce93e8b`](../../commit/ce93e8b))

## [v1.0.0] - 2026-07-22

Initial release of CloudSpyglass — an AWS infrastructure visualization tool that scans AWS accounts across multiple regions, discovers resources and their relationships, and renders interactive architecture diagrams.

### Added

#### Backend — Core Services

- Credential management service with AWS credential validation, replacement, and error categorization ([`daedd7a`](../../commit/daedd7ab26a0c0acb8f9d0cc49415ae3fbb5674c))
- Multi-region scanning service with exponential backoff and partial failure handling ([`fb0e775`](../../commit/fb0e7757e0b339e1345c35305ee2367dcf7b4783))
- Relationship resolution engine detecting network, IAM, event-driven, and data relationships between resources ([`496e371`](../../commit/496e371))
- Filter engine with tag-based AND logic, resource type OR logic, and autocomplete suggestions ([`acd9ec2`](../../commit/acd9ec2))
- Scan storage service with JSON file persistence, one file per account, and corrupt file handling ([`70345bc`](../../commit/70345bc))
- Export service supporting PDF, PNG, and SVG diagram export with size limits and filename formatting ([`56ebfb7`](../../commit/56ebfb7))
- Icon and image serving routes for AWS architecture icons ([`7c12909`](../../commit/7c12909))
- Settings API routes and structured error handling with recoverability classification ([`ea3f1e2`](../../commit/ea3f1e2))

#### Backend — API Routes

- Credential API routes for authentication management ([`e4482ad`](../../commit/e4482ad433586e50dd9d39b05852c7176c566f8f))
- Scan API routes to trigger and manage infrastructure scans ([`1f95382`](../../commit/1f95382))
- Filter API routes for querying and applying filters ([`4f61eaa`](../../commit/4f61eaa))
- Export API route for diagram download ([`c6e9a8a`](../../commit/c6e9a8a))
- FastAPI application wiring with all router registrations ([`e31d458`](../../commit/e31d458d1e9f08241e28f8648da4b9855dc8b743))

#### Frontend — Diagram & Visualization

- Interactive diagram canvas with dagre auto-layout engine ([`dedc5e1`](../../commit/dedc5e1))
- Custom `ResourceNode` component for AWS resource visualization ([`26f5d62`](../../commit/26f5d62))
- Custom `RelationshipEdge` component with styled relationship lines ([`d190b42`](../../commit/d190b42))
- Detail panel displaying resource metadata on node selection ([`b4efc56`](../../commit/b4efc56))

#### Frontend — User Interface

- Filter bar with `TagFilterInput` and `TypeFilterSelect` components ([`8113222`](../../commit/81132224a8777200fd97bfe6624c58f68ce0fb80))
- Diagram page as main application view ([`691f2d4`](../../commit/691f2d44c56d2bc8289595407a590fb63b06e818))
- Settings page for application configuration ([`00e95d0`](../../commit/00e95d0dcc50bb162715ea74e932f243c3c1f75f))
- Navigation header, application logo, and routing setup ([`dbf12fe`](../../commit/dbf12fe023f27dfae9c2b285ebca622275bb18c7))
- Scan controls with start/stop buttons and configurable auto-refresh logic ([`4fae469`](../../commit/4fae46907a49d3c9f1d2661e3ca056ac42184dff))
- Export menu component for PDF/PNG/SVG download ([`4d3b839`](../../commit/4d3b83925256c0d92cd5459057d185e87785440b))
- Region selector for multi-region scan configuration ([`eef2b37`](../../commit/eef2b37505322e9346515351de44fbddcb8fec10))
- Stop button to cancel in-progress scans ([`be7f5bf`](../../commit/be7f5bf370d704cc48e80e47db8eb9880ea8edf9))

#### Infrastructure & DevOps

- Docker Compose development environment with hot-reload volumes ([`69ce1a2`](../../commit/69ce1a26e9ac204f2ee2e575b8ceb3a8f7982078))
- Multi-stage production Dockerfile with Nginx reverse proxy and supervisord ([`131bd79`](../../commit/131bd796856c45bf57d47f0ad156138b97de1f48))
- GitHub Actions CI/CD pipelines for backend, frontend, and infrastructure ([`2fcfd8f`](../../commit/2fcfd8f41961ae021677765c1b78ec32b8cc2d6b))
- Terraform infrastructure-as-code for ECS Fargate deployment behind ALB ([`0072e21`](../../commit/0072e21f2566b7a80c93f7be5ccf62e0013f2ec2))
- AWS architecture icons and application logo assets ([`54bcf77`](../../commit/54bcf77bc95197a845a642462e0617df6c5c35c0))

#### Testing

- Property-based tests (Hypothesis) for credential validation, replacement, and error categorization ([`7585dda`](../../commit/7585dda0bc5e4315c03567f44b8575956908ecfb))
- Property-based tests for region selection and exponential backoff ([`03ace55`](../../commit/03ace55225ee9ee3b3f2e423d3ec8bb3bc94c1ad))
- Property-based tests for network, IAM, event-driven relationship detection and external classification ([`2fadfa2`](../../commit/2fadfa2))
- Property-based tests for filter logic: tag AND, type OR, autocomplete ordering, and combined intersection ([`82f35a4`](../../commit/82f35a4))
- Property-based tests for scan storage persistence round-trip and corrupt file handling ([`81ec351`](../../commit/81ec351))
- Property-based tests for export filename format, size limits, and filtered annotations ([`1f6afb8`](../../commit/1f6afb8))
- Property-based tests for icon endpoint correctness and error handling ([`8191a69`](../../commit/8191a69))
- Property-based tests for error response structure and recoverability classification ([`9638108`](../../commit/9638108))
- Frontend property-based tests (fast-check) for filter logic, tag suggestions, edge styling, detail panel, and diagram state preservation ([`b90cf62`](../../commit/b90cf6278059f8de8a90abd0464c070297666e3c))
- Frontend and backend integration tests ([`c6126bc`](../../commit/c6126bc3fa266095cbe7548385042a3097e60ead))

### Fixed

- Export service download and formatted visualization not working correctly ([#8](../../pull/8)) ([`c7fac3f`](../../commit/c7fac3f48dada040a32092f5ce3a9643eee9fbc5))
- Diagram flow rendering for dependent services not connecting properly ([#9](../../pull/9), [#10](../../pull/10)) ([`6ef7def`](../../commit/6ef7defc92093aab7eda689b9cad7952e0a15541))
- `POST /api/scan` returned 422 and frontend didn't wait for scan to complete ([`b75fd66`](../../commit/b75fd6609fb04548fca53ee505d1108b13c45c2c))
- Credential persistence between pages and filter state lost on navigation ([`c17f885`](../../commit/c17f8859693bdd5433a1e5d9da5a0a6389324b24))
- Session token field max length increased from 1024 to 4096 to support actual AWS token sizes ([`4f9a9d9`](../../commit/4f9a9d988beacc7c3ce8941ca274755e7b0e3ab3))
- Scan timeout increased from 60s to 180s per region, then to 360s total, to prevent premature timeouts on large accounts ([`fd842b8`](../../commit/fd842b8791f3bcad751597b8da89a83383e33529))

[v2.0.0]: https://github.com/yarias-tech/hackathon-aws-cloudspyglass/releases/tag/v2.0.0
[v1.0.0]: https://github.com/yarias-tech/hackathon-aws-cloudspyglass/releases/tag/v1.0.0
