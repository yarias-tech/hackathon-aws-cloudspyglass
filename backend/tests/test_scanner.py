"""Unit tests for the Scanner service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from backend.models.resources import Resource
from backend.services.scanner import (
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    REGION_SCAN_TIMEOUT_SECONDS,
    Scanner,
    calculate_backoff_delay,
)


class TestCalculateBackoffDelay:
    """Tests for the exponential backoff calculation."""

    def test_first_retry(self):
        assert calculate_backoff_delay(1) == 1.0  # 2^0 = 1

    def test_second_retry(self):
        assert calculate_backoff_delay(2) == 2.0  # 2^1 = 2

    def test_third_retry(self):
        assert calculate_backoff_delay(3) == 4.0  # 2^2 = 4

    def test_fourth_retry(self):
        assert calculate_backoff_delay(4) == 8.0  # 2^3 = 8

    def test_fifth_retry(self):
        assert calculate_backoff_delay(5) == 16.0  # 2^4 = 16

    def test_sixth_retry_capped(self):
        # 2^5 = 32 > 30, so capped at 30
        assert calculate_backoff_delay(6) == MAX_BACKOFF_SECONDS

    def test_large_retry_capped(self):
        assert calculate_backoff_delay(10) == MAX_BACKOFF_SECONDS


class TestScannerInit:
    """Tests for Scanner initialization."""

    def test_scanner_requires_credential_manager(self):
        cred_mgr = MagicMock()
        scanner = Scanner(cred_mgr)
        assert scanner._credential_manager is cred_mgr


class TestScannerDiscoverRegions:
    """Tests for region discovery."""

    async def test_discover_enabled_regions(self):
        """Test that discover regions calls EC2 DescribeRegions."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            regions = await scanner._discover_enabled_regions()

            # moto returns a set of default regions
            assert isinstance(regions, list)
            assert len(regions) > 0
            assert "us-east-1" in regions


class TestScannerScan:
    """Tests for the main scan orchestration."""

    async def test_scan_with_specified_regions(self):
        """Test scan with explicit region list."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            result = await scanner.scan(regions=["us-east-1"])

            assert result.account_id is not None
            assert result.scan_timestamp is not None
            assert result.total_scan_duration_ms >= 0
            assert isinstance(result.resources, list)
            assert isinstance(result.failures, list)

    async def test_scan_discovers_regions_when_none_specified(self):
        """Test that scan discovers regions when none are provided."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            # Mock region discovery to avoid scanning all moto regions (too slow)
            scanner._discover_enabled_regions = AsyncMock(
                return_value=["us-east-1", "us-west-2"]
            )
            result = await scanner.scan(regions=None)

            assert result.account_id is not None
            assert len(result.scanned_regions) > 0

    async def test_scan_returns_ec2_instances(self):
        """Test that scan returns EC2 instances."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            ec2 = session.client("ec2", region_name="us-east-1")
            ec2.run_instances(
                ImageId="ami-12345678",
                MinCount=1,
                MaxCount=1,
                InstanceType="t3.micro",
                TagSpecifications=[{
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": "test-instance"}],
                }],
            )

            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            result = await scanner.scan(regions=["us-east-1"])

            ec2_resources = [r for r in result.resources if r.resource_type == "ec2"]
            assert len(ec2_resources) >= 1
            assert ec2_resources[0].name == "test-instance"
            assert ec2_resources[0].attributes.get("instance_type") == "t3.micro"

    async def test_scan_returns_s3_buckets(self):
        """Test that scan returns S3 buckets."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            s3 = session.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="test-bucket-123")

            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            result = await scanner.scan(regions=["us-east-1"])

            s3_resources = [r for r in result.resources if r.resource_type == "s3"]
            assert len(s3_resources) >= 1
            assert any(r.name == "test-bucket-123" for r in s3_resources)

    async def test_scan_returns_lambda_functions(self):
        """Test that scan returns Lambda functions."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            iam = session.client("iam")
            iam.create_role(
                RoleName="test-lambda-role",
                AssumeRolePolicyDocument="{}",
                Path="/",
            )

            lam = session.client("lambda", region_name="us-east-1")
            lam.create_function(
                FunctionName="test-function",
                Runtime="python3.12",
                Role="arn:aws:iam::123456789012:role/test-lambda-role",
                Handler="handler.handler",
                Code={"ZipFile": b"fake code"},
                MemorySize=256,
                Timeout=30,
            )

            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            result = await scanner.scan(regions=["us-east-1"])

            lambda_resources = [
                r for r in result.resources if r.resource_type == "lambda"
            ]
            assert len(lambda_resources) >= 1
            assert lambda_resources[0].name == "test-function"
            assert lambda_resources[0].attributes.get("runtime") == "python3.12"
            assert lambda_resources[0].iam_role is not None


class TestScannerResourceEnrichment:
    """Tests for resource enrichment with metadata."""

    async def test_ec2_enriched_with_tags(self):
        """Test that EC2 instances are enriched with tags."""
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            ec2 = session.client("ec2", region_name="us-east-1")
            ec2.run_instances(
                ImageId="ami-12345678",
                MinCount=1,
                MaxCount=1,
                InstanceType="t3.medium",
                TagSpecifications=[{
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": "web-server"},
                        {"Key": "Environment", "Value": "production"},
                    ],
                }],
            )

            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)
            result = await scanner.scan(regions=["us-east-1"])

            ec2_resources = [
                r for r in result.resources if r.resource_type == "ec2"
            ]
            assert len(ec2_resources) >= 1
            instance = ec2_resources[0]
            assert instance.tags.get("Name") == "web-server"
            assert instance.tags.get("Environment") == "production"
            assert instance.attributes.get("instance_type") == "t3.medium"
            assert instance.attributes.get("state") == "running"
