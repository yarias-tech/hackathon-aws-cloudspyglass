"""Multi-region AWS resource scanner with exponential backoff and timeout handling."""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from ..exceptions import CloudSpyglassError
from ..models.resources import Resource
from ..models.scan import RegionFailure, ScanResult

logger = logging.getLogger(__name__)

# Constants
TOTAL_SCAN_TIMEOUT_SECONDS = 1800  # 30 minutes
REGION_SCAN_TIMEOUT_SECONDS = 360  # 360 seconds per region
MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 30

# Global resource types (scanned once, not per-region)
GLOBAL_RESOURCE_TYPES = ["s3", "iam_role", "cloudfront", "route53", "ecr"]

# Regional resource types (scanned per region)
REGIONAL_RESOURCE_TYPES = [
    "ec2", "security_group", "vpc", "subnet", "lambda", "rds",
    "alb", "nlb", "ecs", "sns", "sqs", "dynamodb", "api_gateway",
    "eks", "elasticache", "ebs", "elastic_ip", "nat_gateway",
    "transit_gateway", "vpn_gateway", "step_functions", "kinesis",
    "secrets_manager", "redshift", "opensearch", "codepipeline", "glue",
]

ALL_RESOURCE_TYPES = REGIONAL_RESOURCE_TYPES + GLOBAL_RESOURCE_TYPES


def calculate_backoff_delay(retry_number: int) -> float:
    """Calculate exponential backoff delay: min(2^(n-1), 30) seconds.

    Args:
        retry_number: The retry attempt number (1-based, 1 through MAX_RETRIES).

    Returns:
        Delay in seconds before the next retry.
    """
    return min(2 ** (retry_number - 1), MAX_BACKOFF_SECONDS)


