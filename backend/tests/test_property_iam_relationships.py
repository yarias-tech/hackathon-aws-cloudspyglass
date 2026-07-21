"""Property-based tests for IAM relationship detection.

**Validates: Requirements 4.2**

Property 8: IAM relationship detection
- For any set of resources containing Lambda functions, EC2 instances, or ECS services
  with IAM role associations, the RelationshipResolver SHALL produce a relationship
  record for each role attachment with category: "iam".
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

instance_id_strategy = hex_suffix.map(lambda s: f"i-{s}")

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(
    alphabet="0123456789", min_size=12, max_size=12
)

# IAM role name strategy
role_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
    min_size=3,
    max_size=20,
)

# Lambda function name strategy
func_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=12,
)

# ECS service name strategy
ecs_service_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=12,
)


# ---------------------------------------------------------------------------
# Helper: Build ARNs
# ---------------------------------------------------------------------------

def _ec2_arn(region: str, account_id: str, instance_id: str) -> str:
    return f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"


def _lambda_arn(region: str, account_id: str, func_name: str) -> str:
    return f"arn:aws:lambda:{region}:{account_id}:function:{func_name}"


def _ecs_arn(region: str, account_id: str, service_name: str) -> str:
    return f"arn:aws:ecs:{region}:{account_id}:service/{service_name}"


def _iam_role_arn(account_id: str, role_name: str) -> str:
    return f"arn:aws:iam::{account_id}:role/{role_name}"


# ---------------------------------------------------------------------------
# Property: EC2 → IAM Role relationships
# ---------------------------------------------------------------------------

class TestEC2ToIAMRole:
    """EC2 instances with iam_role produce IAM relationships."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        role_name=role_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ec2_to_iam_role_produces_iam_relationship(
        self, account_id: str, region: str, instance_id: str, role_name: str
    ) -> None:
        """For any EC2 with an iam_role, produces one IAM relationship with derived_from='IamInstanceProfile.Arn'."""
        role_arn = _iam_role_arn(account_id, role_name)

        ec2_resource = Resource(
            arn=_ec2_arn(region, account_id, instance_id),
            resource_type="ec2",
            name=f"instance-{instance_id}",
            region=region,
            iam_role=role_arn,
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ec2_resource])

        iam_rels = [
            r for r in relationships
            if r.source_arn == ec2_resource.arn
            and r.category == "iam"
            and r.derived_from == "IamInstanceProfile.Arn"
        ]

        assert len(iam_rels) == 1, f"Expected 1 IAM relationship, got {len(iam_rels)}"
        assert iam_rels[0].target_arn == role_arn


# ---------------------------------------------------------------------------
# Property: Lambda → IAM Role relationships
# ---------------------------------------------------------------------------

class TestLambdaToIAMRole:
    """Lambda functions with iam_role produce IAM relationships."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        func_name=func_name_strategy,
        role_name=role_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_lambda_to_iam_role_produces_iam_relationship(
        self, account_id: str, region: str, func_name: str, role_name: str
    ) -> None:
        """For any Lambda with an iam_role, produces one IAM relationship with derived_from='Role'."""
        role_arn = _iam_role_arn(account_id, role_name)

        lambda_resource = Resource(
            arn=_lambda_arn(region, account_id, func_name),
            resource_type="lambda",
            name=func_name,
            region=region,
            iam_role=role_arn,
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([lambda_resource])

        iam_rels = [
            r for r in relationships
            if r.source_arn == lambda_resource.arn
            and r.category == "iam"
            and r.derived_from == "Role"
        ]

        assert len(iam_rels) == 1, f"Expected 1 IAM relationship, got {len(iam_rels)}"
        assert iam_rels[0].target_arn == role_arn


# ---------------------------------------------------------------------------
# Property: ECS → IAM Role relationships (via iam_role field)
# ---------------------------------------------------------------------------

class TestECSToIAMRoleViaField:
    """ECS services with iam_role field produce IAM relationships."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        service_name=ecs_service_name_strategy,
        role_name=role_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ecs_to_iam_role_via_field_produces_iam_relationship(
        self, account_id: str, region: str, service_name: str, role_name: str
    ) -> None:
        """For any ECS with iam_role set, produces one IAM relationship with derived_from='TaskDefinition.TaskRoleArn'."""
        role_arn = _iam_role_arn(account_id, role_name)

        ecs_resource = Resource(
            arn=_ecs_arn(region, account_id, service_name),
            resource_type="ecs",
            name=service_name,
            region=region,
            iam_role=role_arn,
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ecs_resource])

        iam_rels = [
            r for r in relationships
            if r.source_arn == ecs_resource.arn
            and r.category == "iam"
            and r.derived_from == "TaskDefinition.TaskRoleArn"
        ]

        assert len(iam_rels) == 1, f"Expected 1 IAM relationship, got {len(iam_rels)}"
        assert iam_rels[0].target_arn == role_arn


