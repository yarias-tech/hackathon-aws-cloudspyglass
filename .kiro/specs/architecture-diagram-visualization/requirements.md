# Requirements Document

## Introduction

Replace CloudSpyglass's current flat flowchart-style diagram with a proper AWS architecture diagram visualization that mirrors the look and feel of official AWS Architecture Diagrams. The new diagram uses nested container groups to represent AWS infrastructure hierarchy (Cloud → Account → Region → VPC → Availability Zones → Subnets), official AWS Architecture Icons for each service, spatial grouping of resources by their network location, and visual connections between related resources. This transforms the tool from a basic node-edge graph into a professional architecture visualization suitable for documentation, audits, and team communication.

## Glossary

- **Diagram_Renderer**: The frontend module responsible for converting backend scan data into a positioned, styled React Flow diagram with nested containers and service icons.
- **Layout_Engine**: The component that computes spatial positions for all containers and resource nodes based on the AWS hierarchy (Cloud → Account → Region → VPC → AZ → Subnet).
- **Container_Node**: A React Flow parent node that visually groups child resources and sub-containers. Rendered as a bordered, labeled rectangle with background color and an icon badge.
- **Resource_Node**: A React Flow node representing a single AWS resource, rendered with the corresponding AWS Architecture Icon and a text label.
- **Hierarchy_Builder**: The backend service that transforms flat resource and relationship data into a nested tree structure representing the AWS infrastructure hierarchy.
- **Architecture_Icon_Resolver**: The module that maps AWS resource types to their official AWS Architecture Icon file paths.
- **Edge_Renderer**: The component responsible for drawing styled connections (arrows) between nodes representing relationships.
- **Boundary_Service**: A resource (Internet Gateway, NAT Gateway, WAF) that sits at the edge between two container layers and is rendered on the boundary line.

## Requirements

### Requirement 1: Nested Container Hierarchy

**User Story:** As a cloud architect, I want to see my AWS resources organized inside nested containers representing the AWS infrastructure hierarchy, so that I can immediately understand the network topology and placement of each resource.

#### Acceptance Criteria

1. THE Diagram_Renderer SHALL render an outermost Container_Node labeled "AWS Cloud" with the AWS Cloud group icon badge.
2. WHEN scan data contains an account ID, THE Diagram_Renderer SHALL render an "AWS Account" Container_Node nested inside the AWS Cloud container, labeled with the account ID.
3. WHEN scan data contains resources in a region, THE Diagram_Renderer SHALL render a "Region" Container_Node nested inside the Account container, labeled with the region name (e.g., "us-east-1") and displaying the Region group icon.
4. WHEN scan data contains VPC resources, THE Diagram_Renderer SHALL render a "VPC" Container_Node nested inside the corresponding Region container, labeled with the VPC Name tag if present or the VPC ID otherwise, and styled with a solid green border and a light green background.
5. WHEN scan data contains subnets within a VPC, THE Diagram_Renderer SHALL render "Availability Zone" Container_Nodes nested inside the VPC container, one per distinct AZ, labeled with the AZ name.
6. WHEN scan data contains subnets, THE Diagram_Renderer SHALL render "Subnet" Container_Nodes nested inside the corresponding AZ container, labeled with the subnet Name tag if present or the subnet ID otherwise.
7. WHEN a subnet has a route table with a route to an Internet Gateway, THE Diagram_Renderer SHALL apply a green background color and the Public Subnet group icon to that Subnet container.
8. IF a subnet does not have a route to an Internet Gateway, THEN THE Diagram_Renderer SHALL apply a blue background color and the Private Subnet group icon to that Subnet container.
9. THE Layout_Engine SHALL position child containers within their parent container without visual overlap.
10. THE Layout_Engine SHALL maintain a minimum padding of 20 pixels between a parent container's border and its children.
11. WHEN a container (VPC, Availability Zone, or Subnet) contains no child resources or sub-containers, THE Diagram_Renderer SHALL still render that container at a minimum size of 100x60 pixels displaying only its label and icon badge.

### Requirement 2: AWS Architecture Icons

**User Story:** As a developer, I want each AWS resource to be displayed with its official AWS Architecture Icon, so that I can identify resource types at a glance without reading labels.

#### Acceptance Criteria

