"""Detects relationships between AWS resources by configuration analysis."""

import logging
import re

from ..models.resources import Relationship, Resource

logger = logging.getLogger(__name__)


class RelationshipResolver:
    """Detects relationships between AWS resources by configuration analysis.

    Analyzes scanned resource configurations to produce a list of typed
    relationships (network, iam, event, data) and placeholder resources
    for any unresolved ARN targets.
    """

    def __init__(self, account_id: str) -> None:
        """Initialize the RelationshipResolver.

        Args:
            account_id: The 12-digit AWS account ID from the scan.
        """
        self._account_id = account_id

    def resolve(
        self, resources: list[Resource]
    ) -> tuple[list[Relationship], list[Resource]]:
        """Orchestrate all category resolvers and return relationships + unresolved targets.

        Args:
            resources: List of scanned Resource objects.

        Returns:
            Tuple of (relationships, unresolved_resources) where unresolved_resources
            are placeholder Resource objects for ARNs referenced but not found in the scan.
        """
        # Build ARN lookup index for quick resolution
        self._arn_index: dict[str, Resource] = {r.arn: r for r in resources}

        relationships: list[Relationship] = []

        relationships.extend(self._resolve_network_relationships(resources))
        relationships.extend(self._resolve_iam_relationships(resources))
        relationships.extend(self._resolve_event_relationships(resources))
        relationships.extend(self._resolve_data_relationships(resources))

        # Collect unresolved targets
        unresolved_resources = self._collect_unresolved_targets(relationships)

        return relationships, unresolved_resources

    def _resolve_network_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve network relationships: SG attachments, VPC memberships, LB targets.

        Detects:
        - EC2 → Security Group (from SecurityGroups[].GroupId)
        - EC2 → VPC (from VpcId)
        - EC2 → Subnet (from SubnetId)
        - RDS → VPC (from DBSubnetGroup.VpcId)
        - Lambda → VPC (from VpcConfig.VpcId)
        - Lambda → Subnet (from VpcConfig.SubnetIds[])
        - ALB/NLB → VPC (from VpcId)
        - ALB/NLB → Target (from TargetGroups[].Targets[])
        """
        relationships: list[Relationship] = []

        for resource in resources:
            attrs = resource.attributes

            if resource.resource_type == "ec2":
                # EC2 → Security Groups
                for sg_id in attrs.get("security_groups", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="SecurityGroups[].GroupId",
                    ))

                # EC2 → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

                # EC2 → Subnet
                subnet_id = attrs.get("subnet_id")
                if subnet_id:
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="SubnetId",
                    ))

            elif resource.resource_type == "lambda":
                # Lambda → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcConfig.VpcId",
                    ))

                # Lambda → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="VpcConfig.SubnetIds[]",
                    ))

            elif resource.resource_type == "rds":
                # RDS → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="DBSubnetGroup.VpcId",
                    ))

            elif resource.resource_type in ("alb", "nlb"):
                # ALB/NLB → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

                # ALB/NLB → Targets (from target_arns attribute if available)
                target_arns = attrs.get("target_arns", [])
                for target_arn in target_arns:
                    if self._classify_external(target_arn):
                        # Mark external but still record
                        pass
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="network",
                        derived_from="TargetGroups[].Targets[]",
                    ))

        return relationships

    def _resolve_iam_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve IAM relationships: role associations for Lambda, EC2, ECS.

        Detects:
        - EC2 → IAM Role (from IamInstanceProfile.Arn)
        - Lambda → IAM Role (from Role)
        - ECS → IAM Role (from TaskDefinition.TaskRoleArn)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            if resource.resource_type == "ec2":
                # EC2 → IAM Role
                if resource.iam_role:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=resource.iam_role,
                        category="iam",
                        derived_from="IamInstanceProfile.Arn",
                    ))

            elif resource.resource_type == "lambda":
                # Lambda → IAM Role
                if resource.iam_role:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=resource.iam_role,
                        category="iam",
                        derived_from="Role",
                    ))

            elif resource.resource_type == "ecs":
                # ECS → IAM Role (task role stored in iam_role or attributes)
                task_role = resource.iam_role or resource.attributes.get("task_role_arn")
                if task_role:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=task_role,
                        category="iam",
                        derived_from="TaskDefinition.TaskRoleArn",
                    ))

        return relationships

    def _resolve_event_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve event relationships: event source mappings, S3 notifications.

        Detects:
        - SQS → Lambda (from EventSourceMappings[].EventSourceArn)
        - SNS → Lambda (from Subscriptions[].Endpoint)
        - S3 → Lambda/SQS/SNS (from NotificationConfiguration)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            attrs = resource.attributes

            if resource.resource_type == "sqs":
                # SQS → Lambda (event source mappings stored in attributes)
                event_source_targets = attrs.get("event_source_targets", [])
                for target_arn in event_source_targets:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="EventSourceMappings[].EventSourceArn",
                    ))

            elif resource.resource_type == "sns":
                # SNS → Lambda (subscriptions stored in attributes)
                subscription_endpoints = attrs.get("subscription_endpoints", [])
                for endpoint_arn in subscription_endpoints:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=endpoint_arn,
                        category="event",
                        derived_from="Subscriptions[].Endpoint",
                    ))

            elif resource.resource_type == "s3":
                # S3 → Lambda/SQS/SNS (notifications stored in attributes)
                notification_targets = attrs.get("notification_targets", [])
                for target_arn in notification_targets:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="NotificationConfiguration",
                    ))

        return relationships

    def _resolve_data_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve data relationships: RDS subnet group memberships.

        Detects:
        - RDS → Subnet (from DBSubnetGroup.Subnets[].SubnetIdentifier)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            if resource.resource_type == "rds":
                attrs = resource.attributes
                # RDS → Subnets (subnet identifiers from the subnet group)
                subnet_ids = attrs.get("subnet_ids", [])
                for subnet_id in subnet_ids:
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="data",
                        derived_from="DBSubnetGroup.Subnets[].SubnetIdentifier",
                    ))

        return relationships

    def _classify_external(self, arn_or_hostname: str) -> bool:
        """Detect cross-account ARNs and non-AWS hostnames.

        Args:
            arn_or_hostname: An ARN string or hostname to classify.

        Returns:
            True if the target is external (cross-account or non-AWS hostname).
        """
        # Check if it's an ARN
        arn_pattern = re.compile(
            r"^arn:aws[a-zA-Z-]*:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:(\d{12}|):"
        )
        match = arn_pattern.match(arn_or_hostname)
        if match:
            # Extract account ID from the ARN
            account_in_arn = match.group(1)
            if account_in_arn and account_in_arn != self._account_id:
                return True
            return False

        # If not an ARN, treat as hostname — check if it's AWS
        if not arn_or_hostname.endswith(".amazonaws.com"):
            return True

        return False

    def _collect_unresolved_targets(
        self, relationships: list[Relationship]
    ) -> list[Resource]:
        """Create placeholder Resource objects for targets not found in scan results.

        For each relationship target ARN that is not in the ARN index,
        creates an unresolved Resource placeholder.

        Returns:
            List of placeholder Resource objects with is_unresolved=True.
        """
        unresolved: dict[str, Resource] = {}

        for rel in relationships:
            if rel.target_arn not in self._arn_index and rel.target_arn not in unresolved:
                is_external = self._classify_external(rel.target_arn)
                resource_type = self._infer_type_from_arn(rel.target_arn)
                name = self._infer_name_from_arn(rel.target_arn)
                region = self._infer_region_from_arn(rel.target_arn)

                unresolved[rel.target_arn] = Resource(
                    arn=rel.target_arn,
                    resource_type=resource_type,
                    name=name,
                    region=region,
                    is_external=is_external,
                    is_unresolved=True,
                )

        return list(unresolved.values())

    # ------------------------------------------------------------------
    # ARN Builder Helpers
    # ------------------------------------------------------------------

    def _build_sg_arn(self, sg_id: str, region: str) -> str:
        """Build ARN for a Security Group."""
        return f"arn:aws:ec2:{region}:{self._account_id}:security-group/{sg_id}"

    def _build_vpc_arn(self, vpc_id: str, region: str) -> str:
        """Build ARN for a VPC."""
        return f"arn:aws:ec2:{region}:{self._account_id}:vpc/{vpc_id}"

    def _build_subnet_arn(self, subnet_id: str, region: str) -> str:
        """Build ARN for a Subnet."""
        return f"arn:aws:ec2:{region}:{self._account_id}:subnet/{subnet_id}"

    # ------------------------------------------------------------------
    # ARN Parsing Helpers
    # ------------------------------------------------------------------

    def _infer_type_from_arn(self, arn: str) -> str:
        """Infer the resource type from an ARN string."""
        type_mapping = {
            "ec2": "ec2",
            "lambda": "lambda",
            "s3": "s3",
            "rds": "rds",
            "iam": "iam_role",
            "elasticloadbalancing": "alb",
            "ecs": "ecs",
            "sns": "sns",
            "sqs": "sqs",
            "dynamodb": "dynamodb",
        }

        # Parse service from ARN: arn:aws:SERVICE:region:account:...
        parts = arn.split(":")
        if len(parts) >= 3:
            service = parts[2]
            # Refine ELB type
            if service == "elasticloadbalancing":
                if "loadbalancer/net/" in arn:
                    return "nlb"
                return "alb"
            # Refine EC2 subtypes
            if service == "ec2":
                if "security-group/" in arn:
                    return "security_group"
                if "vpc/" in arn:
                    return "vpc"
                if "subnet/" in arn:
                    return "subnet"
                return "ec2"
            return type_mapping.get(service, "unknown")

        return "unknown"

    def _infer_name_from_arn(self, arn: str) -> str:
        """Infer a display name from an ARN string."""
        # Try to extract the resource identifier from the end of the ARN
        parts = arn.split(":")
        if len(parts) >= 6:
            resource_part = parts[-1]
            # Handle formats like "function/my-func" or "instance/i-1234"
            if "/" in resource_part:
                return resource_part.split("/")[-1]
            return resource_part

        # S3 bucket ARN format: arn:aws:s3:::bucket-name
        if arn.startswith("arn:aws:s3:::"):
            return arn.replace("arn:aws:s3:::", "")

        return arn.split("/")[-1] if "/" in arn else arn

    def _infer_region_from_arn(self, arn: str) -> str:
        """Infer the region from an ARN string."""
        parts = arn.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return "global"
