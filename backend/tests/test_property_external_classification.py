"""Property-based tests for external component classification.

**Validates: Requirements 4.5**

Property 10: External component classification
- For any ARN reference found in resource configurations, if the embedded Account_ID
  differs from the scanned account OR the referenced hostname does not match
  *.amazonaws.com, the system SHALL classify that target as an external component.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.models.resources import Resource
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

# Generate a different account ID (guaranteed different from the scanned account)
def different_account_id(scanned_account: str) -> st.SearchStrategy[str]:
    """Strategy that produces a 12-digit account ID different from the scanned one."""
    return account_id_strategy.filter(lambda a: a != scanned_account)


# AWS service names for ARN construction
aws_services = st.sampled_from(["ec2", "lambda", "s3", "rds", "iam", "sqs", "sns", "ecs"])

# Resource identifier suffix
resource_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=3,
    max_size=20,
)

# Non-AWS hostnames (should NOT end with .amazonaws.com)
non_aws_hostname_strategy = st.one_of(
    # Generic hostnames
    st.builds(
        lambda subdomain, domain, tld: f"{subdomain}.{domain}.{tld}",
        subdomain=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=2, max_size=10),
        domain=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=2, max_size=10),
        tld=st.sampled_from(["com", "org", "net", "io", "dev", "co"]),
    ),
    # IP-like hostnames
    st.builds(
        lambda a, b, c, d: f"{a}.{b}.{c}.{d}",
        a=st.integers(min_value=1, max_value=254).map(str),
        b=st.integers(min_value=0, max_value=255).map(str),
        c=st.integers(min_value=0, max_value=255).map(str),
        d=st.integers(min_value=1, max_value=254).map(str),
    ),
)

# AWS hostnames (should end with .amazonaws.com)
aws_hostname_strategy = st.builds(
    lambda service, region: f"{service}.{region}.amazonaws.com",
    service=st.sampled_from(["s3", "ec2", "sqs", "sns", "lambda", "rds"]),
    region=region_strategy,
)


# ---------------------------------------------------------------------------
# Helper: Build a cross-account ARN
# ---------------------------------------------------------------------------

def _build_cross_account_arn(
    service: str, region: str, foreign_account: str, resource_id: str
) -> str:
    """Build an ARN with a different account ID than the scanned account."""
    if service == "s3":
        return f"arn:aws:s3:::{resource_id}"
    elif service == "iam":
        return f"arn:aws:iam::{foreign_account}:role/{resource_id}"
    else:
        return f"arn:aws:{service}:{region}:{foreign_account}:{resource_id}"


def _build_same_account_arn(
    service: str, region: str, account_id: str, resource_id: str
) -> str:
    """Build an ARN with the same account ID as the scanned account."""
    if service == "s3":
        return f"arn:aws:s3:::{resource_id}"
    elif service == "iam":
        return f"arn:aws:iam::{account_id}:role/{resource_id}"
    else:
        return f"arn:aws:{service}:{region}:{account_id}:{resource_id}"


# ---------------------------------------------------------------------------
# Property: Cross-account ARNs are classified as external
# ---------------------------------------------------------------------------

class TestCrossAccountARNClassifiedExternal:
    """ARNs with a different account_id than the scanned account are external."""

    @given(
        scanned_account=account_id_strategy,
        region=region_strategy,
        service=aws_services,
        resource_id=resource_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_cross_account_arn_is_external(
        self, scanned_account: str, region: str, service: str, resource_id: str
    ) -> None:
        """For any ARN with an account_id different from scanned account, classify as external."""
        # Generate a foreign account that differs from scanned
        # Rotate last digit to guarantee difference
        last_digit = int(scanned_account[-1])
        foreign_last = str((last_digit + 1) % 10)
        foreign_account = scanned_account[:-1] + foreign_last

        cross_account_arn = _build_cross_account_arn(
            service, region, foreign_account, resource_id
        )

        # Skip S3 ARNs (they don't have account IDs embedded)
        assume(service != "s3")

        resolver = RelationshipResolver(scanned_account)
        result = resolver._classify_external(cross_account_arn)

        assert result is True, (
            f"ARN '{cross_account_arn}' with foreign account '{foreign_account}' "
            f"(scanned: '{scanned_account}') should be classified as external"
        )


# ---------------------------------------------------------------------------
# Property: Same-account ARNs are NOT classified as external
# ---------------------------------------------------------------------------

class TestSameAccountARNNotExternal:
    """ARNs with the same account_id as the scanned account are NOT external."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        service=aws_services,
        resource_id=resource_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_same_account_arn_is_not_external(
        self, account_id: str, region: str, service: str, resource_id: str
    ) -> None:
        """For any ARN with the same account_id as scanned account, classify as NOT external."""
        same_account_arn = _build_same_account_arn(
            service, region, account_id, resource_id
        )

        resolver = RelationshipResolver(account_id)
        result = resolver._classify_external(same_account_arn)

        assert result is False, (
            f"ARN '{same_account_arn}' with same account '{account_id}' "
            f"should NOT be classified as external"
        )