1. THE Architecture_Icon_Resolver SHALL map each supported resource type to an SVG icon file from the 48/ size subdirectory within the corresponding category folder of the Architecture-Service-Icons_07312025 asset directory.
2. THE Resource_Node SHALL render the mapped icon at 48x48 pixels centered above the resource name label.
3. WHEN no icon mapping exists for a resource type, THE Resource_Node SHALL render a generic placeholder icon consisting of a 48x48 pixel gray square with a question mark symbol, visually distinct from any mapped service icon.
4. THE Architecture_Icon_Resolver SHALL map container types (AWS Cloud, Account, Region, VPC, Public Subnet, Private Subnet, Auto Scaling Group) to SVG icons from the Architecture-Group-Icons_07312025 asset directory.
5. THE Container_Node SHALL render the mapped group icon as a 32x32 pixel badge in the top-left corner of the container header, aligned vertically with the container label text.
6. IF a mapped SVG icon file fails to load, THEN THE Resource_Node or Container_Node SHALL render the generic placeholder icon in its place.

### Requirement 3: Spatial Grouping by Network Location

**User Story:** As an SRE, I want resources to appear inside the subnet, AZ, and VPC they belong to, so that I can verify correct network placement and identify misconfigurations.

#### Acceptance Criteria

1. WHEN a resource has a subnet_id attribute, THE Layout_Engine SHALL place that Resource_Node inside the corresponding Subnet Container_Node.
2. WHEN a resource has a vpc_id attribute but no subnet_id and has an availability_zone attribute, THE Layout_Engine SHALL place that Resource_Node inside the corresponding Availability Zone Container_Node but outside any Subnet container.
3. WHEN a resource has a vpc_id attribute but no subnet_id and no availability_zone attribute, THE Layout_Engine SHALL place that Resource_Node inside the corresponding VPC Container_Node but outside any AZ or Subnet container.
4. WHEN a resource has neither vpc_id nor subnet_id and is not a global service (IAM, Route53, CloudFront, S3, WAF), THE Layout_Engine SHALL place that Resource_Node inside the Region Container_Node but outside any VPC container.
5. WHEN a resource is a global service (IAM, Route53, CloudFront, S3, WAF), THE Layout_Engine SHALL place that Resource_Node inside the Account Container_Node but outside any Region container.
6. WHEN a resource has is_external set to true, THE Layout_Engine SHALL place that Resource_Node outside the AWS Cloud Container_Node in an "External Resources" area.
7. THE Layout_Engine SHALL evaluate placement attributes in the following priority order: is_external (highest), global service membership, subnet_id, vpc_id, region (lowest), using the first matching rule to determine placement.
8. THE Layout_Engine SHALL arrange Resource_Nodes within a container using a grid or flow-based sub-layout with a minimum spacing of 16 pixels between adjacent Resource_Nodes to prevent overlap.

### Requirement 4: Visual Connections and Relationship Arrows

**User Story:** As a cloud architect, I want to see arrows connecting related resources with visual differentiation by relationship type, so that I can trace data flows, network paths, and IAM dependencies.

#### Acceptance Criteria

1. THE Edge_Renderer SHALL draw a directed arrow from source to target for each relationship in the diagram data.
2. WHEN a relationship has category "network", THE Edge_Renderer SHALL render the arrow with a solid line style and a blue color.
3. WHEN a relationship has category "iam", THE Edge_Renderer SHALL render the arrow with a dashed line style and a red color.
4. WHEN a relationship has category "event", THE Edge_Renderer SHALL render the arrow with a dotted line style and an orange color.
5. WHEN a relationship has category "data", THE Edge_Renderer SHALL render the arrow with a solid line style and a purple color.
6. WHEN an edge label is present and its text length exceeds 40 characters, THE Edge_Renderer SHALL truncate the label to 40 characters followed by an ellipsis and display it along the edge path; WHEN the label is 40 characters or fewer, THE Edge_Renderer SHALL display the full label text along the edge path.
7. THE Edge_Renderer SHALL route arrows around container boundaries to avoid crossing through containers that do not contain either the source or target node of that edge.
8. WHEN the user hovers over an edge, THE Edge_Renderer SHALL increase the edge stroke width to 3 pixels and display a tooltip with the derived_from metadata; IF derived_from metadata is not present on the hovered edge, THEN THE Edge_Renderer SHALL display a tooltip showing the relationship category and the source and target resource names.
9. IF a relationship has a category value that is not one of "network", "iam", "event", or "data", THEN THE Edge_Renderer SHALL render the arrow with a solid line style and a gray color.

