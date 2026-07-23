"""Unit tests for the HierarchyBuilder service.

Validates:
- Requirements 6.1: Hierarchy tree construction (cloud → account → region → vpc → az → subnet)
- Requirements 6.2: Resource placement into correct containers
- Requirements 6.3: Default private classification when no route table exists
- Requirements 6.4: Placeholder container creation for unknown VPCs
"""

import pytest

from backend.models.resources import Resource, Relationship
from backend.models.hierarchy import HierarchyTree, ContainerMetadata
from backend.services.hierarchy_builder import HierarchyBuilder


@pytest.fixture
def builder() -> HierarchyBuilder:
    """Create a HierarchyBuilder instance."""
    return HierarchyBuilder()


@pytest.fixture
def account_id() -> str:
    """Standard test account ID."""
    return "123456789012"


class TestTreeConstruction:
    """Validates Requirements 6.1, 6.2: Tree construction with multi-VPC, multi-AZ scan."""

    def test_multi_vpc_multi_az_hierarchy_structure(self, builder: HierarchyBuilder, account_id: str):
        """A scan with 2 VPCs, multiple subnets in different AZs produces correct nesting."""
        resources = [
            # VPC 1
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC Alpha",
                region="us-east-1",
                tags={"Name": "VPC Alpha"},
                attributes={"vpc_id": "vpc-aaa"},
            ),
            # VPC 2
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-bbb",
                resource_type="vpc",
                name="VPC Beta",
                region="us-east-1",
                tags={"Name": "VPC Beta"},
                attributes={"vpc_id": "vpc-bbb"},
            ),
            # Subnet in VPC 1, AZ us-east-1a
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-001",
                resource_type="subnet",
                name="Public Subnet 1a",
                region="us-east-1",
                tags={"Name": "Public Subnet 1a"},
                attributes={
                    "subnet_id": "subnet-001",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                    "route_tables": [{"routes": [{"destination": "0.0.0.0/0", "target": "igw-123"}]}],
                },
            ),
            # Subnet in VPC 1, AZ us-east-1b
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-002",
                resource_type="subnet",
                name="Private Subnet 1b",
                region="us-east-1",
                tags={"Name": "Private Subnet 1b"},
                attributes={
                    "subnet_id": "subnet-002",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1b",
                },
            ),
            # Subnet in VPC 2, AZ us-east-1a
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-003",
                resource_type="subnet",
                name="Private Subnet 2a",
                region="us-east-1",
                tags={"Name": "Private Subnet 2a"},
                attributes={
                    "subnet_id": "subnet-003",
                    "vpc_id": "vpc-bbb",
                    "availability_zone": "us-east-1a",
                },
            ),
            # EC2 instance in subnet-001
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-111",
                resource_type="ec2",
                name="Web Server",
                region="us-east-1",
                attributes={"subnet_id": "subnet-001", "vpc_id": "vpc-aaa"},
            ),
            # Lambda in VPC 2
            Resource(
                arn="arn:aws:lambda:us-east-1:123456789012:function:processor",
                resource_type="lambda",
                name="processor",
                region="us-east-1",
                attributes={"subnet_id": "subnet-003", "vpc_id": "vpc-bbb"},
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        # Verify root is cloud
        assert tree.root_id == "cloud"
        cloud = containers_map["cloud"]
        assert cloud.type == "cloud"
        assert cloud.parent_id is None

        # Verify account under cloud
        account_container_id = f"account-{account_id}"
        assert account_container_id in containers_map
        account = containers_map[account_container_id]
        assert account.type == "account"
        assert account.parent_id == "cloud"
        assert account_container_id in cloud.children

        # Verify region under account
        region_id = "region-us-east-1"
        assert region_id in containers_map
        region = containers_map[region_id]
        assert region.type == "region"
        assert region.parent_id == account_container_id
        assert region_id in account.children

        # Verify both VPCs under region
        assert "vpc-vpc-aaa" in containers_map
        assert "vpc-vpc-bbb" in containers_map
        vpc_a = containers_map["vpc-vpc-aaa"]
        vpc_b = containers_map["vpc-vpc-bbb"]
        assert vpc_a.type == "vpc"
        assert vpc_b.type == "vpc"
        assert vpc_a.parent_id == region_id
        assert vpc_b.parent_id == region_id
        assert "vpc-vpc-aaa" in region.children
        assert "vpc-vpc-bbb" in region.children

        # Verify AZ containers under VPC A
        az_1a_id = "az-us-east-1-us-east-1a"
        az_1b_id = "az-us-east-1-us-east-1b"
        assert az_1a_id in containers_map
        assert az_1b_id in containers_map
        assert containers_map[az_1a_id].parent_id == "vpc-vpc-aaa"
        assert containers_map[az_1b_id].parent_id == "vpc-vpc-aaa"

        # Verify subnets under AZs
        assert "subnet-subnet-001" in containers_map
        assert containers_map["subnet-subnet-001"].parent_id == az_1a_id
        assert "subnet-subnet-002" in containers_map
        assert containers_map["subnet-subnet-002"].parent_id == az_1b_id

    def test_resources_assigned_to_correct_containers(self, builder: HierarchyBuilder, account_id: str):
        """Resources are placed in their deepest matching container."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC Alpha",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-001",
                resource_type="subnet",
                name="Subnet 1",
                region="us-east-1",
                attributes={
                    "subnet_id": "subnet-001",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                },
            ),
            # EC2 in subnet → should go to subnet container
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-111",
                resource_type="ec2",
                name="Web Server",
                region="us-east-1",
                attributes={"subnet_id": "subnet-001", "vpc_id": "vpc-aaa"},
            ),
            # Global service → should go to account container
            Resource(
                arn="arn:aws:s3:::my-bucket",
                resource_type="s3",
                name="my-bucket",
                region="us-east-1",
            ),
            # Resource with only vpc_id → should go to VPC container
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:security-group/sg-111",
                resource_type="security_group",
                name="SG 1",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        # EC2 is in subnet container
        subnet_container = containers_map["subnet-subnet-001"]
        assert "arn:aws:ec2:us-east-1:123456789012:instance/i-111" in subnet_container.resources

        # S3 is in account container
        account_container = containers_map[f"account-{account_id}"]
        assert "arn:aws:s3:::my-bucket" in account_container.resources

        # Security group is in VPC container
        vpc_container = containers_map["vpc-vpc-aaa"]
        assert "arn:aws:ec2:us-east-1:123456789012:security-group/sg-111" in vpc_container.resources

    def test_container_children_relationships_are_bidirectional(self, builder: HierarchyBuilder, account_id: str):
        """Every container listed as a child has its parent_id pointing back to the parent."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC Alpha",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-001",
                resource_type="subnet",
                name="Subnet 1",
                region="us-east-1",
                attributes={
                    "subnet_id": "subnet-001",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                },
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        for container in tree.containers:
            for child_id in container.children:
                child = containers_map[child_id]
                assert child.parent_id == container.id, (
                    f"Child '{child_id}' has parent_id='{child.parent_id}' "
                    f"but is listed as child of '{container.id}'"
                )


class TestPlaceholderContainerCreation:
    """Validates Requirement 6.4: Placeholder containers for unknown VPCs."""

    def test_unknown_vpc_creates_placeholder(self, builder: HierarchyBuilder, account_id: str):
        """A resource referencing an unknown vpc_id triggers placeholder VPC creation."""
        resources = [
            # EC2 referencing a VPC that has no corresponding VPC resource
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-orphan",
                resource_type="ec2",
                name="Orphan Instance",
                region="us-east-1",
                attributes={"vpc_id": "vpc-unknown-123"},
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        # Placeholder VPC should exist
        placeholder_id = "vpc-vpc-unknown-123"
        assert placeholder_id in containers_map
        placeholder = containers_map[placeholder_id]
        assert placeholder.type == "vpc"
        assert "Unknown VPC" in placeholder.name
        assert "vpc-unknown-123" in placeholder.name

    def test_placeholder_vpc_parented_under_region(self, builder: HierarchyBuilder, account_id: str):
        """Placeholder VPC container is correctly parented under the region container."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-west-2:123456789012:instance/i-orphan",
                resource_type="ec2",
                name="Orphan Instance",
                region="us-west-2",
                attributes={"vpc_id": "vpc-mystery"},
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-west-2"])
        containers_map = {c.id: c for c in tree.containers}

        placeholder = containers_map["vpc-vpc-mystery"]
        assert placeholder.parent_id == "region-us-west-2"

        # Region should list the placeholder as a child
        region = containers_map["region-us-west-2"]
        assert "vpc-vpc-mystery" in region.children

    def test_resource_assigned_to_placeholder_vpc(self, builder: HierarchyBuilder, account_id: str):
        """The resource referencing an unknown VPC is placed inside the placeholder container."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-orphan",
                resource_type="ec2",
                name="Orphan",
                region="us-east-1",
                attributes={"vpc_id": "vpc-ghost"},
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        placeholder = containers_map["vpc-vpc-ghost"]
        assert "arn:aws:ec2:us-east-1:123456789012:instance/i-orphan" in placeholder.resources


class TestSubnetClassification:
    """Validates Requirement 6.3: Default private classification when no route table exists."""

    def test_subnet_without_route_table_is_private(self, builder: HierarchyBuilder, account_id: str):
        """A subnet with no route_tables attribute defaults to private classification."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-no-rt",
                resource_type="subnet",
                name="No Route Table Subnet",
                region="us-east-1",
                attributes={
                    "subnet_id": "subnet-no-rt",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                },
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        subnet_container = containers_map["subnet-subnet-no-rt"]
        assert subnet_container.subnet_type == "private"
        assert subnet_container.icon_key == "private_subnet"

    def test_subnet_with_igw_route_is_public(self, builder: HierarchyBuilder, account_id: str):
        """A subnet with route table containing 0.0.0.0/0 → igw-* is classified as public."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-pub",
                resource_type="subnet",
                name="Public Subnet",
                region="us-east-1",
                attributes={
                    "subnet_id": "subnet-pub",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                    "route_tables": [
                        {
                            "routes": [
                                {"destination": "10.0.0.0/16", "target": "local"},
                                {"destination": "0.0.0.0/0", "target": "igw-abc123"},
                            ]
                        }
                    ],
                },
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        subnet_container = containers_map["subnet-subnet-pub"]
        assert subnet_container.subnet_type == "public"
        assert subnet_container.icon_key == "public_subnet"

    def test_subnet_with_non_igw_default_route_is_private(self, builder: HierarchyBuilder, account_id: str):
        """A subnet with 0.0.0.0/0 route targeting a NAT gateway is still private."""
        resources = [
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-aaa",
                resource_type="vpc",
                name="VPC",
                region="us-east-1",
                attributes={"vpc_id": "vpc-aaa"},
            ),
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-nat",
                resource_type="subnet",
                name="NAT Subnet",
                region="us-east-1",
                attributes={
                    "subnet_id": "subnet-nat",
                    "vpc_id": "vpc-aaa",
                    "availability_zone": "us-east-1a",
                    "route_tables": [
                        {
                            "routes": [
                                {"destination": "0.0.0.0/0", "target": "nat-xyz789"},
                            ]
                        }
                    ],
                },
            ),
        ]

        tree = builder.build(resources, [], account_id, ["us-east-1"])
        containers_map = {c.id: c for c in tree.containers}

        subnet_container = containers_map["subnet-subnet-nat"]
        assert subnet_container.subnet_type == "private"