# ---------------------------------------------------------------------------
# Property: Non-AWS hostnames are classified as external
# ---------------------------------------------------------------------------

class TestNonAWSHostnameClassifiedExternal:
    """Hostnames that do NOT end with .amazonaws.com are classified as external."""

    @given(
        account_id=account_id_strategy,
        hostname=non_aws_hostname_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_non_aws_hostname_is_external(
        self, account_id: str, hostname: str
    ) -> None:
        """For any hostname not matching *.amazonaws.com, classify as external."""
        # Ensure our generated hostname doesn't accidentally end with amazonaws.com
        assume(not hostname.endswith(".amazonaws.com"))

        resolver = RelationshipResolver(account_id)
        result = resolver._classify_external(hostname)

        assert result is True, (
            f"Hostname '{hostname}' should be classified as external "
            f"(does not end with .amazonaws.com)"
        )


# ---------------------------------------------------------------------------
# Property: AWS hostnames are NOT classified as external
# ---------------------------------------------------------------------------

class TestAWSHostnameNotExternal:
    """Hostnames ending with .amazonaws.com are NOT classified as external."""

    @given(
        account_id=account_id_strategy,
        hostname=aws_hostname_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_aws_hostname_is_not_external(
        self, account_id: str, hostname: str
    ) -> None:
        """For any hostname matching *.amazonaws.com, classify as NOT external."""
        resolver = RelationshipResolver(account_id)
        result = resolver._classify_external(hostname)

        assert result is False, (
            f"Hostname '{hostname}' ending with .amazonaws.com should NOT be "
            f"classified as external"
        )


# ---------------------------------------------------------------------------
# Property: External targets produce is_external=True on unresolved resources
# ---------------------------------------------------------------------------

class TestExternalTargetProducesExternalResource:
    """When a relationship references a cross-account ARN, the unresolved resource is external."""

    @given(
        scanned_account=account_id_strategy,
        region=region_strategy,
        instance_id=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
    )
    @settings(max_examples=50, deadline=None)
    def test_cross_account_target_marked_external_in_unresolved(
        self, scanned_account: str, region: str, instance_id: str
    ) -> None:
        """Cross-account ARN targets produce unresolved resources with is_external=True."""
        # Create a foreign account by rotating last digit
        last_digit = int(scanned_account[-1])
        foreign_last = str((last_digit + 1) % 10)
        foreign_account = scanned_account[:-1] + foreign_last

        # Create an ALB that references a cross-account target
        cross_account_target = (
            f"arn:aws:ec2:{region}:{foreign_account}:instance/i-{instance_id}"
        )

        lb_resource = Resource(
            arn=f"arn:aws:elasticloadbalancing:{region}:{scanned_account}:loadbalancer/app/my-lb/abc123",
            resource_type="alb",
            name="my-lb",
            region=region,
            attributes={"target_arns": [cross_account_target]},
        )

        resolver = RelationshipResolver(scanned_account)
        relationships, unresolved = resolver.resolve([lb_resource])

        # The cross-account target should appear in unresolved with is_external=True
        external_unresolved = [
            r for r in unresolved
            if r.arn == cross_account_target
        ]

        assert len(external_unresolved) == 1, (
            f"Expected cross-account target '{cross_account_target}' in unresolved list"
        )
        assert external_unresolved[0].is_external is True, (
            f"Cross-account target should have is_external=True"
        )
        assert external_unresolved[0].is_unresolved is True, (
            f"Cross-account target should have is_unresolved=True"
        )


# ---------------------------------------------------------------------------
# Property: Same-account unresolved targets are NOT external
# ---------------------------------------------------------------------------

class TestSameAccountUnresolvedNotExternal:
    """When a relationship references a same-account ARN not in scan, it's unresolved but NOT external."""

    @given(
        account_id=account_id_strategy,
        region=region_strategy,
        instance_id=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
        sg_id=st.text(alphabet="0123456789abcdef", min_size=8, max_size=17),
    )
    @settings(max_examples=50, deadline=None)
    def test_same_account_unresolved_not_external(
        self, account_id: str, region: str, instance_id: str, sg_id: str
    ) -> None:
        """Same-account unresolved ARN targets are NOT marked as external."""
        # EC2 referencing a security group not in the scan
        ec2_resource = Resource(
            arn=f"arn:aws:ec2:{region}:{account_id}:instance/i-{instance_id}",
            resource_type="ec2",
            name=f"instance-i-{instance_id}",
            region=region,
            attributes={"security_groups": [f"sg-{sg_id}"]},
        )

        resolver = RelationshipResolver(account_id)
        _, unresolved = resolver.resolve([ec2_resource])

        expected_sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/sg-{sg_id}"
        same_account_unresolved = [
            r for r in unresolved
            if r.arn == expected_sg_arn
        ]

        assert len(same_account_unresolved) == 1, (
            f"Expected same-account SG target '{expected_sg_arn}' in unresolved list"
        )
        assert same_account_unresolved[0].is_external is False, (
            f"Same-account unresolved target should have is_external=False"
        )
        assert same_account_unresolved[0].is_unresolved is True, (
            f"Same-account unresolved target should have is_unresolved=True"
        )
