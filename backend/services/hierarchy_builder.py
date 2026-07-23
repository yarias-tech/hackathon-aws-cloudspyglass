"""Builds the AWS infrastructure hierarchy from flat resource data.

Transforms a flat list of scanned resources into a nested container tree
representing: cloud → account → region → vpc → az → subnet.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.7, 5.1, 5.2, 5.3, 5.4
"""

from typing import Literal

from ..models.hierarchy import (
    BoundaryServicePlacement,
    ContainerMetadata,
    HierarchyTree,
)
from ..models.resources import Relationship, Resource


class HierarchyBuilder:
    """Builds the AWS infrastructure hierarchy from flat resource data."""

    GLOBAL_SERVICES = {"iam", "iam_role", "route53", "cloudfront", "s3", "waf", "ecr"}
    BOUNDARY_SERVICES = {"internet_gateway", "nat_gateway", "waf", "vpn_gateway"}

    def build(
        self,
        resources: list[Resource],
        relationships: list[Relationship],
        account_id: str,
        scanned_regions: list[str],
    ) -> HierarchyTree:
        """Build complete hierarchy tree from scan data.

        Constructs the container tree in order: cloud → account → region → vpc → az → subnet.
        Then assigns each resource to its deepest matching container and detects boundary
        service placements.
        """
        containers: dict[str, ContainerMetadata] = {}
        boundary_services: list[BoundaryServicePlacement] = []

        # Level 1: Cloud container (root)
        cloud_id = "cloud"
        containers[cloud_id] = ContainerMetadata(
            id=cloud_id,
            name="AWS Cloud",
            type="cloud",
            parent_id=None,
            icon_key="cloud",
        )

        # Level 2: Account container
        account_container_id = f"account-{account_id}"
        containers[account_container_id] = ContainerMetadata(
            id=account_container_id,
            name=f"Account {account_id}",
            type="account",
            parent_id=cloud_id,
            icon_key="account",
        )
        containers[cloud_id].children.append(account_container_id)

        # Level 3: Region containers
        for region in scanned_regions:
            region_id = f"region-{region}"
            containers[region_id] = ContainerMetadata(
                id=region_id,
                name=region,
                type="region",
                parent_id=account_container_id,
                icon_key="region",
            )
            containers[account_container_id].children.append(region_id)

        # Discover VPCs, subnets, and AZs from resources
        vpc_resources = [r for r in resources if r.resource_type == "vpc"]
        subnet_resources = [r for r in resources if r.resource_type == "subnet"]

        # Level 4: VPC containers
        known_vpcs: set[str] = set()
        for vpc in vpc_resources:
            vpc_id = vpc.attributes.get("vpc_id") or vpc.arn.split("/")[-1]
            if vpc_id in known_vpcs:
                continue
            known_vpcs.add(vpc_id)
            container_id = f"vpc-{vpc_id}"
            region_container_id = f"region-{vpc.region}"

            # Ensure region container exists
            if region_container_id not in containers:
                containers[region_container_id] = ContainerMetadata(
                    id=region_container_id,
                    name=vpc.region,
                    type="region",
                    parent_id=account_container_id,
                    icon_key="region",
                )
                containers[account_container_id].children.append(region_container_id)

            vpc_name = vpc.tags.get("Name", vpc_id)
            containers[container_id] = ContainerMetadata(
                id=container_id,
                name=vpc_name,
                type="vpc",
                parent_id=region_container_id,
                icon_key="vpc",
            )
            containers[region_container_id].children.append(container_id)

        # Level 5 & 6: AZ and Subnet containers
        known_azs: set[str] = set()
        for subnet in subnet_resources:
            subnet_id = subnet.attributes.get("subnet_id") or subnet.arn.split("/")[-1]
            vpc_id = subnet.attributes.get("vpc_id")
            az = subnet.attributes.get("availability_zone")

            if not vpc_id:
                continue

            vpc_container_id = f"vpc-{vpc_id}"
            # Create placeholder VPC if not known
            if vpc_container_id not in containers:
                self._create_placeholder_vpc(
                    containers, vpc_id, subnet.region, account_container_id
                )
                known_vpcs.add(vpc_id)

            # Create AZ container if needed
            if az:
                az_container_id = f"az-{subnet.region}-{az}"
                if az_container_id not in known_azs:
                    known_azs.add(az_container_id)
                    containers[az_container_id] = ContainerMetadata(
                        id=az_container_id,
                        name=az,
                        type="az",
                        parent_id=vpc_container_id,
                        icon_key="az",
                    )
                    containers[vpc_container_id].children.append(az_container_id)

                # Create subnet container
                subnet_type = self._classify_subnet_type(subnet, resources)
                subnet_container_id = f"subnet-{subnet_id}"
                subnet_name = subnet.tags.get("Name", subnet_id)
                icon_key = (
                    "public_subnet" if subnet_type == "public" else "private_subnet"
                )
                containers[subnet_container_id] = ContainerMetadata(
                    id=subnet_container_id,
                    name=subnet_name,
                    type="subnet",
                    parent_id=az_container_id,
                    subnet_type=subnet_type,
                    icon_key=icon_key,
                )
                containers[az_container_id].children.append(subnet_container_id)

        # Assign resources to containers and detect boundary services
        for resource in resources:
            # Skip VPC and subnet resources (they are containers, not leaf resources)
            if resource.resource_type in ("vpc", "subnet"):
                continue

            # Handle boundary services
            if resource.resource_type in self.BOUNDARY_SERVICES:
                placement = self._detect_boundary_placement(resource, containers)
                if placement:
                    boundary_services.append(placement)
                continue

            # Assign to container
            container_id = self._assign_resource_to_container(
                resource, containers, account_container_id
            )
            if container_id and container_id in containers:
                containers[container_id].resources.append(resource.arn)

        tree = HierarchyTree(
            containers=list(containers.values()),
            root_id=cloud_id,
            boundary_services=boundary_services,
        )
        return tree

    def _classify_subnet_type(
        self, subnet_resource: Resource, resources: list[Resource]
    ) -> Literal["public", "private"]:
        """Determine if subnet is public or private based on route tables.

        A subnet is public if it has an associated route table with a route
        targeting an Internet Gateway (destination 0.0.0.0/0 → igw-*).

        If no route table information is available, checks subnet attributes
        for hints (e.g., map_public_ip_on_launch). Defaults to "private" per
        Requirement 6.3.
        """
        # Check subnet attributes for route table data
        route_tables = subnet_resource.attributes.get("route_tables", [])
        if route_tables:
            for rt in route_tables:
                routes = rt.get("routes", [])
                for route in routes:
                    destination = route.get("destination", "")
                    target = route.get("target", "")
                    if destination == "0.0.0.0/0" and target.startswith("igw-"):
                        return "public"

        # Check for route table info embedded in attributes
        routes = subnet_resource.attributes.get("routes", [])
        if routes:
            for route in routes:
                destination = route.get("destination", route.get("DestinationCidrBlock", ""))
                target = route.get("target", route.get("GatewayId", ""))
                if destination == "0.0.0.0/0" and target.startswith("igw-"):
                    return "public"

        # Check if map_public_ip_on_launch is set (common indicator)
        if subnet_resource.attributes.get("map_public_ip_on_launch") is True:
            return "public"

        # Look for route table resources associated with this subnet
        subnet_id = subnet_resource.attributes.get("subnet_id") or subnet_resource.arn.split("/")[-1]
        for resource in resources:
            if resource.resource_type == "route_table":
                associated_subnets = resource.attributes.get("associated_subnets", [])
                if subnet_id in associated_subnets:
                    routes = resource.attributes.get("routes", [])
                    for route in routes:
                        destination = route.get("destination", route.get("DestinationCidrBlock", ""))
                        target = route.get("target", route.get("GatewayId", ""))
                        if destination == "0.0.0.0/0" and target.startswith("igw-"):
                            return "public"

        # Default to private (Requirement 6.3)
        return "private"

    def _assign_resource_to_container(
        self,
        resource: Resource,
        containers: dict[str, ContainerMetadata],
        account_container_id: str,
    ) -> str | None:
        """Return the container_id for the deepest container this resource belongs to.

        Priority order (from Property 3 in design):
        1. is_external → None (external resources area, not assigned to a container)
        2. global service type → account container
        3. has subnet_id → subnet container
        4. has vpc_id + availability_zone → AZ container
        5. has vpc_id only → VPC container
        6. otherwise → region container
        """
        # Priority 1: External resources
        if resource.is_external:
            return None

        # Priority 2: Global services
        if resource.resource_type in self.GLOBAL_SERVICES:
            return account_container_id

        # Priority 3: Has subnet_id
        subnet_id = resource.attributes.get("subnet_id")
        subnet_ids = resource.attributes.get("subnet_ids", [])

        if subnet_id:
            container_id = f"subnet-{subnet_id}"
            if container_id not in containers:
                self._create_placeholder_subnet(
                    containers, subnet_id, resource, account_container_id
                )
            return container_id

        # For resources with multiple subnet_ids, use the first one
        if subnet_ids and len(subnet_ids) > 0:
            first_subnet = subnet_ids[0]
            container_id = f"subnet-{first_subnet}"
            if container_id not in containers:
                self._create_placeholder_subnet(
                    containers, first_subnet, resource, account_container_id
                )
            return container_id

        # Priority 4: Has vpc_id + availability_zone
        vpc_id = resource.attributes.get("vpc_id")
        az = resource.attributes.get("availability_zone")

        if vpc_id and az:
            vpc_container_id = f"vpc-{vpc_id}"
            if vpc_container_id not in containers:
                self._create_placeholder_vpc(
                    containers, vpc_id, resource.region, account_container_id
                )
            az_container_id = f"az-{resource.region}-{az}"
            if az_container_id not in containers:
                containers[az_container_id] = ContainerMetadata(
                    id=az_container_id,
                    name=az,
                    type="az",
                    parent_id=vpc_container_id,
                    icon_key="az",
                )
                containers[vpc_container_id].children.append(az_container_id)
            return az_container_id

        # Priority 5: Has vpc_id only
        if vpc_id:
            vpc_container_id = f"vpc-{vpc_id}"
            if vpc_container_id not in containers:
                self._create_placeholder_vpc(
                    containers, vpc_id, resource.region, account_container_id
                )
            return vpc_container_id

        # Priority 6: Region container (fallback)
        region_container_id = f"region-{resource.region}"
        if region_container_id not in containers:
            # Create region container if it doesn't exist
            containers[region_container_id] = ContainerMetadata(
                id=region_container_id,
                name=resource.region,
                type="region",
                parent_id=account_container_id,
                icon_key="region",
            )
            containers[account_container_id].children.append(region_container_id)
        return region_container_id

    def _create_placeholder_vpc(
        self,
        containers: dict[str, ContainerMetadata],
        vpc_id: str,
        region: str,
        account_container_id: str,
    ) -> None:
        """Create a placeholder VPC container for an unknown VPC."""
        vpc_container_id = f"vpc-{vpc_id}"
        region_container_id = f"region-{region}"

        # Ensure region exists
        if region_container_id not in containers:
            containers[region_container_id] = ContainerMetadata(
                id=region_container_id,
                name=region,
                type="region",
                parent_id=account_container_id,
                icon_key="region",
            )
            containers[account_container_id].children.append(region_container_id)

        containers[vpc_container_id] = ContainerMetadata(
            id=vpc_container_id,
            name=f"Unknown VPC ({vpc_id})",
            type="vpc",
            parent_id=region_container_id,
            icon_key="vpc",
        )
        containers[region_container_id].children.append(vpc_container_id)

    def _create_placeholder_subnet(
        self,
        containers: dict[str, ContainerMetadata],
        subnet_id: str,
        resource: Resource,
        account_container_id: str,
    ) -> None:
        """Create a placeholder subnet container for an unknown subnet."""
        subnet_container_id = f"subnet-{subnet_id}"
        vpc_id = resource.attributes.get("vpc_id")
        az = resource.attributes.get("availability_zone")
        region = resource.region

        # Determine parent: AZ if available, else VPC, else region
        if vpc_id:
            vpc_container_id = f"vpc-{vpc_id}"
            if vpc_container_id not in containers:
                self._create_placeholder_vpc(
                    containers, vpc_id, region, account_container_id
                )

            if az:
                az_container_id = f"az-{region}-{az}"
                if az_container_id not in containers:
                    containers[az_container_id] = ContainerMetadata(
                        id=az_container_id,
                        name=az,
                        type="az",
                        parent_id=vpc_container_id,
                        icon_key="az",
                    )
                    containers[vpc_container_id].children.append(az_container_id)
                parent_id = az_container_id
            else:
                parent_id = vpc_container_id
        else:
            region_container_id = f"region-{region}"
            if region_container_id not in containers:
                containers[region_container_id] = ContainerMetadata(
                    id=region_container_id,
                    name=region,
                    type="region",
                    parent_id=account_container_id,
                    icon_key="region",
                )
                containers[account_container_id].children.append(region_container_id)
            parent_id = region_container_id

        containers[subnet_container_id] = ContainerMetadata(
            id=subnet_container_id,
            name=f"Unknown Subnet ({subnet_id})",
            type="subnet",
            parent_id=parent_id,
            subnet_type="private",
            icon_key="private_subnet",
        )
        containers[parent_id].children.append(subnet_container_id)

    def _detect_boundary_placement(
        self,
        resource: Resource,
        containers: dict[str, ContainerMetadata],
    ) -> BoundaryServicePlacement | None:
        """Detect and create boundary service placement for a resource.

        Boundary services are positioned at container edges:
        - internet_gateway: top edge between VPC and Region
        - nat_gateway: between public and private subnet
        - waf: top edge between AWS Cloud and External Resources
        - vpn_gateway: top edge between VPC and External Resources
        """
        if resource.resource_type == "internet_gateway":
            # IGW sits between VPC and Region
            vpc_id = resource.attributes.get("vpc_id") or resource.attributes.get(
                "attached_vpc"
            )
            if vpc_id:
                vpc_container_id = f"vpc-{vpc_id}"
                region_container_id = f"region-{resource.region}"
                inner_id = (
                    vpc_container_id
                    if vpc_container_id in containers
                    else region_container_id
                )
                outer_id = (
                    region_container_id
                    if region_container_id in containers
                    else None
                )
                return BoundaryServicePlacement(
                    resource_arn=resource.arn,
                    boundary_type="igw",
                    inner_container_id=inner_id,
                    outer_container_id=outer_id,
                    edge_position="top",
                )

        elif resource.resource_type == "nat_gateway":
            # NAT sits between public and private subnets
            subnet_id = resource.attributes.get("subnet_id")
            vpc_id = resource.attributes.get("vpc_id")
            if subnet_id:
                subnet_container_id = f"subnet-{subnet_id}"
                # The NAT is in the public subnet, positioned toward private subnets
                inner_id = (
                    subnet_container_id
                    if subnet_container_id in containers
                    else f"vpc-{vpc_id}" if vpc_id else f"region-{resource.region}"
                )
                # Find a private subnet in the same VPC to use as outer
                outer_id = None
                if vpc_id:
                    vpc_container_id = f"vpc-{vpc_id}"
                    if vpc_container_id in containers:
                        for child_id in containers[vpc_container_id].children:
                            if child_id.startswith("az-"):
                                az_container = containers.get(child_id)
                                if az_container:
                                    for sub_child in az_container.children:
                                        sub_container = containers.get(sub_child)
                                        if (
                                            sub_container
                                            and sub_container.type == "subnet"
                                            and sub_container.subnet_type == "private"
                                        ):
                                            outer_id = sub_child
                                            break
                            if outer_id:
                                break

                return BoundaryServicePlacement(
                    resource_arn=resource.arn,
                    boundary_type="nat",
                    inner_container_id=inner_id,
                    outer_container_id=outer_id,
                    edge_position="bottom",
                )

        elif resource.resource_type == "waf":
            # WAF sits between AWS Cloud and External Resources
            return BoundaryServicePlacement(
                resource_arn=resource.arn,
                boundary_type="waf",
                inner_container_id="cloud",
                outer_container_id=None,
                edge_position="top",
            )

        elif resource.resource_type == "vpn_gateway":
            # VPN Gateway sits between VPC and External Resources
            vpc_id = resource.attributes.get("attached_vpc") or resource.attributes.get(
                "vpc_id"
            )
            if vpc_id:
                vpc_container_id = f"vpc-{vpc_id}"
                inner_id = (
                    vpc_container_id
                    if vpc_container_id in containers
                    else f"region-{resource.region}"
                )
                return BoundaryServicePlacement(
                    resource_arn=resource.arn,
                    boundary_type="vpn",
                    inner_container_id=inner_id,
                    outer_container_id=None,
                    edge_position="top",
                )

        return None