### Requirement 5: Boundary Service Positioning

**User Story:** As a cloud architect, I want Internet Gateways, NAT Gateways, and WAF resources positioned at the boundary of their respective containers, so that I can see how traffic enters and exits each network layer.

#### Acceptance Criteria

1. WHEN a resource is of type "internet_gateway", THE Layout_Engine SHALL position it on the top edge boundary between the VPC container and the Region container, with the node center aligned to the VPC container's top border.
2. WHEN a resource is of type "nat_gateway" and both a public subnet container and a private subnet container exist within the same AZ, THE Layout_Engine SHALL position it on the boundary between the public subnet container and the private subnet container, with the node center aligned to the shared edge between those two containers.
3. WHEN a resource is of type "waf", THE Layout_Engine SHALL position it on the top edge boundary between the AWS Cloud container and the External Resources area.
4. WHEN a resource is of type "vpn_gateway", THE Layout_Engine SHALL position it on the top edge boundary between the VPC container and the External Resources area.
5. THE Layout_Engine SHALL visually attach boundary services to the container edge by centering the node on the container border line, resulting in 50% of the node area inside the container and 50% outside.
6. IF a boundary service cannot be positioned between two containers because the adjacent container does not exist in the diagram, THEN THE Layout_Engine SHALL position the boundary service node inside the innermost container it belongs to, aligned to the container edge nearest to where traffic would exit.
7. WHEN multiple boundary services are positioned on the same container edge, THE Layout_Engine SHALL space them horizontally with a minimum gap of 20 pixels between adjacent boundary service nodes to prevent overlap.

### Requirement 6: Backend Hierarchy Data Transformation

**User Story:** As a frontend developer, I want the backend to provide pre-computed hierarchy data that maps each resource to its container path, so that the frontend can render nested containers without complex re-computation.

#### Acceptance Criteria

1. THE Hierarchy_Builder SHALL produce a tree structure with levels: cloud → account → regions → vpcs → availability_zones → subnets.
2. THE Hierarchy_Builder SHALL assign each resource to the deepest container it belongs to based on its vpc_id, subnet_id, and availability_zone attributes.
3. THE Hierarchy_Builder SHALL classify subnets as "public" or "private" based on route table associations; IF a subnet has no associated route table in the scan data, THEN THE Hierarchy_Builder SHALL classify it as "private" by default.
4. WHEN a resource references a VPC or subnet that was not discovered in the scan, THE Hierarchy_Builder SHALL create a placeholder container labeled "Unknown VPC" or "Unknown Subnet".
5. THE Hierarchy_Builder SHALL expose the hierarchy data through the existing `/api/diagrams/{scan_id}` endpoint as an additional `hierarchy` field alongside the existing `nodes` and `edges` fields.
6. THE Hierarchy_Builder SHALL include container metadata: id, name, type (cloud, account, region, vpc, az, subnet), parent_id, subnet_type (public or private, for subnet containers), icon_key, and a `resources` array listing the resource IDs assigned to that container.
7. THE Hierarchy_Builder SHALL assign global services (IAM, Route53, CloudFront, S3, WAF) to the account-level container and regional non-VPC services to the region-level container.

### Requirement 7: Color Coding and Visual Styling

**User Story:** As a user, I want containers and resources styled with distinct colors matching official AWS architecture diagram conventions, so that the diagram is immediately readable and professional.

#### Acceptance Criteria

1. THE Diagram_Renderer SHALL style the AWS Cloud container with a background color of rgba(240, 240, 240, 0.5) and a 2px dashed border in color #232F3E.
2. THE Diagram_Renderer SHALL style the Account container with a 2px dashed border in color #DF3312 and no background fill (transparent).
3. THE Diagram_Renderer SHALL style Region containers with a 2px dashed border in color #147EB4 and a background color of rgba(20, 126, 180, 0.05).
4. THE Diagram_Renderer SHALL style VPC containers with a 2px solid border in color #1B660F and a background color of rgba(27, 102, 15, 0.05).
5. THE Diagram_Renderer SHALL style public Subnet containers with a background color of rgba(27, 102, 15, 0.15) and a 2px solid border in color #1B660F.
6. THE Diagram_Renderer SHALL style private Subnet containers with a background color of rgba(20, 126, 180, 0.15) and a 2px solid border in color #147EB4.
7. THE Diagram_Renderer SHALL style Availability Zone containers with a 1px dashed border in color #5A6B7B, no background fill, and an AZ label badge.
8. THE Diagram_Renderer SHALL render container labels in a header bar at the top of the container with the group icon on the left side, using a font size of 14px and font weight of 600.