# ---------------------------------------------------------------------------
# Property: ECS → IAM Role relationships (via task_role_arn attribute)
# ---------------------------------------------------------------------------

class TestECSToIAMRoleViaAttribute:
    """ECS services with task_role_arn attribute produce IAM relationships."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        service_name=ecs_service_name_strategy,
        role_name=role_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_ecs_to_iam_role_via_attribute_produces_iam_relationship(
        self, account_id: str, region: str, service_name: str, role_name: str
    ) -> None:
        """For any ECS with task_role_arn in attributes (no iam_role field), produces one IAM relationship."""
        role_arn = _iam_role_arn(account_id, role_name)

        ecs_resource = Resource(
            arn=_ecs_arn(region, account_id, service_name),
            resource_type="ecs",
            name=service_name,
            region=region,
            iam_role=None,
            attributes={"task_role_arn": role_arn},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([ecs_resource])

        iam_rels = [
            r for r in relationships
            if r.source_arn == ecs_resource.arn
            and r.category == "iam"
            and r.derived_from == "TaskDefinition.TaskRoleArn"
        ]

        assert len(iam_rels) == 1, f"Expected 1 IAM relationship, got {len(iam_rels)}"
        assert iam_rels[0].target_arn == role_arn


# ---------------------------------------------------------------------------
# Property: All IAM relationships have category="iam"
# ---------------------------------------------------------------------------

class TestAllIAMRelationshipsCategory:
    """All relationships from IAM role associations have category='iam'."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=instance_id_strategy,
        ec2_role_name=role_name_strategy,
        func_name=func_name_strategy,
        lambda_role_name=role_name_strategy,
        service_name=ecs_service_name_strategy,
        ecs_role_name=role_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_all_iam_derived_relationships_have_iam_category(
        self, account_id: str, region: str, instance_id: str,
        ec2_role_name: str, func_name: str, lambda_role_name: str,
        service_name: str, ecs_role_name: str,
    ) -> None:
        """For any mix of resources with IAM role associations, all IAM relationships have category='iam'."""
        ec2_role_arn = _iam_role_arn(account_id, ec2_role_name)
        lambda_role_arn = _iam_role_arn(account_id, lambda_role_name)
        ecs_role_arn = _iam_role_arn(account_id, ecs_role_name)

        resources = [
            Resource(
                arn=_ec2_arn(region, account_id, instance_id),
                resource_type="ec2",
                name=f"instance-{instance_id}",
                region=region,
                iam_role=ec2_role_arn,
            ),
            Resource(
                arn=_lambda_arn(region, account_id, func_name),
                resource_type="lambda",
                name=func_name,
                region=region,
                iam_role=lambda_role_arn,
            ),
            Resource(
                arn=_ecs_arn(region, account_id, service_name),
                resource_type="ecs",
                name=service_name,
                region=region,
                iam_role=ecs_role_arn,
            ),
        ]

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve(resources)

        # All relationships from IAM-type derived_from fields should be "iam"
        iam_derived_from_values = {
            "IamInstanceProfile.Arn",
            "Role",
            "TaskDefinition.TaskRoleArn",
        }

        for rel in relationships:
            if rel.derived_from in iam_derived_from_values:
                assert rel.category == "iam", (
                    f"Relationship with derived_from='{rel.derived_from}' "
                    f"has category='{rel.category}', expected 'iam'"
                )

        # Verify we got exactly 3 IAM relationships (one per resource)
        iam_rels = [r for r in relationships if r.category == "iam"]
        assert len(iam_rels) == 3, (
            f"Expected 3 IAM relationships (one per resource), got {len(iam_rels)}"
        )
