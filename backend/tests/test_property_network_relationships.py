"""Property-based tests for network relationship detection.

**Validates: Requirements 4.1**

Property 7: Network relationship detection
- For any set of resources containing EC2 instances with SecurityGroup/VPC/Subnet
  references, RDS instances with VPC configurations, Lambda functions with VpcConfig,
  or Load Balancers with targets, the RelationshipResolver SHALL produce a relationship
  record for each detected connection with category: "network" and the correct
  derived_from property name.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.resources import Relationship, Resource
from backend.services.relationship_resolver import RelationshipResolver


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

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

region_strategy = st.sampled_from(VALID_AWS_REGIONS)

# AWS resource ID strategies
hex_suffix = st.text(
    alphabet="0123456789abcdef", min_size=8, max_size=17
)

sg_id_strategy = hex_suffix.map(lambda s: f"sg-{s}")
vpc_id_strategy = hex_suffix.map(lambda s: f"vpc-{s}")
subnet_id_strategy = hex_suffix.map(lambda s: f"subnet-{s}")
instance_id_strategy = hex_suffix.map(lambda s: f"i-{s}")

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(
    alphabet="0123456789", min_size=12, max_size=12
)

# List of security group IDs (1-5)
sg_list_strategy = st.lists(sg_id_strategy, min_size=1, max_size=5, unique=True)

# List of subnet IDs (1-3)
subnet_list_strategy = st.lists(subnet_id_strategy, min_size=1, max_size=3, unique=True)

# Target ARN strategy (simulates EC2 or ECS target ARNs)
target_arn_strategy = st.builds(
    lambda region, account, instance_id: (
        f"arn:aws:ec2:{region}:{account}:instance/{instance_id}"
    ),
    region=region_strategy,
    account=account_id_strategy,
    instance_id=instance_id_strategy,
)

target_arns_strategy = st.lists(target_arn_strategy, min_size=1, max_size=3, unique=True)


# ---------------------------------------------------------------------------
# Helper: Build resource ARN
# ---------------------------------------------------------------------------

def _ec2_arn(region: str, account_id: str, instance_id: str) -> str:
    return f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"


def _rds_arn(region: str, account_id: str, db_id: str) -> str:
    return f"arn:aws:rds:{region}:{account_id}:db:{db_id}"


def _lambda_arn(region: str, account_id: str, func_name: str) -> str:
    return f"arn:aws:lambda:{region}:{account_id}:function:{func_name}"


def _lb_arn(region: str, account_id: str, lb_type: str, lb_name: str) -> str:
    prefix = "net" if lb_type == "nlb" else "app"
    return f"arn:aws:elasticloadbalancing:{region}:{account_id}:loadbalancer/{prefix}/{lb_name}/abc123"


# ---------------------------------------------------------------------------
# Property: EC2 → Security Group relationships
# ---------------------------------------------------------------------------

class TestEC2ToSecurityGroup:
    """EC2 instances with security_groups produce network relationships to each SG."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_ids=sg_list_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ec2_to_sg_produces_network_relationships(
        self, account_id: str, region: str, instance_id: str, sg_ids: list[str]
    ) -> None:
        """For any EC2 with security groups, produces one network relationship per SG."""
        ec2_resource = Resource(
            arn=_ec2_arn(region, account_id, instance_id),
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={"security_groups": sg_ids},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ec2_resource])

        # Filter to only network relationships from this EC2
        network_rels = [
            r for r in relationships
            if r.source_arn == ec2_resource.arn and r.category == "network"
            and r.derived_from == "SecurityGroups[].GroupId"
        ]

        assert len(network_rels) == len(sg_ids), (
            f"Expected {len(sg_ids)} SG relationships, got {len(network_rels)}"
        )

        for sg_id in sg_ids:
            expected_target = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"
            matching = [r for r in network_rels if r.target_arn == expected_target]
            assert len(matching) == 1, (
                f"Expected relationship to {expected_target}, not found"
            )


# ---------------------------------------------------------------------------
# Property: EC2 → VPC relationships
# ---------------------------------------------------------------------------