class Scanner:
    """Multi-region AWS resource scanner with exponential backoff."""

    def __init__(self, credential_manager) -> None:
        """Initialize the Scanner with a CredentialManager dependency.

        Args:
            credential_manager: CredentialManager instance for obtaining boto3 sessions.
        """
        self._credential_manager = credential_manager

    async def scan(self, regions: list[str] | None = None) -> ScanResult:
        """Orchestrate multi-region parallel scanning.

        Args:
            regions: Optional list of region codes. If None/empty, discovers all enabled regions.

        Returns:
            ScanResult with resources, failures, and metadata.
        """
        start_time = time.time()

        # Validate credentials first
        session = await self._credential_manager.get_boto3_session()
        account_id = await self._get_account_id(session)

        # Determine regions to scan
        if not regions:
            regions = await self._discover_enabled_regions()

        all_resources: list[Resource] = []
        all_failures: list[RegionFailure] = []
        scanned_regions: list[str] = []

        # Scan global resources once (from the session's default region)
        global_resources, global_failures = await self._scan_global_resources(
            session, account_id
        )
        all_resources.extend(global_resources)
        all_failures.extend(global_failures)

        # Parallel scan of regional resources with total timeout
        # Limit concurrency to avoid throttling — scan 5 regions at a time
        try:
            for batch_start in range(0, len(regions), 5):
                batch_regions = regions[batch_start:batch_start + 5]
                region_tasks = [
                    self._scan_region(region, account_id)
                    for region in batch_regions
                ]

                # Check if we've exceeded total timeout
                elapsed = time.time() - start_time
                remaining = TOTAL_SCAN_TIMEOUT_SECONDS - elapsed
                if remaining <= 0:
                    for region in regions[batch_start:]:
                        all_failures.append(RegionFailure(
                            region=region,
                            resource_type="all",
                            error_message="Scan cancelled: total 10-minute timeout reached",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ))
                    break

                results = await asyncio.wait_for(
                    asyncio.gather(*region_tasks, return_exceptions=True),
                    timeout=remaining,
                )

                for i, result in enumerate(results):
                    region = batch_regions[i]
                    if isinstance(result, Exception):
                        all_failures.append(RegionFailure(
                            region=region,
                            resource_type="all",
                            error_message=str(result),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ))
                    else:
                        resources, failures = result
                        all_resources.extend(resources)
                        all_failures.extend(failures)
                        scanned_regions.append(region)

        except asyncio.TimeoutError:
            # Total timeout reached — return what we have
            logger.warning("Total scan timeout reached (10 minutes)")
            for region in regions:
                if region not in scanned_regions:
                    all_failures.append(RegionFailure(
                        region=region,
                        resource_type="all",
                        error_message="Scan cancelled: total 10-minute timeout reached",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))

        elapsed_ms = int((time.time() - start_time) * 1000)

        return ScanResult(
            account_id=account_id,
            scan_timestamp=datetime.now(timezone.utc).isoformat(),
            resources=all_resources,
            relationships=[],  # Resolved separately by RelationshipResolver
            failures=all_failures,
            scanned_regions=scanned_regions,
            total_scan_duration_ms=elapsed_ms,
        )

    async def _scan_region(
        self, region: str, account_id: str
    ) -> tuple[list[Resource], list[RegionFailure]]:
        """Scan all regional resource types in a single region with 60s timeout.

        Args:
            region: AWS region code.
            account_id: The AWS account ID.

        Returns:
            Tuple of (resources, failures) for this region.
        """
        resources: list[Resource] = []
        failures: list[RegionFailure] = []

        try:
            session = await self._credential_manager.get_boto3_session()
            # Create a regional session
            regional_session = boto3.Session(
                aws_access_key_id=session.get_credentials().access_key,
                aws_secret_access_key=session.get_credentials().secret_key,
                aws_session_token=session.get_credentials().token,
                region_name=region,
            )

            async def scan_with_timeout():
                tasks = [
                    self._scan_resource_type(regional_session, region, rt, account_id)
                    for rt in REGIONAL_RESOURCE_TYPES
                ]
                return await asyncio.gather(*tasks, return_exceptions=True)

            results = await asyncio.wait_for(
                scan_with_timeout(),
                timeout=REGION_SCAN_TIMEOUT_SECONDS,
            )

            for i, result in enumerate(results):
                rt = REGIONAL_RESOURCE_TYPES[i]
                if isinstance(result, Exception):
                    failures.append(RegionFailure(
                        region=region,
                        resource_type=rt,
                        error_message=str(result),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))
                else:
                    resources.extend(result)

        except asyncio.TimeoutError:
            failures.append(RegionFailure(
                region=region,
                resource_type="all",
                error_message=f"Region scan timed out after {REGION_SCAN_TIMEOUT_SECONDS}s",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
        except Exception as exc:
            failures.append(RegionFailure(
                region=region,
                resource_type="all",
                error_message=str(exc),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        return resources, failures

    async def _scan_global_resources(
        self, session: boto3.Session, account_id: str
    ) -> tuple[list[Resource], list[RegionFailure]]:
        """Scan global resource types (S3, IAM, CloudFront, Route53).

        These are scanned once (not per-region).
        """
        resources: list[Resource] = []
        failures: list[RegionFailure] = []

        for rt in GLOBAL_RESOURCE_TYPES:
            try:
                result = await self._scan_resource_type(
                    session, "global", rt, account_id
                )
                resources.extend(result)
            except Exception as exc:
                failures.append(RegionFailure(
                    region="global",
                    resource_type=rt,
                    error_message=str(exc),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

        return resources, failures

    async def _scan_resource_type(
        self, session: boto3.Session, region: str, resource_type: str, account_id: str
    ) -> list[Resource]:
        """Scan a single resource type with exponential backoff retry.

        Args:
            session: boto3 Session configured for the target region.
            region: AWS region code or 'global'.
            resource_type: The resource type identifier.
            account_id: The AWS account ID.

        Returns:
            List of discovered Resource objects.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await self._fetch_resources(
                    session, region, resource_type, account_id
                )
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in ("Throttling", "RequestLimitExceeded", "TooManyRequestsException"):
                    last_error = exc
                    if attempt < MAX_RETRIES + 1:
                        delay = calculate_backoff_delay(attempt)
                        logger.warning(
                            "Throttled on %s/%s (attempt %d), retrying in %.1fs",
                            region, resource_type, attempt, delay,
                        )
                        await asyncio.sleep(delay)
                else:
                    raise
            except Exception:
                raise

        # All retries exhausted
        raise last_error or CloudSpyglassError(
            error_code="AWS_THROTTLED",
            message=f"Max retries exhausted for {resource_type} in {region}",
            recoverable=True,
            status_code=429,
        )

    async def _fetch_resources(
        self, session: boto3.Session, region: str, resource_type: str, account_id: str
    ) -> list[Resource]:
        """Dispatch to the appropriate resource-type fetcher.

        Uses run_in_executor for blocking boto3 calls.
        """
        loop = asyncio.get_event_loop()
        fetcher = self._get_fetcher(resource_type)
        return await loop.run_in_executor(
            None, fetcher, session, region, account_id
        )

    def _get_fetcher(self, resource_type: str):
        """Return the fetcher function for a given resource type."""
        fetchers = {
            "ec2": self._fetch_ec2,
            "security_group": self._fetch_security_groups,
            "vpc": self._fetch_vpcs,
            "subnet": self._fetch_subnets,
            "s3": self._fetch_s3,
            "lambda": self._fetch_lambda,
            "rds": self._fetch_rds,
            "iam_role": self._fetch_iam_roles,
            "alb": self._fetch_alb,
            "nlb": self._fetch_nlb,
            "ecs": self._fetch_ecs,
            "sns": self._fetch_sns,
            "sqs": self._fetch_sqs,
            "dynamodb": self._fetch_dynamodb,
            "cloudfront": self._fetch_cloudfront,
            "route53": self._fetch_route53,
            "api_gateway": self._fetch_api_gateway,
            "eks": self._fetch_eks,
            "elasticache": self._fetch_elasticache,
            "ebs": self._fetch_ebs,
            "elastic_ip": self._fetch_elastic_ips,
            "nat_gateway": self._fetch_nat_gateways,
            "transit_gateway": self._fetch_transit_gateways,
            "vpn_gateway": self._fetch_vpn_gateways,
            "step_functions": self._fetch_step_functions,
            "kinesis": self._fetch_kinesis,
            "secrets_manager": self._fetch_secrets_manager,
            "ecr": self._fetch_ecr,
            "redshift": self._fetch_redshift,
            "opensearch": self._fetch_opensearch,
            "codepipeline": self._fetch_codepipeline,
            "glue": self._fetch_glue,
        }
        return fetchers[resource_type]

    async def _discover_enabled_regions(self) -> list[str]:
        """Discover all enabled regions via EC2 DescribeRegions API."""
        session = await self._credential_manager.get_boto3_session()
        loop = asyncio.get_event_loop()

        def _describe_regions():
            ec2 = session.client("ec2")
            response = ec2.describe_regions(
                Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
            )
            return [r["RegionName"] for r in response.get("Regions", [])]

        return await loop.run_in_executor(None, _describe_regions)

    async def _get_account_id(self, session: boto3.Session) -> str:
        """Get the AWS account ID from STS."""
        loop = asyncio.get_event_loop()

        def _get_identity():
            sts = session.client("sts")
            return sts.get_caller_identity()["Account"]

        return await loop.run_in_executor(None, _get_identity)

    # ------------------------------------------------------------------
    # Resource Fetchers — each returns list[Resource]
    # ------------------------------------------------------------------

    def _extract_tags(self, tag_list: list[dict] | None) -> dict[str, str]:
        """Convert AWS tag list format to a simple dict."""
        if not tag_list:
            return {}
        return {t.get("Key", ""): t.get("Value", "") for t in tag_list}

    def _get_name_from_tags(self, tags: dict[str, str], fallback: str = "") -> str:
        """Extract Name tag value, falling back to provided default."""
        return tags.get("Name", fallback)

    def _fetch_ec2(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch EC2 instances."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []
        paginator = ec2.get_paginator("describe_instances")

        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance["InstanceId"]
                    tags = self._extract_tags(instance.get("Tags"))
                    name = self._get_name_from_tags(tags, instance_id)

                    iam_role = None
                    iam_profile = instance.get("IamInstanceProfile")
                    if iam_profile:
                        iam_role = iam_profile.get("Arn")

                    resources.append(Resource(
                        arn=f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
                        resource_type="ec2",
                        name=name,
                        region=region,
                        tags=tags,
                        creation_date=instance.get("LaunchTime", "").isoformat()
                            if instance.get("LaunchTime") else None,
                        iam_role=iam_role,
                        attributes={
                            "instance_type": instance.get("InstanceType"),
                            "state": instance.get("State", {}).get("Name"),
                            "vpc_id": instance.get("VpcId"),
                            "subnet_id": instance.get("SubnetId"),
                            "security_groups": [
                                sg["GroupId"]
                                for sg in instance.get("SecurityGroups", [])
                            ],
                            "private_ip": instance.get("PrivateIpAddress"),
                            "public_ip": instance.get("PublicIpAddress"),
                        },
                    ))

        return resources

    def _fetch_security_groups(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Security Groups."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []
        paginator = ec2.get_paginator("describe_security_groups")

        for page in paginator.paginate():
            for sg in page.get("SecurityGroups", []):
                sg_id = sg["GroupId"]
                tags = self._extract_tags(sg.get("Tags"))
                name = self._get_name_from_tags(tags, sg.get("GroupName", sg_id))

                resources.append(Resource(
                    arn=f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}",
                    resource_type="security_group",
                    name=name,
                    region=region,
                    tags=tags,
                    attributes={
                        "group_name": sg.get("GroupName"),
                        "vpc_id": sg.get("VpcId"),
                        "description": sg.get("Description"),
                        "ingress_rules_count": len(sg.get("IpPermissions", [])),
                        "egress_rules_count": len(sg.get("IpPermissionsEgress", [])),
                    },
                ))

        return resources

    def _fetch_vpcs(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch VPCs."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        response = ec2.describe_vpcs()
        for vpc in response.get("Vpcs", []):
            vpc_id = vpc["VpcId"]
            tags = self._extract_tags(vpc.get("Tags"))
            name = self._get_name_from_tags(tags, vpc_id)

            resources.append(Resource(
                arn=f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}",
                resource_type="vpc",
                name=name,
                region=region,
                tags=tags,
                attributes={
                    "cidr_block": vpc.get("CidrBlock"),
                    "state": vpc.get("State"),
                    "is_default": vpc.get("IsDefault", False),
                },
            ))

        return resources

    def _fetch_subnets(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Subnets."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        response = ec2.describe_subnets()
        for subnet in response.get("Subnets", []):
            subnet_id = subnet["SubnetId"]
            tags = self._extract_tags(subnet.get("Tags"))
            name = self._get_name_from_tags(tags, subnet_id)

            resources.append(Resource(
                arn=f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}",
                resource_type="subnet",
                name=name,
                region=region,
                tags=tags,
                attributes={
                    "vpc_id": subnet.get("VpcId"),
                    "cidr_block": subnet.get("CidrBlock"),
                    "availability_zone": subnet.get("AvailabilityZone"),
                    "available_ips": subnet.get("AvailableIpAddressCount"),
                },
            ))

        return resources

    def _fetch_s3(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch S3 buckets (global resource)."""
        s3 = session.client("s3")
        resources: list[Resource] = []

        response = s3.list_buckets()
        for bucket in response.get("Buckets", []):
            bucket_name = bucket["Name"]
            creation_date = bucket.get("CreationDate")

            # Try to get bucket location
            try:
                loc_resp = s3.get_bucket_location(Bucket=bucket_name)
                bucket_region = loc_resp.get("LocationConstraint") or "us-east-1"
            except ClientError:
                bucket_region = "unknown"

            # Try to get bucket tags
            tags = {}
            try:
                tag_resp = s3.get_bucket_tagging(Bucket=bucket_name)
                tags = self._extract_tags(tag_resp.get("TagSet"))
            except ClientError:
                pass  # No tags or access denied

            # Get notification configuration targets
            notification_targets: list[str] = []
            try:
                notif_resp = s3.get_bucket_notification_configuration(Bucket=bucket_name)
                # Lambda function configurations
                for config in notif_resp.get("LambdaFunctionConfigurations", []):
                    arn = config.get("LambdaFunctionArn")
                    if arn:
                        notification_targets.append(arn)
                # SQS queue configurations
                for config in notif_resp.get("QueueConfigurations", []):
                    arn = config.get("QueueArn")
                    if arn:
                        notification_targets.append(arn)
                # SNS topic configurations
                for config in notif_resp.get("TopicConfigurations", []):
                    arn = config.get("TopicArn")
                    if arn:
                        notification_targets.append(arn)
            except ClientError:
                pass

            # Get replication configuration targets
            replication_targets: list[str] = []
            try:
                repl_resp = s3.get_bucket_replication(Bucket=bucket_name)
                rules = repl_resp.get("ReplicationConfiguration", {}).get("Rules", [])
                for rule in rules:
                    dest_bucket = rule.get("Destination", {}).get("Bucket")
                    if dest_bucket:
                        replication_targets.append(dest_bucket)
            except ClientError:
                pass  # No replication or access denied

            resources.append(Resource(
                arn=f"arn:aws:s3:::{bucket_name}",
                resource_type="s3",
                name=bucket_name,
                region=bucket_region,
                tags=tags,
                creation_date=creation_date.isoformat() if creation_date else None,
                attributes={
                    "bucket_name": bucket_name,
                    "notification_targets": notification_targets,
                    "replication_targets": replication_targets,
                },
            ))

        return resources

    def _fetch_lambda(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Lambda functions."""
        client = session.client("lambda", region_name=region)
        resources: list[Resource] = []
        paginator = client.get_paginator("list_functions")

        for page in paginator.paginate():
            for func in page.get("Functions", []):
                func_name = func["FunctionName"]
                func_arn = func["FunctionArn"]

                # Get tags
                tags = {}
                try:
                    tag_resp = client.list_tags(Resource=func_arn)
                    tags = tag_resp.get("Tags", {})
                except ClientError:
                    pass

                # VPC config
                vpc_config = func.get("VpcConfig", {})

                # Collect event source mappings for this function
                event_source_arns: list[str] = []
                try:
                    esm_paginator = client.get_paginator("list_event_source_mappings")
                    for esm_page in esm_paginator.paginate(FunctionName=func_arn):
                        for mapping in esm_page.get("EventSourceMappings", []):
                            source_arn = mapping.get("EventSourceArn")
                            if source_arn:
                                event_source_arns.append(source_arn)
                except ClientError:
                    pass

                # Extract ARNs from environment variables
                environment_resource_arns: list[str] = []
                env_vars = func.get("Environment", {}).get("Variables", {})
                arn_pattern = re.compile(r"arn:aws[a-zA-Z-]*:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:\d{12}:[^\s,\"']+")
                for value in env_vars.values():
                    if isinstance(value, str):
                        found = arn_pattern.findall(value)
                        environment_resource_arns.extend(found)

                resources.append(Resource(
                    arn=func_arn,
                    resource_type="lambda",
                    name=func_name,
                    region=region,
                    tags=tags,
                    creation_date=func.get("LastModified"),
                    iam_role=func.get("Role"),
                    attributes={
                        "runtime": func.get("Runtime"),
                        "handler": func.get("Handler"),
                        "memory_size": func.get("MemorySize"),
                        "timeout": func.get("Timeout"),
                        "vpc_id": vpc_config.get("VpcId"),
                        "subnet_ids": vpc_config.get("SubnetIds", []),
                        "security_group_ids": vpc_config.get("SecurityGroupIds", []),
                        "event_source_arns": event_source_arns,
                        "environment_resource_arns": environment_resource_arns,
                    },
                ))

        return resources

    def _fetch_rds(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch RDS instances and clusters."""
        rds = session.client("rds", region_name=region)
        resources: list[Resource] = []

        # Fetch DB instances
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                db_id = db["DBInstanceIdentifier"]
                db_arn = db["DBInstanceArn"]

                # Get tags
                tags = {}
                try:
                    tag_resp = rds.list_tags_for_resource(ResourceName=db_arn)
                    tags = self._extract_tags(tag_resp.get("TagList"))
                except ClientError:
                    pass

                subnet_group = db.get("DBSubnetGroup", {})

                # Collect security group IDs
                security_group_ids = [
                    sg["VpcSecurityGroupId"]
                    for sg in db.get("VpcSecurityGroups", [])
                    if sg.get("Status") == "active"
                ]

                # Collect subnet IDs from subnet group
                subnet_ids = [
                    s["SubnetIdentifier"]
                    for s in subnet_group.get("Subnets", [])
                ]

                resources.append(Resource(
                    arn=db_arn,
                    resource_type="rds",
                    name=db_id,
                    region=region,
                    tags=tags,
                    creation_date=db.get("InstanceCreateTime", "").isoformat()
                        if db.get("InstanceCreateTime") else None,
                    attributes={
                        "engine": db.get("Engine"),
                        "engine_version": db.get("EngineVersion"),
                        "instance_class": db.get("DBInstanceClass"),
                        "status": db.get("DBInstanceStatus"),
                        "vpc_id": subnet_group.get("VpcId"),
                        "multi_az": db.get("MultiAZ", False),
                        "storage_type": db.get("StorageType"),
                        "allocated_storage": db.get("AllocatedStorage"),
                        "security_group_ids": security_group_ids,
                        "subnet_ids": subnet_ids,
                        "kms_key_id": db.get("KmsKeyId"),
                    },
                ))

        return resources

    def _fetch_iam_roles(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch IAM roles (global resource)."""
        iam = session.client("iam")
        resources: list[Resource] = []
        paginator = iam.get_paginator("list_roles")

        for page in paginator.paginate():
            for role in page.get("Roles", []):
                role_name = role["RoleName"]
                role_arn = role["Arn"]

                # Get tags
                tags = {}
                try:
                    tag_resp = iam.list_role_tags(RoleName=role_name)
                    tags = self._extract_tags(tag_resp.get("Tags"))
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=role_arn,
                    resource_type="iam_role",
                    name=role_name,
                    region="global",
                    tags=tags,
                    creation_date=role.get("CreateDate", "").isoformat()
                        if role.get("CreateDate") else None,
                    attributes={
                        "path": role.get("Path"),
                        "max_session_duration": role.get("MaxSessionDuration"),
                        "description": role.get("Description", ""),
                    },
                ))

        return resources

    def _fetch_alb(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Application Load Balancers."""
        elbv2 = session.client("elbv2", region_name=region)
        resources: list[Resource] = []
        paginator = elbv2.get_paginator("describe_load_balancers")

        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                if lb.get("Type") != "application":
                    continue
                lb_arn = lb["LoadBalancerArn"]
                lb_name = lb["LoadBalancerName"]

                # Get tags
                tags = {}
                try:
                    tag_resp = elbv2.describe_tags(ResourceArns=[lb_arn])
                    for desc in tag_resp.get("TagDescriptions", []):
                        tags = self._extract_tags(desc.get("Tags"))
                except ClientError:
                    pass

                # Collect subnet IDs from availability zones
                subnet_ids = [
                    az["SubnetId"]
                    for az in lb.get("AvailabilityZones", [])
                    if az.get("SubnetId")
                ]

                # Security groups
                security_group_ids = lb.get("SecurityGroups", [])

                # Get load balancer attributes (access logs, etc.)
                access_logs_bucket: str | None = None
                access_logs_prefix: str | None = None
                try:
                    attrs_resp = elbv2.describe_load_balancer_attributes(
                        LoadBalancerArn=lb_arn
                    )
                    lb_attrs = {
                        a["Key"]: a["Value"]
                        for a in attrs_resp.get("Attributes", [])
                    }
                    if lb_attrs.get("access_logs.s3.enabled") == "true":
                        access_logs_bucket = lb_attrs.get("access_logs.s3.bucket")
                        access_logs_prefix = lb_attrs.get("access_logs.s3.prefix")
                except ClientError:
                    pass

                # Get target group targets (EC2 instances, IPs, Lambda ARNs)
                target_arns: list[str] = []
                try:
                    tg_paginator = elbv2.get_paginator("describe_target_groups")
                    for tg_page in tg_paginator.paginate(LoadBalancerArn=lb_arn):
                        for tg in tg_page.get("TargetGroups", []):
                            tg_arn = tg["TargetGroupArn"]
                            target_type = tg.get("TargetType", "instance")
                            try:
                                th_resp = elbv2.describe_target_health(
                                    TargetGroupArn=tg_arn
                                )
                                for thd in th_resp.get("TargetHealthDescriptions", []):
                                    target_id = thd["Target"]["Id"]
                                    if target_type == "instance":
                                        t_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{target_id}"
                                    elif target_type == "lambda":
                                        t_arn = target_id  # Already an ARN
                                    else:
                                        continue  # Skip IP targets
                                    if t_arn not in target_arns:
                                        target_arns.append(t_arn)
                            except ClientError:
                                pass
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=lb_arn,
                    resource_type="alb",
                    name=lb_name,
                    region=region,
                    tags=tags,
                    creation_date=lb.get("CreatedTime", "").isoformat()
                        if lb.get("CreatedTime") else None,
                    attributes={
                        "dns_name": lb.get("DNSName"),
                        "scheme": lb.get("Scheme"),
                        "vpc_id": lb.get("VpcId"),
                        "state": lb.get("State", {}).get("Code"),
                        "type": "application",
                        "security_group_ids": security_group_ids,
                        "subnet_ids": subnet_ids,
                        "target_arns": target_arns,
                        "access_logs_bucket": access_logs_bucket,
                        "access_logs_prefix": access_logs_prefix,
                    },
                ))

        return resources

    def _fetch_nlb(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Network Load Balancers."""
        elbv2 = session.client("elbv2", region_name=region)
        resources: list[Resource] = []
        paginator = elbv2.get_paginator("describe_load_balancers")

        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                if lb.get("Type") != "network":
                    continue
                lb_arn = lb["LoadBalancerArn"]
                lb_name = lb["LoadBalancerName"]

                # Get tags
                tags = {}
                try:
                    tag_resp = elbv2.describe_tags(ResourceArns=[lb_arn])
                    for desc in tag_resp.get("TagDescriptions", []):
                        tags = self._extract_tags(desc.get("Tags"))
                except ClientError:
                    pass

                # Collect subnet IDs from availability zones
                subnet_ids = [
                    az["SubnetId"]
                    for az in lb.get("AvailabilityZones", [])
                    if az.get("SubnetId")
                ]

                # NLBs may have security groups (newer feature)
                security_group_ids = lb.get("SecurityGroups", [])

                # Get load balancer attributes (access logs, etc.)
                access_logs_bucket: str | None = None
                access_logs_prefix: str | None = None
                try:
                    attrs_resp = elbv2.describe_load_balancer_attributes(
                        LoadBalancerArn=lb_arn
                    )
                    lb_attrs = {
                        a["Key"]: a["Value"]
                        for a in attrs_resp.get("Attributes", [])
                    }
                    if lb_attrs.get("access_logs.s3.enabled") == "true":
                        access_logs_bucket = lb_attrs.get("access_logs.s3.bucket")
                        access_logs_prefix = lb_attrs.get("access_logs.s3.prefix")
                except ClientError:
                    pass

                # Get target group targets (EC2 instances, IPs)
                target_arns: list[str] = []
                try:
                    tg_paginator = elbv2.get_paginator("describe_target_groups")
                    for tg_page in tg_paginator.paginate(LoadBalancerArn=lb_arn):
                        for tg in tg_page.get("TargetGroups", []):
                            tg_arn = tg["TargetGroupArn"]
                            target_type = tg.get("TargetType", "instance")
                            try:
                                th_resp = elbv2.describe_target_health(
                                    TargetGroupArn=tg_arn
                                )
                                for thd in th_resp.get("TargetHealthDescriptions", []):
                                    target_id = thd["Target"]["Id"]
                                    if target_type == "instance":
                                        t_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{target_id}"
                                    elif target_type == "lambda":
                                        t_arn = target_id
                                    else:
                                        continue
                                    if t_arn not in target_arns:
                                        target_arns.append(t_arn)
                            except ClientError:
                                pass
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=lb_arn,
                    resource_type="nlb",
                    name=lb_name,
                    region=region,
                    tags=tags,
                    creation_date=lb.get("CreatedTime", "").isoformat()
                        if lb.get("CreatedTime") else None,
                    attributes={
                        "dns_name": lb.get("DNSName"),
                        "scheme": lb.get("Scheme"),
                        "vpc_id": lb.get("VpcId"),
                        "state": lb.get("State", {}).get("Code"),
                        "type": "network",
                        "security_group_ids": security_group_ids,
                        "subnet_ids": subnet_ids,
                        "target_arns": target_arns,
                        "access_logs_bucket": access_logs_bucket,
                        "access_logs_prefix": access_logs_prefix,
                    },
                ))

        return resources

    def _fetch_ecs(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch ECS clusters and services."""
        ecs = session.client("ecs", region_name=region)
        resources: list[Resource] = []

        # List clusters
        cluster_arns = []
        paginator = ecs.get_paginator("list_clusters")
        for page in paginator.paginate():
            cluster_arns.extend(page.get("clusterArns", []))

        if not cluster_arns:
            return resources

        # Describe clusters (max 100 at a time)
        for i in range(0, len(cluster_arns), 100):
            batch = cluster_arns[i:i + 100]
            resp = ecs.describe_clusters(
                clusters=batch, include=["TAGS"]
            )
            for cluster in resp.get("clusters", []):
                cluster_arn = cluster["clusterArn"]
                cluster_name = cluster["clusterName"]
                tags = self._extract_tags(cluster.get("tags"))

                # Fetch services in this cluster to capture LB associations
                service_lb_target_groups: list[str] = []
                service_lb_arns: list[str] = []
                try:
                    svc_arns: list[str] = []
                    svc_paginator = ecs.get_paginator("list_services")
                    for svc_page in svc_paginator.paginate(cluster=cluster_arn):
                        svc_arns.extend(svc_page.get("serviceArns", []))

                    # Describe services in batches of 10
                    for j in range(0, len(svc_arns), 10):
                        svc_batch = svc_arns[j:j + 10]
                        svc_resp = ecs.describe_services(
                            cluster=cluster_arn, services=svc_batch
                        )
                        for svc in svc_resp.get("services", []):
                            for lb_conf in svc.get("loadBalancers", []):
                                tg_arn = lb_conf.get("targetGroupArn")
                                if tg_arn and tg_arn not in service_lb_target_groups:
                                    service_lb_target_groups.append(tg_arn)
                except ClientError:
                    pass

                # Resolve target group ARNs to load balancer ARNs
                if service_lb_target_groups:
                    try:
                        elbv2 = session.client("elbv2", region_name=region)
                        # describe_target_groups accepts up to 20 ARNs at a time
                        for j in range(0, len(service_lb_target_groups), 20):
                            tg_batch = service_lb_target_groups[j:j + 20]
                            tg_resp = elbv2.describe_target_groups(
                                TargetGroupArns=tg_batch
                            )
                            for tg in tg_resp.get("TargetGroups", []):
                                for lb_arn in tg.get("LoadBalancerArns", []):
                                    if lb_arn not in service_lb_arns:
                                        service_lb_arns.append(lb_arn)
                    except ClientError:
                        pass

                resources.append(Resource(
                    arn=cluster_arn,
                    resource_type="ecs",
                    name=cluster_name,
                    region=region,
                    tags=tags,
                    attributes={
                        "status": cluster.get("status"),
                        "running_tasks_count": cluster.get("runningTasksCount", 0),
                        "active_services_count": cluster.get("activeServicesCount", 0),
                        "load_balancer_arns": service_lb_arns,
                    },
                ))

        return resources

    def _fetch_sns(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch SNS topics."""
        sns = session.client("sns", region_name=region)
        resources: list[Resource] = []
        paginator = sns.get_paginator("list_topics")

        for page in paginator.paginate():
            for topic in page.get("Topics", []):
                topic_arn = topic["TopicArn"]
                topic_name = topic_arn.split(":")[-1]

                # Get tags
                tags = {}
                try:
                    tag_resp = sns.list_tags_for_resource(ResourceArn=topic_arn)
                    tags = self._extract_tags(tag_resp.get("Tags"))
                except ClientError:
                    pass

                # Get attributes
                attrs = {}
                try:
                    attr_resp = sns.get_topic_attributes(TopicArn=topic_arn)
                    topic_attrs = attr_resp.get("Attributes", {})
                    attrs = {
                        "display_name": topic_attrs.get("DisplayName", ""),
                        "subscriptions_confirmed": int(
                            topic_attrs.get("SubscriptionsConfirmed", 0)
                        ),
                    }
                except ClientError:
                    pass

                # Collect subscription endpoints (Lambda, SQS, HTTP ARNs)
                subscription_endpoints: list[str] = []
                try:
                    sub_paginator = sns.get_paginator("list_subscriptions_by_topic")
                    for sub_page in sub_paginator.paginate(TopicArn=topic_arn):
                        for sub in sub_page.get("Subscriptions", []):
                            endpoint = sub.get("Endpoint", "")
                            protocol = sub.get("Protocol", "")
                            # Only collect ARN-based endpoints (lambda, sqs, sns)
                            if protocol in ("lambda", "sqs", "application") and endpoint.startswith("arn:"):
                                if endpoint not in subscription_endpoints:
                                    subscription_endpoints.append(endpoint)
                except ClientError:
                    pass

                attrs["subscription_endpoints"] = subscription_endpoints

                resources.append(Resource(
                    arn=topic_arn,
                    resource_type="sns",
                    name=topic_name,
                    region=region,
                    tags=tags,
                    attributes=attrs,
                ))

        return resources

    def _fetch_sqs(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch SQS queues."""
        sqs = session.client("sqs", region_name=region)
        resources: list[Resource] = []

        paginator = sqs.get_paginator("list_queues")
        for page in paginator.paginate():
            for queue_url in page.get("QueueUrls", []):
                # Get queue attributes
                try:
                    attr_resp = sqs.get_queue_attributes(
                        QueueUrl=queue_url,
                        AttributeNames=["All"],
                    )
                    attrs = attr_resp.get("Attributes", {})
                except ClientError:
                    attrs = {}

                queue_arn = attrs.get(
                    "QueueArn",
                    f"arn:aws:sqs:{region}:{account_id}:{queue_url.split('/')[-1]}",
                )
                queue_name = queue_url.split("/")[-1]

                # Get tags
                tags = {}
                try:
                    tag_resp = sqs.list_queue_tags(QueueUrl=queue_url)
                    tags = tag_resp.get("Tags", {})
                except ClientError:
                    pass

                created = attrs.get("CreatedTimestamp")
                creation_date = (
                    datetime.fromtimestamp(int(created), tz=timezone.utc).isoformat()
                    if created
                    else None
                )

                resources.append(Resource(
                    arn=queue_arn,
                    resource_type="sqs",
                    name=queue_name,
                    region=region,
                    tags=tags,
                    creation_date=creation_date,
                    attributes={
                        "visibility_timeout": attrs.get("VisibilityTimeout"),
                        "message_retention_period": attrs.get("MessageRetentionPeriod"),
                        "approximate_messages": attrs.get(
                            "ApproximateNumberOfMessages"
                        ),
                    },
                ))

        return resources

    def _fetch_dynamodb(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch DynamoDB tables."""
        dynamodb = session.client("dynamodb", region_name=region)
        lambda_client = session.client("lambda", region_name=region)
        resources: list[Resource] = []
        paginator = dynamodb.get_paginator("list_tables")

        for page in paginator.paginate():
            for table_name in page.get("TableNames", []):
                try:
                    desc = dynamodb.describe_table(TableName=table_name)
                    table = desc.get("Table", {})
                except ClientError:
                    continue

                table_arn = table.get(
                    "TableArn",
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}",
                )

                # Get tags
                tags = {}
                try:
                    tag_resp = dynamodb.list_tags_of_resource(ResourceArn=table_arn)
                    tags = self._extract_tags(tag_resp.get("Tags"))
                except ClientError:
                    pass

                creation_date = table.get("CreationDateTime")

                # Collect stream targets (Lambda functions triggered by DynamoDB Streams)
                stream_targets: list[str] = []
                stream_spec = table.get("StreamSpecification", {})
                latest_stream_arn = table.get("LatestStreamArn")
                if stream_spec.get("StreamEnabled") and latest_stream_arn:
                    # Find Lambda event source mappings for this stream
                    try:
                        esm_paginator = lambda_client.get_paginator("list_event_source_mappings")
                        for esm_page in esm_paginator.paginate(EventSourceArn=latest_stream_arn):
                            for mapping in esm_page.get("EventSourceMappings", []):
                                func_arn = mapping.get("FunctionArn")
                                if func_arn and func_arn not in stream_targets:
                                    stream_targets.append(func_arn)
                    except ClientError:
                        pass

                resources.append(Resource(
                    arn=table_arn,
                    resource_type="dynamodb",
                    name=table_name,
                    region=region,
                    tags=tags,
                    creation_date=creation_date.isoformat() if creation_date else None,
                    attributes={
                        "status": table.get("TableStatus"),
                        "item_count": table.get("ItemCount", 0),
                        "size_bytes": table.get("TableSizeBytes", 0),
                        "billing_mode": table.get("BillingModeSummary", {}).get(
                            "BillingMode", "PROVISIONED"
                        ),
                        "stream_enabled": stream_spec.get("StreamEnabled", False),
                        "stream_targets": stream_targets,
                    },
                ))

        return resources

    def _fetch_cloudfront(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch CloudFront distributions (global resource)."""
        cf = session.client("cloudfront")
        resources: list[Resource] = []

        paginator = cf.get_paginator("list_distributions")
        for page in paginator.paginate():
            dist_list = page.get("DistributionList", {})
            for dist in dist_list.get("Items", []):
                dist_id = dist["Id"]
                dist_arn = dist["ARN"]
                domain = dist.get("DomainName", "")

                # Get tags
                tags = {}
                try:
                    tag_resp = cf.list_tags_for_resource(Resource=dist_arn)
                    items = tag_resp.get("Tags", {}).get("Items", [])
                    tags = self._extract_tags(items)
                except ClientError:
                    pass

                # Extract origin details (S3 buckets, ALB/NLB, custom origins)
                origin_arns: list[str] = []
                origin_lb_arns: list[str] = []
                origins = dist.get("Origins", {}).get("Items", [])
                for origin in origins:
                    origin_domain = origin.get("DomainName", "")
                    # S3 bucket origins: <bucket>.s3.amazonaws.com or <bucket>.s3.<region>.amazonaws.com
                    if ".s3." in origin_domain or origin_domain.endswith(".s3.amazonaws.com"):
                        bucket_name = origin_domain.split(".s3")[0]
                        origin_arns.append(f"arn:aws:s3:::{bucket_name}")
                    # ALB/NLB origins: <name>-<id>.<region>.elb.amazonaws.com
                    elif ".elb.amazonaws.com" in origin_domain:
                        origin_lb_arns.append(origin_domain)

                # Extract logging bucket if configured
                logging_bucket: str | None = None
                logging_config = dist.get("ViewerCertificate", {})
                # Logging is in the distribution config
                dist_logging = dist.get("Logging", {})
                if dist_logging and dist_logging.get("Enabled"):
                    log_bucket_domain = dist_logging.get("Bucket", "")
                    if log_bucket_domain:
                        # Format: <bucket>.s3.amazonaws.com
                        logging_bucket = log_bucket_domain.split(".s3")[0]

                resources.append(Resource(
                    arn=dist_arn,
                    resource_type="cloudfront",
                    name=domain or dist_id,
                    region="global",
                    tags=tags,
                    creation_date=dist.get("LastModifiedTime", "").isoformat()
                        if dist.get("LastModifiedTime") else None,
                    attributes={
                        "domain_name": domain,
                        "status": dist.get("Status"),
                        "enabled": dist.get("Enabled", False),
                        "price_class": dist.get("PriceClass"),
                        "origin_arns": origin_arns,
                        "origin_lb_arns": origin_lb_arns,
                        "logging_bucket": logging_bucket,
                    },
                ))

        return resources

    def _fetch_route53(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Route53 hosted zones (global resource)."""
        route53 = session.client("route53")
        resources: list[Resource] = []

        paginator = route53.get_paginator("list_hosted_zones")
        for page in paginator.paginate():
            for zone in page.get("HostedZones", []):
                zone_id = zone["Id"].split("/")[-1]
                zone_name = zone["Name"]

                # Get tags
                tags = {}
                try:
                    tag_resp = route53.list_tags_for_resource(
                        ResourceType="hostedzone", ResourceId=zone_id
                    )
                    tag_set = tag_resp.get("ResourceTagSet", {}).get("Tags", [])
                    tags = self._extract_tags(tag_set)
                except ClientError:
                    pass

                # Collect alias targets (ALBs, CloudFront, S3, etc.)
                alias_targets: list[str] = []
                try:
                    rrs_paginator = route53.get_paginator("list_resource_record_sets")
                    for rrs_page in rrs_paginator.paginate(HostedZoneId=zone_id):
                        for rr in rrs_page.get("ResourceRecordSets", []):
                            alias = rr.get("AliasTarget")
                            if alias:
                                dns_name = alias.get("DNSName", "")
                                if dns_name and dns_name not in alias_targets:
                                    alias_targets.append(dns_name.rstrip("."))
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=f"arn:aws:route53:::hostedzone/{zone_id}",
                    resource_type="route53",
                    name=zone_name,
                    region="global",
                    tags=tags,
                    attributes={
                        "record_count": zone.get("ResourceRecordSetCount", 0),
                        "is_private": zone.get("Config", {}).get(
                            "PrivateZone", False
                        ),
                        "comment": zone.get("Config", {}).get("Comment", ""),
                        "alias_targets": alias_targets,
                    },
                ))

        return resources

    def _fetch_api_gateway(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch API Gateway REST APIs."""
        apigw = session.client("apigateway", region_name=region)
        resources: list[Resource] = []

        paginator = apigw.get_paginator("get_rest_apis")
        for page in paginator.paginate():
            for api in page.get("items", []):
                api_id = api["id"]
                api_name = api.get("name", api_id)
                api_arn = (
                    f"arn:aws:apigateway:{region}::/restapis/{api_id}"
                )

                # Tags are included in the response for REST APIs
                tags = api.get("tags", {})

                created = api.get("createdDate")

                # Collect integration targets (Lambda ARNs, HTTP endpoints)
                integration_targets: list[str] = []
                try:
                    res_resp = apigw.get_resources(restApiId=api_id, limit=500)
                    for resource_item in res_resp.get("items", []):
                        for method_info in resource_item.get("resourceMethods", {}).values():
                            # Need to get each method's integration
                            pass
                    # Fetch integrations by iterating resources and methods
                    for resource_item in res_resp.get("items", []):
                        resource_id = resource_item["id"]
                        for http_method in resource_item.get("resourceMethods", {}).keys():
                            try:
                                integ = apigw.get_integration(
                                    restApiId=api_id,
                                    resourceId=resource_id,
                                    httpMethod=http_method,
                                )
                                uri = integ.get("uri", "")
                                # Extract Lambda ARN from integration URI
                                # Format: arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{arn}/invocations
                                if ":lambda:path" in uri and "/functions/" in uri:
                                    lambda_arn = uri.split("/functions/")[1].split("/invocations")[0]
                                    if lambda_arn and lambda_arn not in integration_targets:
                                        integration_targets.append(lambda_arn)
                            except ClientError:
                                pass
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=api_arn,
                    resource_type="api_gateway",
                    name=api_name,
                    region=region,
                    tags=tags,
                    creation_date=created.isoformat() if created else None,
                    attributes={
                        "description": api.get("description", ""),
                        "endpoint_configuration": api.get(
                            "endpointConfiguration", {}
                        ).get("types", []),
                        "api_key_source": api.get("apiKeySource"),
                        "integration_targets": integration_targets,
                    },
                ))

        return resources

    # ------------------------------------------------------------------
    # Tier 1: Additional Resource Fetchers
    # ------------------------------------------------------------------

    def _fetch_eks(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch EKS clusters."""
        eks = session.client("eks", region_name=region)
        resources: list[Resource] = []

        paginator = eks.get_paginator("list_clusters")
        cluster_names: list[str] = []
        for page in paginator.paginate():
            cluster_names.extend(page.get("clusters", []))

        for name in cluster_names:
            try:
                resp = eks.describe_cluster(name=name)
                cluster = resp.get("cluster", {})
                cluster_arn = cluster.get("arn", f"arn:aws:eks:{region}:{account_id}:cluster/{name}")
                tags = cluster.get("tags", {})

                vpc_config = cluster.get("resourcesVpcConfig", {})

                resources.append(Resource(
                    arn=cluster_arn,
                    resource_type="eks",
                    name=name,
                    region=region,
                    tags=tags,
                    creation_date=cluster.get("createdAt", "").isoformat()
                        if cluster.get("createdAt") else None,
                    iam_role=cluster.get("roleArn"),
                    attributes={
                        "status": cluster.get("status"),
                        "version": cluster.get("version"),
                        "endpoint": cluster.get("endpoint"),
                        "platform_version": cluster.get("platformVersion"),
                        "vpc_id": vpc_config.get("vpcId"),
                        "subnet_ids": vpc_config.get("subnetIds", []),
                        "security_group_ids": vpc_config.get("securityGroupIds", []),
                    },
                ))
            except ClientError:
                pass

        return resources

    def _fetch_elasticache(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch ElastiCache clusters."""
        client = session.client("elasticache", region_name=region)
        resources: list[Resource] = []

        paginator = client.get_paginator("describe_cache_clusters")
        for page in paginator.paginate(ShowCacheNodeInfo=True):
            for cluster in page.get("CacheClusters", []):
                cluster_id = cluster["CacheClusterId"]
                cluster_arn = cluster.get("ARN",
                    f"arn:aws:elasticache:{region}:{account_id}:cluster:{cluster_id}")

                # Fetch tags
                tags = {}
                try:
                    tag_resp = client.list_tags_for_resource(ResourceName=cluster_arn)
                    tags = self._extract_tags(tag_resp.get("TagList"))
                except ClientError:
                    pass

                # Collect security group IDs
                security_group_ids = [
                    sg["SecurityGroupId"]
                    for sg in cluster.get("SecurityGroups", [])
                    if sg.get("Status") == "active"
                ]

                # Get VPC info from cache subnet group
                vpc_id = None
                subnet_ids: list[str] = []
                subnet_group_name = cluster.get("CacheSubnetGroupName")
                if subnet_group_name:
                    try:
                        sg_resp = client.describe_cache_subnet_groups(
                            CacheSubnetGroupName=subnet_group_name
                        )
                        for group in sg_resp.get("CacheSubnetGroups", []):
                            vpc_id = group.get("VpcId")
                            subnet_ids = [
                                s["SubnetIdentifier"]
                                for s in group.get("Subnets", [])
                            ]
                    except ClientError:
                        pass

                resources.append(Resource(
                    arn=cluster_arn,
                    resource_type="elasticache",
                    name=cluster_id,
                    region=region,
                    tags=tags,
                    creation_date=cluster.get("CacheClusterCreateTime", "").isoformat()
                        if cluster.get("CacheClusterCreateTime") else None,
                    attributes={
                        "engine": cluster.get("Engine"),
                        "engine_version": cluster.get("EngineVersion"),
                        "cache_node_type": cluster.get("CacheNodeType"),
                        "num_cache_nodes": cluster.get("NumCacheNodes"),
                        "status": cluster.get("CacheClusterStatus"),
                        "preferred_az": cluster.get("PreferredAvailabilityZone"),
                        "vpc_id": vpc_id,
                        "security_group_ids": security_group_ids,
                        "subnet_ids": subnet_ids,
                    },
                ))

        return resources

    def _fetch_ebs(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch EBS volumes."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page.get("Volumes", []):
                vol_id = vol["VolumeId"]
                tags = self._extract_tags(vol.get("Tags"))
                name = self._get_name_from_tags(tags, vol_id)

                attachments = vol.get("Attachments", [])
                attached_to = attachments[0].get("InstanceId") if attachments else None

                resources.append(Resource(
                    arn=f"arn:aws:ec2:{region}:{account_id}:volume/{vol_id}",
                    resource_type="ebs",
                    name=name,
                    region=region,
                    tags=tags,
                    creation_date=vol.get("CreateTime", "").isoformat()
                        if vol.get("CreateTime") else None,
                    attributes={
                        "volume_type": vol.get("VolumeType"),
                        "size_gb": vol.get("Size"),
                        "state": vol.get("State"),
                        "iops": vol.get("Iops"),
                        "encrypted": vol.get("Encrypted", False),
                        "availability_zone": vol.get("AvailabilityZone"),
                        "attached_to": attached_to,
                        "kms_key_id": vol.get("KmsKeyId"),
                    },
                ))

        return resources

    def _fetch_elastic_ips(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Elastic IP addresses."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        response = ec2.describe_addresses()
        for addr in response.get("Addresses", []):
            alloc_id = addr.get("AllocationId", addr.get("PublicIp", "unknown"))
            tags = self._extract_tags(addr.get("Tags"))
            name = self._get_name_from_tags(tags, addr.get("PublicIp", alloc_id))

            resources.append(Resource(
                arn=f"arn:aws:ec2:{region}:{account_id}:elastic-ip/{alloc_id}",
                resource_type="elastic_ip",
                name=name,
                region=region,
                tags=tags,
                attributes={
                    "public_ip": addr.get("PublicIp"),
                    "private_ip": addr.get("PrivateIpAddress"),
                    "instance_id": addr.get("InstanceId"),
                    "network_interface_id": addr.get("NetworkInterfaceId"),
                    "domain": addr.get("Domain"),
                },
            ))

        return resources

    def _fetch_nat_gateways(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch NAT Gateways."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        paginator = ec2.get_paginator("describe_nat_gateways")
        for page in paginator.paginate():
            for ngw in page.get("NatGateways", []):
                ngw_id = ngw["NatGatewayId"]
                tags = self._extract_tags(ngw.get("Tags"))
                name = self._get_name_from_tags(tags, ngw_id)

                resources.append(Resource(
                    arn=f"arn:aws:ec2:{region}:{account_id}:natgateway/{ngw_id}",
                    resource_type="nat_gateway",
                    name=name,
                    region=region,
                    tags=tags,
                    creation_date=ngw.get("CreateTime", "").isoformat()
                        if ngw.get("CreateTime") else None,
                    attributes={
                        "state": ngw.get("State"),
                        "vpc_id": ngw.get("VpcId"),
                        "subnet_id": ngw.get("SubnetId"),
                        "connectivity_type": ngw.get("ConnectivityType"),
                        "elastic_ip_allocation_ids": [
                            addr["AllocationId"]
                            for addr in ngw.get("NatGatewayAddresses", [])
                            if addr.get("AllocationId")
                        ],
                    },
                ))

        return resources

    def _fetch_transit_gateways(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Transit Gateways."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        paginator = ec2.get_paginator("describe_transit_gateways")
        for page in paginator.paginate():
            for tgw in page.get("TransitGateways", []):
                tgw_id = tgw["TransitGatewayId"]
                tgw_arn = tgw.get("TransitGatewayArn",
                    f"arn:aws:ec2:{region}:{account_id}:transit-gateway/{tgw_id}")
                tags = self._extract_tags(tgw.get("Tags"))
                name = self._get_name_from_tags(tags, tgw_id)

                resources.append(Resource(
                    arn=tgw_arn,
                    resource_type="transit_gateway",
                    name=name,
                    region=region,
                    tags=tags,
                    creation_date=tgw.get("CreationTime", "").isoformat()
                        if tgw.get("CreationTime") else None,
                    attributes={
                        "state": tgw.get("State"),
                        "owner_id": tgw.get("OwnerId"),
                        "description": tgw.get("Description", ""),
                    },
                ))

        return resources

    def _fetch_vpn_gateways(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch VPN Gateways."""
        ec2 = session.client("ec2", region_name=region)
        resources: list[Resource] = []

        response = ec2.describe_vpn_gateways()
        for vgw in response.get("VpnGateways", []):
            vgw_id = vgw["VpnGatewayId"]
            tags = self._extract_tags(vgw.get("Tags"))
            name = self._get_name_from_tags(tags, vgw_id)

            vpc_attachments = vgw.get("VpcAttachments", [])
            attached_vpc = vpc_attachments[0].get("VpcId") if vpc_attachments else None

            resources.append(Resource(
                arn=f"arn:aws:ec2:{region}:{account_id}:vpn-gateway/{vgw_id}",
                resource_type="vpn_gateway",
                name=name,
                region=region,
                tags=tags,
                attributes={
                    "state": vgw.get("State"),
                    "type": vgw.get("Type"),
                    "availability_zone": vgw.get("AvailabilityZone"),
                    "attached_vpc": attached_vpc,
                },
            ))

        return resources

    def _fetch_step_functions(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Step Functions state machines."""
        sfn = session.client("stepfunctions", region_name=region)
        resources: list[Resource] = []

        paginator = sfn.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page.get("stateMachines", []):
                sm_arn = sm["stateMachineArn"]
                sm_name = sm["name"]

                # Get tags
                tags = {}
                try:
                    tag_resp = sfn.list_tags_for_resource(resourceArn=sm_arn)
                    tags = {t["key"]: t["value"] for t in tag_resp.get("tags", [])}
                except ClientError:
                    pass

                # Get details
                try:
                    detail = sfn.describe_state_machine(stateMachineArn=sm_arn)
                    role_arn = detail.get("roleArn")
                    created = detail.get("creationDate")
                    status = detail.get("status")
                    sm_type = detail.get("type")
                except ClientError:
                    role_arn = None
                    created = sm.get("creationDate")
                    status = None
                    sm_type = sm.get("type")

                resources.append(Resource(
                    arn=sm_arn,
                    resource_type="step_functions",
                    name=sm_name,
                    region=region,
                    tags=tags,
                    creation_date=created.isoformat() if created else None,
                    iam_role=role_arn,
                    attributes={
                        "status": status,
                        "type": sm_type,
                    },
                ))

        return resources

    def _fetch_kinesis(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Kinesis data streams."""
        kinesis = session.client("kinesis", region_name=region)
        resources: list[Resource] = []

        paginator = kinesis.get_paginator("list_streams")
        stream_names: list[str] = []
        for page in paginator.paginate():
            stream_names.extend(page.get("StreamNames", []))

        for name in stream_names:
            try:
                resp = kinesis.describe_stream_summary(StreamName=name)
                desc = resp.get("StreamDescriptionSummary", {})
                stream_arn = desc.get("StreamARN",
                    f"arn:aws:kinesis:{region}:{account_id}:stream/{name}")

                # Get tags
                tags = {}
                try:
                    tag_resp = kinesis.list_tags_for_stream(StreamName=name)
                    tags = {t["Key"]: t["Value"] for t in tag_resp.get("Tags", [])}
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=stream_arn,
                    resource_type="kinesis",
                    name=name,
                    region=region,
                    tags=tags,
                    creation_date=desc.get("StreamCreationTimestamp", "").isoformat()
                        if desc.get("StreamCreationTimestamp") else None,
                    attributes={
                        "status": desc.get("StreamStatus"),
                        "retention_period_hours": desc.get("RetentionPeriodHours"),
                        "shard_count": desc.get("OpenShardCount"),
                        "encryption_type": desc.get("EncryptionType"),
                    },
                ))
            except ClientError:
                pass

        return resources

    def _fetch_secrets_manager(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Secrets Manager secrets (metadata only, not values)."""
        client = session.client("secretsmanager", region_name=region)
        resources: list[Resource] = []

        paginator = client.get_paginator("list_secrets")
        for page in paginator.paginate():
            for secret in page.get("SecretList", []):
                secret_arn = secret["ARN"]
                secret_name = secret["Name"]
                tags = self._extract_tags(secret.get("Tags"))

                resources.append(Resource(
                    arn=secret_arn,
                    resource_type="secrets_manager",
                    name=secret_name,
                    region=region,
                    tags=tags,
                    creation_date=secret.get("CreatedDate", "").isoformat()
                        if secret.get("CreatedDate") else None,
                    attributes={
                        "description": secret.get("Description", ""),
                        "rotation_enabled": secret.get("RotationEnabled", False),
                        "last_accessed": secret.get("LastAccessedDate", "").isoformat()
                            if secret.get("LastAccessedDate") else None,
                        "last_changed": secret.get("LastChangedDate", "").isoformat()
                            if secret.get("LastChangedDate") else None,
                    },
                ))

        return resources

    def _fetch_ecr(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch ECR repositories (global-ish, scanned once)."""
        ecr = session.client("ecr", region_name=region)
        resources: list[Resource] = []

        paginator = ecr.get_paginator("describe_repositories")
        for page in paginator.paginate():
            for repo in page.get("repositories", []):
                repo_arn = repo["repositoryArn"]
                repo_name = repo["repositoryName"]

                # Get tags
                tags = {}
                try:
                    tag_resp = ecr.list_tags_for_resource(resourceArn=repo_arn)
                    tags = {t["Key"]: t["Value"] for t in tag_resp.get("tags", [])}
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=repo_arn,
                    resource_type="ecr",
                    name=repo_name,
                    region=region,
                    tags=tags,
                    creation_date=repo.get("createdAt", "").isoformat()
                        if repo.get("createdAt") else None,
                    attributes={
                        "repository_uri": repo.get("repositoryUri"),
                        "image_tag_mutability": repo.get("imageTagMutability"),
                        "scan_on_push": repo.get("imageScanningConfiguration", {}).get(
                            "scanOnPush", False),
                        "encryption_type": repo.get("encryptionConfiguration", {}).get(
                            "encryptionType"),
                    },
                ))

        return resources

    def _fetch_redshift(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Redshift clusters."""
        client = session.client("redshift", region_name=region)
        resources: list[Resource] = []

        paginator = client.get_paginator("describe_clusters")
        for page in paginator.paginate():
            for cluster in page.get("Clusters", []):
                cluster_id = cluster["ClusterIdentifier"]
                cluster_arn = f"arn:aws:redshift:{region}:{account_id}:cluster:{cluster_id}"

                tags = self._extract_tags(cluster.get("Tags"))

                # Collect security group IDs
                security_group_ids = [
                    sg["VpcSecurityGroupId"]
                    for sg in cluster.get("VpcSecurityGroups", [])
                    if sg.get("Status") == "active"
                ]

                resources.append(Resource(
                    arn=cluster_arn,
                    resource_type="redshift",
                    name=cluster_id,
                    region=region,
                    tags=tags,
                    creation_date=cluster.get("ClusterCreateTime", "").isoformat()
                        if cluster.get("ClusterCreateTime") else None,
                    attributes={
                        "node_type": cluster.get("NodeType"),
                        "status": cluster.get("ClusterStatus"),
                        "number_of_nodes": cluster.get("NumberOfNodes"),
                        "db_name": cluster.get("DBName"),
                        "vpc_id": cluster.get("VpcId"),
                        "encrypted": cluster.get("Encrypted", False),
                        "security_group_ids": security_group_ids,
                        "kms_key_id": cluster.get("KmsKeyId"),
                    },
                ))

        return resources

    def _fetch_opensearch(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch OpenSearch domains."""
        client = session.client("opensearch", region_name=region)
        resources: list[Resource] = []

        try:
            response = client.list_domain_names()
            domain_names = [d["DomainName"] for d in response.get("DomainNames", [])]
        except ClientError:
            return resources

        # Describe domains in batches of 5
        for i in range(0, len(domain_names), 5):
            batch = domain_names[i:i + 5]
            try:
                resp = client.describe_domains(DomainNames=batch)
                for domain in resp.get("DomainStatusList", []):
                    domain_arn = domain["ARN"]
                    domain_name = domain["DomainName"]

                    # Get tags
                    tags = {}
                    try:
                        tag_resp = client.list_tags(ARN=domain_arn)
                        tags = self._extract_tags(tag_resp.get("TagList"))
                    except ClientError:
                        pass

                    vpc_options = domain.get("VPCOptions", {})

                    resources.append(Resource(
                        arn=domain_arn,
                        resource_type="opensearch",
                        name=domain_name,
                        region=region,
                        tags=tags,
                        attributes={
                            "engine_version": domain.get("EngineVersion"),
                            "instance_type": domain.get("ClusterConfig", {}).get(
                                "InstanceType"),
                            "instance_count": domain.get("ClusterConfig", {}).get(
                                "InstanceCount"),
                            "processing": domain.get("Processing", False),
                            "endpoint": domain.get("Endpoint"),
                            "vpc_id": vpc_options.get("VPCId"),
                            "subnet_ids": vpc_options.get("SubnetIds", []),
                            "security_group_ids": vpc_options.get("SecurityGroupIds", []),
                        },
                    ))
            except ClientError:
                pass

        return resources

    def _fetch_codepipeline(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch CodePipeline pipelines."""
        client = session.client("codepipeline", region_name=region)
        resources: list[Resource] = []

        paginator = client.get_paginator("list_pipelines")
        for page in paginator.paginate():
            for pipeline in page.get("pipelines", []):
                pipeline_name = pipeline["name"]
                pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{pipeline_name}"

                # Get tags
                tags = {}
                try:
                    tag_resp = client.list_tags_for_resource(resourceArn=pipeline_arn)
                    tags = {t["key"]: t["value"] for t in tag_resp.get("tags", [])}
                except ClientError:
                    pass

                resources.append(Resource(
                    arn=pipeline_arn,
                    resource_type="codepipeline",
                    name=pipeline_name,
                    region=region,
                    tags=tags,
                    creation_date=pipeline.get("created", "").isoformat()
                        if pipeline.get("created") else None,
                    attributes={
                        "version": pipeline.get("version"),
                        "updated": pipeline.get("updated", "").isoformat()
                            if pipeline.get("updated") else None,
                    },
                ))

        return resources

    def _fetch_glue(
        self, session: boto3.Session, region: str, account_id: str
    ) -> list[Resource]:
        """Fetch Glue databases and jobs."""
        glue = session.client("glue", region_name=region)
        resources: list[Resource] = []

        # Fetch Glue Jobs
        try:
            paginator = glue.get_paginator("get_jobs")
            for page in paginator.paginate():
                for job in page.get("Jobs", []):
                    job_name = job["Name"]
                    job_arn = f"arn:aws:glue:{region}:{account_id}:job/{job_name}"

                    # Get tags
                    tags = {}
                    try:
                        tag_resp = glue.get_tags(ResourceArn=job_arn)
                        tags = tag_resp.get("Tags", {})
                    except ClientError:
                        pass

                    resources.append(Resource(
                        arn=job_arn,
                        resource_type="glue",
                        name=job_name,
                        region=region,
                        tags=tags,
                        creation_date=job.get("CreatedOn", "").isoformat()
                            if job.get("CreatedOn") else None,
                        iam_role=job.get("Role"),
                        attributes={
                            "type": "job",
                            "worker_type": job.get("WorkerType"),
                            "number_of_workers": job.get("NumberOfWorkers"),
                            "glue_version": job.get("GlueVersion"),
                            "status": job.get("LastModifiedOn", "").isoformat()
                                if job.get("LastModifiedOn") else None,
                        },
                    ))
        except ClientError:
            pass

        return resources
