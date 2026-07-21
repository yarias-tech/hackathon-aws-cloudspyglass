"""Property-based tests for event relationship detection.

**Validates: Requirements 4.3**

Property 9: Event relationship detection
- For any set of resources containing SQS queues with event_source_targets,
  SNS topics with subscription_endpoints, or S3 buckets with notification_targets,
  the RelationshipResolver SHALL produce a relationship record for each event
  connection with category: "event" and the correct derived_from property name.
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

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(
    alphabet="0123456789", min_size=12, max_size=12
)

# Lambda function name strategy
func_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=12,
)

# SQS queue name strategy
queue_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=12,
)

# SNS topic name strategy
topic_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=12,
)

# S3 bucket name strategy
bucket_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=3,
    max_size=12,
)


# ---------------------------------------------------------------------------
# Helper: Build ARNs
# ---------------------------------------------------------------------------

def _sqs_arn(region: str, account_id: str, queue_name: str) -> str:
    return f"arn:aws:sqs:{region}:{account_id}:{queue_name}"


def _sns_arn(region: str, account_id: str, topic_name: str) -> str:
    return f"arn:aws:sns:{region}:{account_id}:{topic_name}"


def _s3_arn(bucket_name: str) -> str:
    return f"arn:aws:s3:::{bucket_name}"


def _lambda_arn(region: str, account_id: str, func_name: str) -> str:
    return f"arn:aws:lambda:{region}:{account_id}:function:{func_name}"


# ---------------------------------------------------------------------------
# Target ARN strategies
# ---------------------------------------------------------------------------

# Lambda ARN targets for SQS/SNS event sources
lambda_target_arn_strategy = st.builds(
    _lambda_arn,
    region=region_strategy,
    account_id=account_id_strategy,
    func_name=func_name_strategy,
)

lambda_target_arns_strategy = st.lists(
    lambda_target_arn_strategy, min_size=1, max_size=3, unique=True
)

# Mixed targets for S3 notifications (Lambda, SQS, SNS)
s3_notification_target_strategy = st.one_of(
    # Lambda target
    st.builds(
        _lambda_arn,
        region=region_strategy,
        account_id=account_id_strategy,
        func_name=func_name_strategy,
    ),
    # SQS target
    st.builds(
        _sqs_arn,
        region=region_strategy,
        account_id=account_id_strategy,
        queue_name=queue_name_strategy,
    ),
    # SNS target
    st.builds(
        _sns_arn,
        region=region_strategy,
        account_id=account_id_strategy,
        topic_name=topic_name_strategy,
    ),
)

s3_notification_targets_strategy = st.lists(
    s3_notification_target_strategy, min_size=1, max_size=4, unique=True
)


# ---------------------------------------------------------------------------
# Property: SQS → Lambda relationships
# ---------------------------------------------------------------------------

class TestSQSToLambda:
    """SQS queues with event_source_targets produce event relationships to Lambda."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        queue_name=queue_name_strategy,
        target_arns=lambda_target_arns_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_sqs_to_lambda_produces_event_relationships(
        self, account_id: str, region: str, queue_name: str, target_arns: list[str]
    ) -> None:
        """For any SQS with event_source_targets, produces one event relationship per target with derived_from='EventSourceMappings[].EventSourceArn'."""
        sqs_resource = Resource(
            arn=_sqs_arn(region, account_id, queue_name),
            resource_type="sqs",
            name=queue_name,
            region=region,
            attributes={"event_source_targets": target_arns},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([sqs_resource])

        event_rels = [
            r for r in relationships
            if r.source_arn == sqs_resource.arn
            and r.category == "event"
            and r.derived_from == "EventSourceMappings[].EventSourceArn"
        ]

        assert len(event_rels) == len(target_arns), (
            f"Expected {len(target_arns)} event relationships, got {len(event_rels)}"
        )

        for target_arn in target_arns:
            matching = [r for r in event_rels if r.target_arn == target_arn]
            assert len(matching) == 1, (
                f"Expected relationship to {target_arn}, not found"
            )


# ---------------------------------------------------------------------------
# Property: SNS → Lambda relationships
# ---------------------------------------------------------------------------

class TestSNSToLambda:
    """SNS topics with subscription_endpoints produce event relationships to Lambda."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        topic_name=topic_name_strategy,
        endpoint_arns=lambda_target_arns_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_sns_to_lambda_produces_event_relationships(
        self, account_id: str, region: str, topic_name: str, endpoint_arns: list[str]
    ) -> None:
        """For any SNS with subscription_endpoints, produces one event relationship per endpoint with derived_from='Subscriptions[].Endpoint'."""
        sns_resource = Resource(
            arn=_sns_arn(region, account_id, topic_name),
            resource_type="sns",
            name=topic_name,
            region=region,
            attributes={"subscription_endpoints": endpoint_arns},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([sns_resource])

        event_rels = [
            r for r in relationships
            if r.source_arn == sns_resource.arn
            and r.category == "event"
            and r.derived_from == "Subscriptions[].Endpoint"
        ]

        assert len(event_rels) == len(endpoint_arns), (
            f"Expected {len(endpoint_arns)} event relationships, got {len(event_rels)}"
        )

        for endpoint_arn in endpoint_arns:
            matching = [r for r in event_rels if r.target_arn == endpoint_arn]
            assert len(matching) == 1, (
                f"Expected relationship to {endpoint_arn}, not found"
            )


# ---------------------------------------------------------------------------
# Property: S3 → Lambda/SQS/SNS relationships
# ---------------------------------------------------------------------------

class TestS3ToNotificationTargets:
    """S3 buckets with notification_targets produce event relationships to Lambda/SQS/SNS."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        bucket_name=bucket_name_strategy,
        notification_targets=s3_notification_targets_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_s3_to_targets_produces_event_relationships(
        self, account_id: str, region: str, bucket_name: str,
        notification_targets: list[str]
    ) -> None:
        """For any S3 with notification_targets, produces one event relationship per target with derived_from='NotificationConfiguration'."""
        s3_resource = Resource(
            arn=_s3_arn(bucket_name),
            resource_type="s3",
            name=bucket_name,
            region=region,
            attributes={"notification_targets": notification_targets},
        )

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve([s3_resource])

        event_rels = [
            r for r in relationships
            if r.source_arn == s3_resource.arn
            and r.category == "event"
            and r.derived_from == "NotificationConfiguration"
        ]

        assert len(event_rels) == len(notification_targets), (
            f"Expected {len(notification_targets)} event relationships, got {len(event_rels)}"
        )

        for target_arn in notification_targets:
            matching = [r for r in event_rels if r.target_arn == target_arn]
            assert len(matching) == 1, (
                f"Expected relationship to {target_arn}, not found"
            )


# ---------------------------------------------------------------------------
# Property: All event relationships have category="event"
# ---------------------------------------------------------------------------

class TestAllEventRelationshipsCategory:
    """All relationships from event source attributes have category='event'."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        queue_name=queue_name_strategy,
        sqs_targets=lambda_target_arns_strategy,
        topic_name=topic_name_strategy,
        sns_endpoints=lambda_target_arns_strategy,
        bucket_name=bucket_name_strategy,
        s3_targets=s3_notification_targets_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_all_event_derived_relationships_have_event_category(
        self, account_id: str, region: str,
        queue_name: str, sqs_targets: list[str],
        topic_name: str, sns_endpoints: list[str],
        bucket_name: str, s3_targets: list[str],
    ) -> None:
        """For any mix of event-source resources, all event relationships have category='event'."""
        resources = [
            Resource(
                arn=_sqs_arn(region, account_id, queue_name),
                resource_type="sqs",
                name=queue_name,
                region=region,
                attributes={"event_source_targets": sqs_targets},
            ),
            Resource(
                arn=_sns_arn(region, account_id, topic_name),
                resource_type="sns",
                name=topic_name,
                region=region,
                attributes={"subscription_endpoints": sns_endpoints},
            ),
            Resource(
                arn=_s3_arn(bucket_name),
                resource_type="s3",
                name=bucket_name,
                region=region,
                attributes={"notification_targets": s3_targets},
            ),
        ]

        resolver = RelationshipResolver(account_id)
        relationships, _ = resolver.resolve(resources)

        # All relationships from event-type derived_from fields should be "event"
        event_derived_from_values = {
            "EventSourceMappings[].EventSourceArn",
            "Subscriptions[].Endpoint",
            "NotificationConfiguration",
        }

        for rel in relationships:
            if rel.derived_from in event_derived_from_values:
                assert rel.category == "event", (
                    f"Relationship with derived_from='{rel.derived_from}' "
                    f"has category='{rel.category}', expected 'event'"
                )

        # Verify we got at least one event relationship per resource type
        sqs_rels = [r for r in relationships if r.derived_from == "EventSourceMappings[].EventSourceArn"]
        sns_rels = [r for r in relationships if r.derived_from == "Subscriptions[].Endpoint"]
        s3_rels = [r for r in relationships if r.derived_from == "NotificationConfiguration"]

        assert len(sqs_rels) == len(sqs_targets), (
            f"Expected {len(sqs_targets)} SQS event relationships, got {len(sqs_rels)}"
        )
        assert len(sns_rels) == len(sns_endpoints), (
            f"Expected {len(sns_endpoints)} SNS event relationships, got {len(sns_rels)}"
        )
        assert len(s3_rels) == len(s3_targets), (
            f"Expected {len(s3_targets)} S3 event relationships, got {len(s3_rels)}"
        )
