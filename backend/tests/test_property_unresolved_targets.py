"""Property-based tests for unresolved target preservation.

**Validates: Requirements 4.7**

Property 11: Unresolved target preservation
- For any relationship where the target ARN is not present in the current scan results,
  the RelationshipResolver SHALL still record the relationship AND mark the target
  resource as is_unresolved: true.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.models.resources import Resource, Relationship
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

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(
    alphabet="0123456789", min_size=12, max_size=12
)

# Resource identifier suffix
resource_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=4,
    max_size=12,
)

# Security group ID strategy
sg_id_strategy = st.builds(
    lambda suffix: f"sg-{suffix}",
    suffix=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
)

# VPC ID strategy
vpc_id_strategy = st.builds(
    lambda suffix: f"vpc-{suffix}",
    suffix=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
)

# Subnet ID strategy
subnet_id_strategy = st.builds(
    lambda suffix: f"subnet-{suffix}",
    suffix=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
)

# Instance ID strategy
instance_id_strategy = st.builds(
    lambda suffix: f"i-{suffix}",
    suffix=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
)


# ---------------------------------------------------------------------------
# Property 11.1: Relationships are preserved for missing targets
# ---------------------------------------------------------------------------

class TestRelationshipsPreservedForMissingTargets:
    """When a resource references targets NOT in the scan, relationships are still recorded.

    **Validates: Requirements 4.7**
    """

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_id=sg_id_strategy,
        vpc_id=vpc_id_strategy,
        subnet_id=subnet_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_ec2_relationships_preserved_when_targets_missing(
        self,
        account_id: str,
        region: str,
        instance_id: str,
        sg_id: str,
        vpc_id: str,
        subnet_id: str,
    ) -> None:
        """For any EC2 referencing SG/VPC/subnet NOT in scan, relationships are still recorded."""
        ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"

        # Create an EC2 resource referencing SG, VPC, and subnet
        ec2_resource = Resource(
            arn=ec2_arn,
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={
                "security_groups": [sg_id],
                "vpc_id": vpc_id,
                "subnet_id": subnet_id,
            },
        )

        # Only provide the EC2 itself — targets are NOT in scan results
        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ec2_resource])

        # Build expected target ARNs
        expected_sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"
        expected_vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
        expected_subnet_arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"

        # All three relationships must be recorded even though targets are missing
        rel_target_arns = [r.target_arn for r in relationships]

        assert expected_sg_arn in rel_target_arns, (
            f"Relationship to SG '{expected_sg_arn}' should be preserved "
            f"even when target is not in scan results"
        )
        assert expected_vpc_arn in rel_target_arns, (
            f"Relationship to VPC '{expected_vpc_arn}' should be preserved "
            f"even when target is not in scan results"
        )
        assert expected_subnet_arn in rel_target_arns, (
            f"Relationship to subnet '{expected_subnet_arn}' should be preserved "
            f"even when target is not in scan results"
        )


# ---------------------------------------------------------------------------
# Property 11.2: Unresolved targets get is_unresolved=True
# ---------------------------------------------------------------------------

class TestUnresolvedTargetsMarkedUnresolved:
    """Targets NOT found in scan results get placeholder Resources with is_unresolved=True.

    **Validates: Requirements 4.7**
    """

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_id=sg_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_missing_target_gets_is_unresolved_true(
        self,
        account_id: str,
        region: str,
        instance_id: str,
        sg_id: str,
    ) -> None:
        """For any target ARN not in scan results, a placeholder with is_unresolved=True is created."""
        ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"

        ec2_resource = Resource(
            arn=ec2_arn,
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={"security_groups": [sg_id]},
        )

        resolver = RelationshipResolver(account_id)
        _, unresolved = resolver.resolve([ec2_resource])

        expected_sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"

        # Find the unresolved placeholder for the missing SG
        unresolved_sgs = [r for r in unresolved if r.arn == expected_sg_arn]

        assert len(unresolved_sgs) == 1, (
            f"Expected exactly one unresolved placeholder for '{expected_sg_arn}', "
            f"got {len(unresolved_sgs)}"
        )
        assert unresolved_sgs[0].is_unresolved is True, (
            f"Unresolved target must have is_unresolved=True"
        )


# ---------------------------------------------------------------------------
# Property 11.3: Resolved targets do NOT get is_unresolved
# ---------------------------------------------------------------------------

class TestResolvedTargetsNotMarkedUnresolved:
    """When the target IS present in scan results, no unresolved placeholder is created.

    **Validates: Requirements 4.7**
    """

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_id=sg_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_present_target_not_marked_unresolved(
        self,
        account_id: str,
        region: str,
        instance_id: str,
        sg_id: str,
    ) -> None:
        """For any target ARN present in scan results, no unresolved placeholder is created."""
        ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
        sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"

        # Create EC2 and the SG it references (both in scan results)
        ec2_resource = Resource(
            arn=ec2_arn,
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={"security_groups": [sg_id]},
        )
        sg_resource = Resource(
            arn=sg_arn,
            resource_type="security_group",
            name=f"sg-{sg_id}",
            region=region,
        )

        resolver = RelationshipResolver(account_id)
        relationships, unresolved = resolver.resolve([ec2_resource, sg_resource])

        # The SG should NOT appear in unresolved (it's in scan results)
        unresolved_arns = [r.arn for r in unresolved]

        assert sg_arn not in unresolved_arns, (
            f"Target '{sg_arn}' IS in scan results and should NOT "
            f"appear in unresolved list"
        )

        # But the relationship should still be recorded
        rel_target_arns = [r.target_arn for r in relationships]
        assert sg_arn in rel_target_arns, (
            f"Relationship to '{sg_arn}' should still be recorded"
        )


# ---------------------------------------------------------------------------
# Property 11.4: Multiple unresolved targets each get their own Resource
# ---------------------------------------------------------------------------

class TestMultipleUnresolvedTargets:
    """When multiple relationships reference different missing targets, each gets its own placeholder.

    **Validates: Requirements 4.7**
    """

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        sg_id=sg_id_strategy,
        vpc_id=vpc_id_strategy,
        subnet_id=subnet_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_each_missing_target_gets_own_unresolved_resource(
        self,
        account_id: str,
        region: str,
        instance_id: str,
        sg_id: str,
        vpc_id: str,
        subnet_id: str,
    ) -> None:
        """For any set of distinct missing target ARNs, each gets its own unresolved Resource."""
        ec2_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"

        ec2_resource = Resource(
            arn=ec2_arn,
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            attributes={
                "security_groups": [sg_id],
                "vpc_id": vpc_id,
                "subnet_id": subnet_id,
            },
        )

        resolver = RelationshipResolver(account_id)
        _, unresolved = resolver.resolve([ec2_resource])

        expected_sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"
        expected_vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
        expected_subnet_arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"

        unresolved_arns = [r.arn for r in unresolved]

        # Each distinct missing target must have its own unresolved Resource
        assert expected_sg_arn in unresolved_arns, (
            f"Missing SG target should have its own unresolved Resource"
        )
        assert expected_vpc_arn in unresolved_arns, (
            f"Missing VPC target should have its own unresolved Resource"
        )
        assert expected_subnet_arn in unresolved_arns, (
            f"Missing subnet target should have its own unresolved Resource"
        )

        # All must have is_unresolved=True
        for r in unresolved:
            if r.arn in (expected_sg_arn, expected_vpc_arn, expected_subnet_arn):
                assert r.is_unresolved is True, (
                    f"Unresolved resource '{r.arn}' must have is_unresolved=True"
                )


# ---------------------------------------------------------------------------
# Property 11.5: Deduplication of unresolved targets
# ---------------------------------------------------------------------------

class TestUnresolvedTargetDeduplication:
    """Multiple relationships to the same missing target produce only ONE unresolved Resource.

    **Validates: Requirements 4.7**
    """

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        vpc_id=vpc_id_strategy,
        instance_id_1=instance_id_strategy,
        instance_id_2=instance_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_same_missing_target_from_multiple_sources_deduplicates(
        self,
        account_id: str,
        region: str,
        vpc_id: str,
        instance_id_1: str,
        instance_id_2: str,
    ) -> None:
        """When multiple resources reference the same missing target, only one placeholder is created."""
        # Ensure distinct instance IDs
        assume(instance_id_1 != instance_id_2)

        ec2_arn_1 = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id_1}"
        ec2_arn_2 = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id_2}"

        # Two EC2 instances both referencing the SAME VPC (which is not in scan)
        ec2_resource_1 = Resource(
            arn=ec2_arn_1,
            resource_type="ec2",
            name=f"instance-{instance_id_1}",
            region=region,
            attributes={"vpc_id": vpc_id},
        )
        ec2_resource_2 = Resource(
            arn=ec2_arn_2,
            resource_type="ec2",
            name=f"instance-{instance_id_2}",
            region=region,
            attributes={"vpc_id": vpc_id},
        )

        resolver = RelationshipResolver(account_id)
        relationships, unresolved = resolver.resolve([ec2_resource_1, ec2_resource_2])

        expected_vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"

        # Both relationships should exist
        vpc_relationships = [r for r in relationships if r.target_arn == expected_vpc_arn]
        assert len(vpc_relationships) == 2, (
            f"Expected 2 relationships to VPC '{expected_vpc_arn}', "
            f"got {len(vpc_relationships)}"
        )

        # But only ONE unresolved placeholder should be created (deduplication)
        unresolved_vpcs = [r for r in unresolved if r.arn == expected_vpc_arn]
        assert len(unresolved_vpcs) == 1, (
            f"Expected exactly 1 unresolved placeholder for VPC '{expected_vpc_arn}', "
            f"got {len(unresolved_vpcs)} (deduplication should prevent duplicates)"
        )
        assert unresolved_vpcs[0].is_unresolved is True, (
            f"Deduplicated unresolved VPC must have is_unresolved=True"
        )
