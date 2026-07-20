"""Multi-region AWS resource scanner with exponential backoff and timeout handling."""

import asyncio
import logging
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from ..exceptions import CloudSpyglassError
from ..models.resources import Resource
from ..models.scan import RegionFailure, ScanResult

logger = logging.getLogger(__name__)

# Constants
TOTAL_SCAN_TIMEOUT_SECONDS = 600  # 10 minutes
REGION_SCAN_TIMEOUT_SECONDS = 60  # 60 seconds per region
MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 30

# Global resource types (scanned once, not per-region)
GLOBAL_RESOURCE_TYPES = ["s3", "iam_role", "cloudfront", "route53"]

# Regional resource types (scanned per region)
REGIONAL_RESOURCE_TYPES = [
    "ec2", "security_group", "vpc", "subnet", "lambda", "rds",
    "alb", "nlb", "ecs", "sns", "sqs", "dynamodb", "api_gateway",
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
        try:
            region_tasks = [
                self._scan_region(region, account_id)
                for region in regions
            ]
            results = await asyncio.wait_for(
                asyncio.gather(*region_tasks, return_exceptions=True),
                timeout=TOTAL_SCAN_TIMEOUT_SECONDS,
            )

            for i, result in enumerate(results):
                region = regions[i]
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
            # Total 10-minute timeout reached — return what we have
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

            resources.append(Resource(
                arn=f"arn:aws:s3:::{bucket_name}",
                resource_type="s3",
                name=bucket_name,
                region=bucket_region,
                tags=tags,
                creation_date=creation_date.isoformat() if creation_date else None,
                attributes={
                    "bucket_name": bucket_name,
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
                    },
                ))

        return resources