class TestEC2ToVPC:
    """EC2 instances with vpc_id produce a network relationship to VPC."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        vpc_id=vpc_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ec2_to_vpc_produces_network_relationship(
        self, account_id: str, region: str, instance_id: str, vpc_id: str
    ) -> None:
        """For any EC2 with a vpc_id, produces one network relationship with derived_from='VpcId'."""
        ec2_resource = Resource(
            arn=_ec2_arn(region, account_id, instance_id),
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={"vpc_id": vpc_id},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ec2_resource])

        vpc_rels = [
            r for r in relationships
            if r.source_arn == ec2_resource.arn
            and r.derived_from == "VpcId"
            and r.category == "network"
        ]

        assert len(vpc_rels) == 1, f"Expected 1 VPC relationship, got {len(vpc_rels)}"

        expected_target = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
        assert vpc_rels[0].target_arn == expected_target


# ---------------------------------------------------------------------------
# Property: EC2 → Subnet relationships
# ---------------------------------------------------------------------------

class TestEC2ToSubnet:
    """EC2 instances with subnet_id produce a network relationship to Subnet."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        subnet_id=subnet_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ec2_to_subnet_produces_network_relationship(
        self, account_id: str, region: str, instance_id: str, subnet_id: str
    ) -> None:
        """For any EC2 with a subnet_id, produces one network relationship with derived_from='SubnetId'."""
        ec2_resource = Resource(
            arn=_ec2_arn(region, account_id, instance_id),
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={"subnet_id": subnet_id},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ec2_resource])

        subnet_rels = [
            r for r in relationships
            if r.source_arn == ec2_resource.arn
            and r.derived_from == "SubnetId"
            and r.category == "network"
        ]

        assert len(subnet_rels) == 1, f"Expected 1 Subnet relationship, got {len(subnet_rels)}"

        expected_target = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
        assert subnet_rels[0].target_arn == expected_target


# ---------------------------------------------------------------------------
# Property: RDS → VPC relationships
# ---------------------------------------------------------------------------

