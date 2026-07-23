"""Property-based tests for hierarchy builder.

# Feature: architecture-diagram-visualization, Property 1: Hierarchy Nesting Order

**Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6, 6.1**

Property 1: Hierarchy Nesting Order
- For any set of resources across accounts, regions, VPCs, AZs, and subnets,
  every container's parent type follows the strict ordering:
  cloud → account → region → vpc → az → subnet.
- Specifically: a container of type X must have a parent of the type that comes
  before X in the ordering (or None for the root cloud container).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.resources import Relationship, Resource
from backend.models.hierarchy import ContainerMetadata, HierarchyTree
from backend.services.hierarchy_builder import HierarchyBuilder


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The strict nesting order: each type maps to its required parent type
EXPECTED_PARENT_TYPE: dict[str, str | None] = {
    "cloud": None,
    "account": "cloud",
    "region": "account",
    "vpc": "region",
    "az": "vpc",
    "subnet": "az",
}

# Valid AWS region codes (representative subset)
VALID_AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-central-1",
    "ap-southeast-1",
    "ap-northeast-1",
]

# Availability zones per region (suffix only)
AZ_SUFFIXES = ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

region_strategy = st.sampled_from(VALID_AWS_REGIONS)

hex_suffix = st.text(alphabet="0123456789abcdef", min_size=8, max_size=17)

vpc_id_strategy = hex_suffix.map(lambda s: f"vpc-{s}")
subnet_id_strategy = hex_suffix.map(lambda s: f"subnet-{s}")
instance_id_strategy = hex_suffix.map(lambda s: f"i-{s}")

account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

az_suffix_strategy = st.sampled_from(AZ_SUFFIXES)


@st.composite
def vpc_resource_strategy(draw: st.DrawFn) -> tuple[Resource, str, str]:
    """Generate a VPC resource and return (resource, vpc_id, region)."""
    region = draw(region_strategy)
    account_id = draw(account_id_strategy)
    vpc_id = draw(vpc_id_strategy)
    arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
    resource = Resource(
        arn=arn,
        resource_type="vpc",
        name=f"vpc-{vpc_id}",
        region=region,
        attributes={"vpc_id": vpc_id},
    )
    return (resource, vpc_id, region)


@st.composite
def subnet_resource_strategy(
    draw: st.DrawFn, vpc_id: str, region: str
) -> tuple[Resource, str, str]:
    """Generate a subnet resource within a given VPC and region."""
    account_id = draw(account_id_strategy)
    subnet_id = draw(subnet_id_strategy)
    az_suffix = draw(az_suffix_strategy)
    az = f"{region}{az_suffix}"
    arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    resource = Resource(
        arn=arn,
        resource_type="subnet",
        name=f"subnet-{subnet_id}",
        region=region,
        attributes={
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": az,
        },
    )
    return (resource, subnet_id, az)


@st.composite
def ec2_resource_strategy(
    draw: st.DrawFn,
    region: str,
    vpc_id: str | None = None,
    subnet_id: str | None = None,
    az: str | None = None,
) -> Resource:
    """Generate an EC2 instance resource."""
    account_id = draw(account_id_strategy)
    instance_id = draw(instance_id_strategy)
    arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
    attributes: dict = {}
    if vpc_id:
        attributes["vpc_id"] = vpc_id
    if subnet_id:
        attributes["subnet_id"] = subnet_id
    if az:
        attributes["availability_zone"] = az
    return Resource(
        arn=arn,
        resource_type="ec2",
        name=f"instance-{instance_id}",
        region=region,
        attributes=attributes,
    )


@st.composite
def lambda_resource_strategy(draw: st.DrawFn, region: str, vpc_id: str | None = None) -> Resource:
    """Generate a Lambda function resource."""
    account_id = draw(account_id_strategy)
    func_name = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=3, max_size=12)
    )
    arn = f"arn:aws:lambda:{region}:{account_id}:function:{func_name}"
    attributes: dict = {}
    if vpc_id:
        attributes["vpc_id"] = vpc_id
    return Resource(
        arn=arn,
        resource_type="lambda",
        name=func_name,
        region=region,
        attributes=attributes,
    )


@st.composite
def global_service_resource_strategy(draw: st.DrawFn) -> Resource:
    """Generate a global service resource (IAM, S3, Route53)."""
    account_id = draw(account_id_strategy)
    service_type = draw(st.sampled_from(["iam", "s3", "route53"]))
    name = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=3, max_size=10)
    )
    if service_type == "iam":
        arn = f"arn:aws:iam::{account_id}:role/{name}"
        region = "global"
    elif service_type == "s3":
        arn = f"arn:aws:s3:::{name}"
        region = "global"
    else:
        arn = f"arn:aws:route53:::{name}"
        region = "global"
    return Resource(
        arn=arn,
        resource_type=service_type,
        name=name,
        region=region,
    )


@st.composite
def scan_data_strategy(draw: st.DrawFn) -> tuple[list[Resource], str, list[str]]:
    """Generate random scan data with resources across accounts, regions, VPCs, AZs, subnets.

    Returns (resources, account_id, scanned_regions).
    """
    account_id = draw(account_id_strategy)

    # Pick 1-3 regions
    num_regions = draw(st.integers(min_value=1, max_value=3))
    regions = draw(
        st.lists(region_strategy, min_size=num_regions, max_size=num_regions, unique=True)
    )

    resources: list[Resource] = []
    all_vpcs: list[tuple[str, str]] = []  # (vpc_id, region)
    all_subnets: list[tuple[str, str, str]] = []  # (subnet_id, vpc_id, az)

    # Generate 1-3 VPCs per region
    for region in regions:
        num_vpcs = draw(st.integers(min_value=1, max_value=3))
        for _ in range(num_vpcs):
            vpc_id = draw(vpc_id_strategy)
            vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
            resources.append(
                Resource(
                    arn=vpc_arn,
                    resource_type="vpc",
                    name=f"vpc-{vpc_id}",
                    region=region,
                    attributes={"vpc_id": vpc_id},
                )
            )
            all_vpcs.append((vpc_id, region))

            # Generate 1-3 subnets per VPC
            num_subnets = draw(st.integers(min_value=1, max_value=3))
            for _ in range(num_subnets):
                subnet_id = draw(subnet_id_strategy)
                az_suffix = draw(az_suffix_strategy)
                az = f"{region}{az_suffix}"
                subnet_arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
                resources.append(
                    Resource(
                        arn=subnet_arn,
                        resource_type="subnet",
                        name=f"subnet-{subnet_id}",
                        region=region,
                        attributes={
                            "subnet_id": subnet_id,
                            "vpc_id": vpc_id,
                            "availability_zone": az,
                        },
                    )
                )
                all_subnets.append((subnet_id, vpc_id, az))

    # Generate some EC2 instances placed in subnets
    if all_subnets:
        num_ec2_in_subnet = draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_ec2_in_subnet):
            subnet_id, vpc_id, az = draw(st.sampled_from(all_subnets))
            # Find region for this VPC
            region = next(r for v, r in all_vpcs if v == vpc_id)
            instance_id = draw(instance_id_strategy)
            ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
            resources.append(
                Resource(
                    arn=ec2_arn,
                    resource_type="ec2",
                    name=f"instance-{instance_id}",
                    region=region,
                    attributes={
                        "subnet_id": subnet_id,
                        "vpc_id": vpc_id,
                        "availability_zone": az,
                    },
                )
            )

    # Generate some EC2 instances placed in VPCs (no subnet)
    if all_vpcs:
        num_ec2_in_vpc = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_ec2_in_vpc):
            vpc_id, region = draw(st.sampled_from(all_vpcs))
            az_suffix = draw(az_suffix_strategy)
            az = f"{region}{az_suffix}"
            instance_id = draw(instance_id_strategy)
            ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
            resources.append(
                Resource(
                    arn=ec2_arn,
                    resource_type="ec2",
                    name=f"instance-{instance_id}",
                    region=region,
                    attributes={
                        "vpc_id": vpc_id,
                        "availability_zone": az,
                    },
                )
            )

    # Generate some Lambda functions in VPCs
    if all_vpcs:
        num_lambdas = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_lambdas):
            vpc_id, region = draw(st.sampled_from(all_vpcs))
            func_name = draw(
                st.text(
                    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                    min_size=3,
                    max_size=10,
                )
            )
            lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{func_name}"
            resources.append(
                Resource(
                    arn=lambda_arn,
                    resource_type="lambda",
                    name=func_name,
                    region=region,
                    attributes={"vpc_id": vpc_id},
                )
            )

    # Generate some global services (IAM, S3, Route53)
    num_globals = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_globals):
        service_type = draw(st.sampled_from(["iam", "s3", "route53"]))
        name = draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=3,
                max_size=10,
            )
        )
        if service_type == "iam":
            arn = f"arn:aws:iam::{account_id}:role/{name}"
        elif service_type == "s3":
            arn = f"arn:aws:s3:::{name}"
        else:
            arn = f"arn:aws:route53:::{name}"
        resources.append(
            Resource(
                arn=arn,
                resource_type=service_type,
                name=name,
                region="global",
            )
        )

    # Generate some RDS in VPCs
    if all_vpcs:
        num_rds = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_rds):
            vpc_id, region = draw(st.sampled_from(all_vpcs))
            db_id = draw(
                st.text(
                    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                    min_size=3,
                    max_size=10,
                )
            )
            rds_arn = f"arn:aws:rds:{region}:{account_id}:db:{db_id}"
            resources.append(
                Resource(
                    arn=rds_arn,
                    resource_type="rds",
                    name=f"db-{db_id}",
                    region=region,
                    attributes={"vpc_id": vpc_id},
                )
            )

    return (resources, account_id, regions)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_container_index(tree: HierarchyTree) -> dict[str, ContainerMetadata]:
    """Build a lookup from container ID to ContainerMetadata."""
    return {c.id: c for c in tree.containers}


# ---------------------------------------------------------------------------
# Property 1: Hierarchy Nesting Order
# ---------------------------------------------------------------------------

class TestHierarchyNestingOrder:
    """Every container's parent type follows strict ordering: cloud → account → region → vpc → az → subnet."""

    @given(data=scan_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_every_container_parent_follows_strict_nesting_order(
        self,
        data: tuple[list[Resource], str, list[str]],
    ) -> None:
        """For any generated scan data, every container in the hierarchy tree
        has a parent whose type matches the expected nesting order.

        cloud (parent=None) → account (parent=cloud) → region (parent=account)
        → vpc (parent=region) → az (parent=vpc) → subnet (parent=az)
        """
        resources, account_id, scanned_regions = data

        builder = HierarchyBuilder()
        tree = builder.build(
            resources=resources,
            relationships=[],
            account_id=account_id,
            scanned_regions=scanned_regions,
        )

        container_index = _build_container_index(tree)

        for container in tree.containers:
            expected_parent_type = EXPECTED_PARENT_TYPE[container.type]

            if expected_parent_type is None:
                # Root cloud container must have no parent
                assert container.parent_id is None, (
                    f"Container '{container.id}' of type '{container.type}' "
                    f"should have no parent (root), but has parent_id='{container.parent_id}'"
                )
            else:
                # Non-root containers must have a parent
                assert container.parent_id is not None, (
                    f"Container '{container.id}' of type '{container.type}' "
                    f"should have a parent of type '{expected_parent_type}', but parent_id is None"
                )

                # Parent must exist in the tree
                assert container.parent_id in container_index, (
                    f"Container '{container.id}' of type '{container.type}' "
                    f"references parent_id='{container.parent_id}' which does not exist in the tree"
                )

                # Parent type must match the expected nesting order
                parent = container_index[container.parent_id]
                assert parent.type == expected_parent_type, (
                    f"Container '{container.id}' of type '{container.type}' "
                    f"has parent '{parent.id}' of type '{parent.type}', "
                    f"but expected parent type '{expected_parent_type}'"
                )


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

igw_id_strategy = hex_suffix.map(lambda s: f"igw-{s}")
nat_id_strategy = hex_suffix.map(lambda s: f"nat-{s}")
rtb_id_strategy = hex_suffix.map(lambda s: f"rtb-{s}")

# Non-IGW target prefixes for private subnet routes
NON_IGW_TARGETS = ["nat-", "local", "pcx-", "vpce-", "vgw-", "eni-", "tgw-"]


@st.composite
def route_with_igw_strategy(draw: st.DrawFn) -> dict:
    """Generate a route entry that targets an Internet Gateway (public subnet indicator)."""
    igw_id = draw(igw_id_strategy)
    return {"destination": "0.0.0.0/0", "target": igw_id}


@st.composite
def route_without_igw_strategy(draw: st.DrawFn) -> dict:
    """Generate a route entry that does NOT target an Internet Gateway."""
    prefix = draw(st.sampled_from(NON_IGW_TARGETS))
    suffix = draw(hex_suffix)
    target = f"{prefix}{suffix}" if prefix not in ("local",) else "local"
    # Destination can be 0.0.0.0/0 or something else—key point is target is NOT igw-*
    destination = draw(
        st.sampled_from(["0.0.0.0/0", "10.0.0.0/16", "172.16.0.0/12", "192.168.0.0/16"])
    )
    return {"destination": destination, "target": target}


@st.composite
def route_table_with_igw_strategy(draw: st.DrawFn) -> list[dict]:
    """Generate a route table (as list of route dicts) that contains an IGW route."""
    # Include 0-3 non-IGW routes plus exactly one IGW route
    non_igw_routes = draw(
        st.lists(route_without_igw_strategy(), min_size=0, max_size=3)
    )
    igw_route = draw(route_with_igw_strategy())
    routes = non_igw_routes + [igw_route]
    # Shuffle so IGW route is not always last
    shuffled = draw(st.permutations(routes))
    return list(shuffled)


@st.composite
def route_table_without_igw_strategy(draw: st.DrawFn) -> list[dict]:
    """Generate a route table (as list of route dicts) with NO IGW route."""
    return draw(st.lists(route_without_igw_strategy(), min_size=0, max_size=5))


@st.composite
def subnet_with_embedded_route_tables_strategy(
    draw: st.DrawFn, has_igw: bool
) -> tuple[Resource, bool]:
    """Generate a subnet resource with route table data embedded in attributes.route_tables.

    Returns (resource, expected_is_public).
    """
    account_id = draw(account_id_strategy)
    region = draw(region_strategy)
    subnet_id = draw(subnet_id_strategy)
    vpc_id = draw(vpc_id_strategy)
    az_suffix = draw(az_suffix_strategy)
    az = f"{region}{az_suffix}"

    if has_igw:
        routes = draw(route_table_with_igw_strategy())
    else:
        routes = draw(route_table_without_igw_strategy())

    rtb_id = draw(rtb_id_strategy)
    route_tables = [{"route_table_id": rtb_id, "routes": routes}]

    arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    resource = Resource(
        arn=arn,
        resource_type="subnet",
        name=f"subnet-{subnet_id}",
        region=region,
        attributes={
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": az,
            "route_tables": route_tables,
        },
    )
    return (resource, has_igw)


@st.composite
def subnet_with_embedded_routes_strategy(
    draw: st.DrawFn, has_igw: bool
) -> tuple[Resource, bool]:
    """Generate a subnet resource with route data embedded in attributes.routes.

    Returns (resource, expected_is_public).
    """
    account_id = draw(account_id_strategy)
    region = draw(region_strategy)
    subnet_id = draw(subnet_id_strategy)
    vpc_id = draw(vpc_id_strategy)
    az_suffix = draw(az_suffix_strategy)
    az = f"{region}{az_suffix}"

    if has_igw:
        routes = draw(route_table_with_igw_strategy())
    else:
        routes = draw(route_table_without_igw_strategy())

    arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    resource = Resource(
        arn=arn,
        resource_type="subnet",
        name=f"subnet-{subnet_id}",
        region=region,
        attributes={
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": az,
            "routes": routes,
        },
    )
    return (resource, has_igw)


@st.composite
def subnet_with_external_route_table_strategy(
    draw: st.DrawFn, has_igw: bool
) -> tuple[Resource, Resource, bool]:
    """Generate a subnet + separate route_table resource associated via associated_subnets.

    Returns (subnet_resource, route_table_resource, expected_is_public).
    """
    account_id = draw(account_id_strategy)
    region = draw(region_strategy)
    subnet_id = draw(subnet_id_strategy)
    vpc_id = draw(vpc_id_strategy)
    az_suffix = draw(az_suffix_strategy)
    az = f"{region}{az_suffix}"

    if has_igw:
        routes = draw(route_table_with_igw_strategy())
    else:
        routes = draw(route_table_without_igw_strategy())

    rtb_id = draw(rtb_id_strategy)

    subnet_arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    subnet_resource = Resource(
        arn=subnet_arn,
        resource_type="subnet",
        name=f"subnet-{subnet_id}",
        region=region,
        attributes={
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": az,
        },
    )

    rtb_arn = f"arn:aws:ec2:{region}:{account_id}:route-table/{rtb_id}"
    route_table_resource = Resource(
        arn=rtb_arn,
        resource_type="route_table",
        name=f"rtb-{rtb_id}",
        region=region,
        attributes={
            "routes": routes,
            "associated_subnets": [subnet_id],
            "vpc_id": vpc_id,
        },
    )

    return (subnet_resource, route_table_resource, has_igw)


@st.composite
def subnet_with_no_route_info_strategy(draw: st.DrawFn) -> Resource:
    """Generate a subnet resource with no route table information at all."""
    account_id = draw(account_id_strategy)
    region = draw(region_strategy)
    subnet_id = draw(subnet_id_strategy)
    vpc_id = draw(vpc_id_strategy)
    az_suffix = draw(az_suffix_strategy)
    az = f"{region}{az_suffix}"

    arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    return Resource(
        arn=arn,
        resource_type="subnet",
        name=f"subnet-{subnet_id}",
        region=region,
        attributes={
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": az,
        },
    )


# ---------------------------------------------------------------------------
# Property 2: Subnet Classification Correctness
# ---------------------------------------------------------------------------

# Feature: architecture-diagram-visualization, Property 2: Subnet Classification Correctness


class TestSubnetClassificationCorrectness:
    """Subnet is classified as "public" iff its associated route table contains 0.0.0.0/0 → igw-*;
    otherwise "private".

    **Validates: Requirements 1.7, 1.8, 6.3**
    """

    @given(data=subnet_with_embedded_route_tables_strategy(has_igw=True))
    @settings(max_examples=100, deadline=None)
    def test_subnet_with_igw_in_route_tables_is_public(
        self,
        data: tuple[Resource, bool],
    ) -> None:
        """A subnet whose route_tables attribute contains a route with
        destination 0.0.0.0/0 targeting igw-* must be classified as public."""
        subnet_resource, expected_is_public = data
        assert expected_is_public is True

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [])
        assert result == "public", (
            f"Subnet with IGW route in route_tables should be 'public' but got '{result}'. "
            f"route_tables={subnet_resource.attributes.get('route_tables')}"
        )

    @given(data=subnet_with_embedded_route_tables_strategy(has_igw=False))
    @settings(max_examples=100, deadline=None)
    def test_subnet_without_igw_in_route_tables_is_private(
        self,
        data: tuple[Resource, bool],
    ) -> None:
        """A subnet whose route_tables attribute has routes but none targeting igw-*
        must be classified as private."""
        subnet_resource, expected_is_public = data
        assert expected_is_public is False

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [])
        assert result == "private", (
            f"Subnet without IGW route in route_tables should be 'private' but got '{result}'. "
            f"route_tables={subnet_resource.attributes.get('route_tables')}"
        )

    @given(data=subnet_with_embedded_routes_strategy(has_igw=True))
    @settings(max_examples=100, deadline=None)
    def test_subnet_with_igw_in_routes_attribute_is_public(
        self,
        data: tuple[Resource, bool],
    ) -> None:
        """A subnet whose routes attribute contains a route with
        destination 0.0.0.0/0 targeting igw-* must be classified as public."""
        subnet_resource, expected_is_public = data
        assert expected_is_public is True

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [])
        assert result == "public", (
            f"Subnet with IGW route in routes should be 'public' but got '{result}'. "
            f"routes={subnet_resource.attributes.get('routes')}"
        )

    @given(data=subnet_with_embedded_routes_strategy(has_igw=False))
    @settings(max_examples=100, deadline=None)
    def test_subnet_without_igw_in_routes_attribute_is_private(
        self,
        data: tuple[Resource, bool],
    ) -> None:
        """A subnet whose routes attribute has routes but none targeting igw-*
        must be classified as private."""
        subnet_resource, expected_is_public = data
        assert expected_is_public is False

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [])
        assert result == "private", (
            f"Subnet without IGW route in routes should be 'private' but got '{result}'. "
            f"routes={subnet_resource.attributes.get('routes')}"
        )

    @given(data=subnet_with_external_route_table_strategy(has_igw=True))
    @settings(max_examples=100, deadline=None)
    def test_subnet_with_igw_in_external_route_table_is_public(
        self,
        data: tuple[Resource, Resource, bool],
    ) -> None:
        """A subnet associated with a separate route_table resource that has
        an IGW route must be classified as public."""
        subnet_resource, route_table_resource, expected_is_public = data
        assert expected_is_public is True

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [route_table_resource])
        assert result == "public", (
            f"Subnet with IGW route in external route_table should be 'public' but got '{result}'. "
            f"route_table routes={route_table_resource.attributes.get('routes')}"
        )

    @given(data=subnet_with_external_route_table_strategy(has_igw=False))
    @settings(max_examples=100, deadline=None)
    def test_subnet_with_external_route_table_no_igw_is_private(
        self,
        data: tuple[Resource, Resource, bool],
    ) -> None:
        """A subnet associated with a separate route_table resource that does NOT
        have an IGW route must be classified as private."""
        subnet_resource, route_table_resource, expected_is_public = data
        assert expected_is_public is False

        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet_resource, [route_table_resource])
        assert result == "private", (
            f"Subnet without IGW route in external route_table should be 'private' but got '{result}'. "
            f"route_table routes={route_table_resource.attributes.get('routes')}"
        )

    @given(subnet=subnet_with_no_route_info_strategy())
    @settings(max_examples=100, deadline=None)
    def test_subnet_with_no_route_info_defaults_to_private(
        self,
        subnet: Resource,
    ) -> None:
        """A subnet with no route table information at all must default to private
        (Requirement 6.3)."""
        builder = HierarchyBuilder()
        result = builder._classify_subnet_type(subnet, [])
        assert result == "private", (
            f"Subnet with no route info should default to 'private' but got '{result}'. "
            f"attributes={subnet.attributes}"
        )