### Requirement 8: Interactive Diagram Behavior

**User Story:** As a user, I want to pan, zoom, expand/collapse containers, and click resources for details, so that I can navigate complex architectures without being overwhelmed.

#### Acceptance Criteria

1. THE Diagram_Renderer SHALL support pan and zoom gestures with zoom range 0.1x to 5.0x.
2. WHEN the diagram is initially loaded, THE Diagram_Renderer SHALL fit the entire diagram in view with all nodes visible within the viewport boundaries.
3. WHEN the user double-clicks a Container_Node, THE Diagram_Renderer SHALL toggle between collapsed (showing only the container label and resource count) and expanded (showing all children) states.
4. WHILE a container is collapsed, THE Diagram_Renderer SHALL display a badge indicating the total number of resources recursively contained within that container (including resources in nested sub-containers).
5. WHEN the user single-clicks a Resource_Node, THE Diagram_Renderer SHALL emit a node selection event with the resource ARN for the detail panel.
6. WHEN the user hovers over a Resource_Node, THE Diagram_Renderer SHALL highlight all edges connected to that node by increasing their stroke width to 3 pixels and reduce unrelated edges to 20% opacity.
7. WHEN the user moves the cursor away from a Resource_Node, THE Diagram_Renderer SHALL restore all edges to their default stroke width and full opacity.
8. THE Diagram_Renderer SHALL provide a "fit view" button that resets the viewport to show the entire diagram.
9. WHEN a container is collapsed and it contains resources that are the source or target of edges, THE Diagram_Renderer SHALL reroute those edges to connect to the collapsed Container_Node instead of the hidden child nodes.

### Requirement 9: Cross-Account and External Resource Rendering

**User Story:** As a user with multi-account setups, I want to see cross-account references and external resources visually separated from the main AWS infrastructure, so that I can understand dependencies that extend beyond my scanned account.

#### Acceptance Criteria

1. WHEN a resource has is_external set to true, THE Diagram_Renderer SHALL render it in a dedicated "External Resources" Container_Node positioned to the right of or above the AWS Cloud container, separated by at least 40 pixels of whitespace from the AWS Cloud container border.
2. WHEN external resources are present, THE Diagram_Renderer SHALL group them into sub-containers by inferred category: "Cross-Account AWS" for resources whose ARN contains a different AWS account ID, "On-Premises" for resources referenced via VPN gateway relationships, and "Third-Party" for resources identified by non-AWS hostnames.
3. WHEN a relationship edge connects an internal resource to an external resource, THE Edge_Renderer SHALL draw the arrow crossing the AWS Cloud container boundary with a visible path from source to target.
4. THE Diagram_Renderer SHALL style external Resource_Nodes with a background opacity of 50% relative to internal nodes and a dashed border to differentiate them from internal resources.
5. IF an external resource cannot be classified into "Cross-Account AWS", "On-Premises", or "Third-Party", THEN THE Diagram_Renderer SHALL place it in a default "Unknown External" sub-container within the External Resources area.

### Requirement 10: Responsive Layout and Performance

**User Story:** As a user scanning large AWS accounts, I want the diagram to render efficiently even with hundreds of resources, so that I do not experience lag or unresponsive UI.

#### Acceptance Criteria

1. THE Layout_Engine SHALL compute positions for up to 500 resources and 100 containers within 3 seconds on a machine with a 4-core CPU, 8 GB RAM, and the latest stable release of Chrome or Firefox.
2. WHEN the total resource count exceeds 200, THE Diagram_Renderer SHALL enable viewport culling to render only nodes visible in the current viewport.
3. WHILE viewport culling is enabled, THE Diagram_Renderer SHALL keep the number of DOM-rendered nodes at or below the count of nodes visible in the current viewport plus a 50-node buffer.
4. WHEN the diagram contains more than 50 containers, THE Layout_Engine SHALL auto-collapse containers deeper than 2 levels from the root on initial render.
5. IF the layout computation exceeds 5 seconds, THEN THE Diagram_Renderer SHALL display a visible progress indicator and provide a cancel button that, when activated, stops computation and restores the last successfully rendered diagram state or displays an empty canvas if no prior diagram exists.