class TestEmptyScan:
    """Validates Requirement 6.1: Empty scan returns minimal hierarchy."""

    def test_empty_resources_returns_cloud_and_account(self, builder: HierarchyBuilder, account_id: str):
        """An empty scan produces at minimum cloud + account containers."""
        tree = builder.build([], [], account_id, [])

        containers_map = {c.id: c for c in tree.containers}

        # Cloud container exists and is root
        assert "cloud" in containers_map
        cloud = containers_map["cloud"]
        assert cloud.type == "cloud"
        assert cloud.parent_id is None
        assert tree.root_id == "cloud"

        # Account container exists and is child of cloud
        account_container_id = f"account-{account_id}"
        assert account_container_id in containers_map
        account = containers_map[account_container_id]
        assert account.type == "account"
        assert account.parent_id == "cloud"
        assert account_container_id in cloud.children

    def test_empty_resources_with_regions_creates_region_containers(self, builder: HierarchyBuilder, account_id: str):
        """Even with no resources, scanned regions produce region containers."""
        tree = builder.build([], [], account_id, ["us-east-1", "eu-west-1"])

        containers_map = {c.id: c for c in tree.containers}

        assert "region-us-east-1" in containers_map
        assert "region-eu-west-1" in containers_map
        assert containers_map["region-us-east-1"].type == "region"
        assert containers_map["region-eu-west-1"].type == "region"

    def test_empty_resources_has_no_boundary_services(self, builder: HierarchyBuilder, account_id: str):
        """An empty scan produces no boundary service placements."""
        tree = builder.build([], [], account_id, ["us-east-1"])

        assert tree.boundary_services == []

    def test_empty_resources_containers_have_no_resources(self, builder: HierarchyBuilder, account_id: str):
        """All containers in an empty scan have empty resource lists."""
        tree = builder.build([], [], account_id, ["us-east-1"])

        for container in tree.containers:
            assert container.resources == [], (
                f"Container '{container.id}' should have no resources but has {container.resources}"
            )