class TestRDSToVPC:
    """RDS instances with vpc_id produce a network relationship to VPC."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        vpc_id=vpc_id_strategy,
        db_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=3, max_size=12),
    )
    @settings(max_examples=50, deadline=None)
    def test_rds_to_vpc_produces_network_relationship(
        self, account_id: str, region: str, vpc_id: str, db_id: str
    ) -> None:
        """For any RDS with a vpc_id, produces one network relationship with derived_from='DBSubnetGroup.VpcId'."""
        rds_resource = Resource(
            arn=_rds_arn(region, account_id, db_id),
            resource_type="rds",
            name=f"db-{db_id}",
            region=region,
            attributes={"vpc_id": vpc_id},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([rds_resource])

        vpc_rels = [
            r for r in relationships
            if r.source_arn == rds_resource.arn
            and r.derived_from == "DBSubnetGroup.VpcId"
            and r.category == "network"
        ]

        assert len(vpc_rels) == 1, f"Expected 1 VPC relationship, got {len(vpc_rels)}"

        expected_target = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
        assert vpc_rels[0].target_arn == expected_target


# ---------------------------------------------------------------------------
# Property: Lambda → VPC relationships
# ---------------------------------------------------------------------------

class TestLambdaToVPC:
    """Lambda functions with vpc_id produce a network relationship to VPC."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        vpc_id=vpc_id_strategy,
        func_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=3, max_size=12),
    )
    @settings(max_examples=50, deadline=None)
    def test_lambda_to_vpc_produces_network_relationship(
        self, account_id: str, region: str, vpc_id: str, func_name: str
    ) -> None:
        """For any Lambda with a vpc_id, produces one network relationship with derived_from='VpcConfig.VpcId'."""
        lambda_resource = Resource(
            arn=_lambda_arn(region, account_id, func_name),
            resource_type="lambda",
            name=func_name,
            region=region,
            attributes={"vpc_id": vpc_id},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([lambda_resource])

        vpc_rels = [
            r for r in relationships
            if r.source_arn == lambda_resource.arn
            and r.derived_from == "VpcConfig.VpcId"
            and r.category == "network"
        ]

        assert len(vpc_rels) == 1, f"Expected 1 VPC relationship, got {len(vpc_rels)}"

        expected_target = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
        assert vpc_rels[0].target_arn == expected_target


# ---------------------------------------------------------------------------
# Property: Lambda → Subnet relationships
# ---------------------------------------------------------------------------

class TestLambdaToSubnet:
    """Lambda functions with subnet_ids produce network relationships to each Subnet."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        subnet_ids=subnet_list_strategy,
        func_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=3, max_size=12),
    )
    @settings(max_examples=50, deadline=None)
    def test_lambda_to_subnets_produces_network_relationships(
        self, account_id: str, region: str, subnet_ids: list[str], func_name: str
    ) -> None:
        """For any Lambda with subnet_ids, produces one network relationship per subnet."""
        lambda_resource = Resource(
            arn=_lambda_arn(region, account_id, func_name),
            resource_type="lambda",
            name=func_name,
            region=region,
            attributes={"subnet_ids": subnet_ids},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([lambda_resource])

        subnet_rels = [
            r for r in relationships
            if r.source_arn == lambda_resource.arn
            and r.derived_from == "VpcConfig.SubnetIds[]"
            and r.category == "network"
        ]

        assert len(subnet_rels) == len(subnet_ids), (
            f"Expected {len(subnet_ids)} Subnet relationships, got {len(subnet_rels)}"
        )

        for subnet_id in subnet_ids:
            expected_target = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
            matching = [r for r in subnet_rels if r.target_arn == expected_target]
            assert len(matching) == 1, (
                f"Expected relationship to {expected_target}, not found"
            )


# ---------------------------------------------------------------------------
# Property: ALB/NLB → Targets relationships
# ---------------------------------------------------------------------------

class TestLBToTargets:
    """ALB/NLB with target_arns produce network relationships to each target."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        target_arns=target_arns_strategy,
        lb_type=st.sampled_from(["alb", "nlb"]),
        lb_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=3, max_size=12),
    )
    @settings(max_examples=50, deadline=None)
    def test_lb_to_targets_produces_network_relationships(
        self, account_id: str, region: str, target_arns: list[str],
        lb_type: str, lb_name: str
    ) -> None:
        """For any ALB/NLB with target_arns, produces one network relationship per target."""
        lb_resource = Resource(
            arn=_lb_arn(region, account_id, lb_type, lb_name),
            resource_type=lb_type,
            name=lb_name,
            region=region,
            attributes={"target_arns": target_arns},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([lb_resource])

        target_rels = [
            r for r in relationships
            if r.source_arn == lb_resource.arn
            and r.derived_from == "TargetGroups[].Targets[]"
            and r.category == "network"
        ]

        assert len(target_rels) == len(target_arns), (
            f"Expected {len(target_arns)} target relationships, got {len(target_rels)}"
        )

        for target_arn in target_arns:
            matching = [r for r in target_rels if r.target_arn == target_arn]
            assert len(matching) == 1, (
                f"Expected relationship to {target_arn}, not found"
            )


# ---------------------------------------------------------------------------
# Property: All network relationships have category="network"
# ---------------------------------------------------------------------------

class TestAllNetworkRelationshipsCategory:
    """All relationships from network attributes have category='network'."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_ids=sg_list_strategy,
        vpc_id=vpc_id_strategy,
        subnet_id=subnet_id_strategy,
        func_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=3, max_size=12),
        lambda_vpc_id=vpc_id_strategy,
        lambda_subnet_ids=subnet_list_strategy,
        rds_vpc_id=vpc_id_strategy,
        db_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=3, max_size=12),
    )
    @settings(max_examples=50, deadline=None)
    def test_all_network_derived_relationships_have_network_category(
        self, account_id: str, region: str, instance_id: str,
        sg_ids: list[str], vpc_id: str, subnet_id: str,
        func_name: str, lambda_vpc_id: str, lambda_subnet_ids: list[str],
        rds_vpc_id: str, db_id: str,
    ) -> None:
        """For any mix of resources with network attributes, all relationships have category='network'."""
        resources = [
            Resource(
                arn=_ec2_arn(region, account_id, instance_id),
                resource_type="ec2",
                name=f"instance-{instance_id}",
                region=region,
                attributes={
                    "security_groups": sg_ids,
                    "vpc_id": vpc_id,
                    "subnet_id": subnet_id,
                },
            ),
            Resource(
                arn=_lambda_arn(region, account_id, func_name),
                resource_type="lambda",
                name=func_name,
                region=region,
                attributes={
                    "vpc_id": lambda_vpc_id,
                    "subnet_ids": lambda_subnet_ids,
                },
            ),
            Resource(
                arn=_rds_arn(region, account_id, db_id),
                resource_type="rds",
                name=f"db-{db_id}",
                region=region,
                attributes={"vpc_id": rds_vpc_id},
            ),
        ]

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve(resources)

        # All relationships from network-type derived_from fields should be "network"
        network_derived_from_values = {
            "SecurityGroups[].GroupId",
            "VpcId",
            "SubnetId",
            "DBSubnetGroup.VpcId",
            "VpcConfig.VpcId",
            "VpcConfig.SubnetIds[]",
            "TargetGroups[].Targets[]",
        }

        for rel in relationships:
            if rel.derived_from in network_derived_from_values:
                assert rel.category == "network", (
                    f"Relationship with derived_from='{rel.derived_from}' "
                    f"has category='{rel.category}', expected 'network'"
                )
