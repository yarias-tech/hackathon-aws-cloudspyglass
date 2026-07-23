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
        """Resolve network relationships between all scanned resource types.

        Detects:
        - EC2 → Security Group, VPC, Subnet
        - EBS → EC2 (attached volume)
        - Elastic IP → EC2 (associated instance)
        - Elastic IP → Network Interface
        - Lambda → VPC, Subnet, Security Group
        - RDS → VPC, Security Group
        - ALB/NLB → VPC, Targets
        - NAT Gateway → VPC, Subnet
        - VPN Gateway → VPC
        - EKS → VPC
        - ElastiCache → VPC (inferred from subnet group)
        - OpenSearch → VPC
        - Redshift → VPC
        - Security Group → VPC
        - Subnet → VPC
        - Transit Gateway attachments
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

            elif resource.resource_type == "ebs":
                # EBS → EC2 (volume attached to instance)
                instance_id = attrs.get("attached_to")
                if instance_id:
                    instance_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:instance/{instance_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=instance_arn,
                        category="network",
                        derived_from="Attachments[].InstanceId",
                    ))

            elif resource.resource_type == "elastic_ip":
                # Elastic IP → EC2 (EIP associated with instance)
                instance_id = attrs.get("instance_id")
                if instance_id:
                    instance_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:instance/{instance_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=instance_arn,
                        category="network",
                        derived_from="InstanceId",
                    ))

                # Elastic IP → Network Interface
                eni_id = attrs.get("network_interface_id")
                if eni_id:
                    eni_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:network-interface/{eni_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=eni_arn,
                        category="network",
                        derived_from="NetworkInterfaceId",
                    ))

            elif resource.resource_type == "security_group":
                # Security Group → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

            elif resource.resource_type == "subnet":
                # Subnet → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
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

                # Lambda → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="VpcConfig.SecurityGroupIds[]",
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

                # RDS → Security Groups (if stored)
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="VpcSecurityGroups[].VpcSecurityGroupId",
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

                # ALB/NLB → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="SecurityGroups[]",
                    ))

                # ALB/NLB → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="AvailabilityZones[].SubnetId",
                    ))

                # ALB/NLB → Targets (EC2 instances, Lambda functions)
                target_arns = attrs.get("target_arns", [])
                for target_arn in target_arns:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="network",
                        derived_from="TargetGroups[].Targets[]",
                    ))

                # ALB/NLB → S3 (access logs bucket)
                access_logs_bucket = attrs.get("access_logs_bucket")
                if access_logs_bucket:
                    bucket_arn = f"arn:aws:s3:::{access_logs_bucket}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=bucket_arn,
                        category="data",
                        derived_from="AccessLogs.S3Bucket",
                    ))

            elif resource.resource_type == "nat_gateway":
                # NAT Gateway → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

                # NAT Gateway → Subnet
                subnet_id = attrs.get("subnet_id")
                if subnet_id:
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="SubnetId",
                    ))

                # NAT Gateway → Elastic IPs
                for alloc_id in attrs.get("elastic_ip_allocation_ids", []):
                    eip_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:elastic-ip/{alloc_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=eip_arn,
                        category="network",
                        derived_from="NatGatewayAddresses[].AllocationId",
                    ))

            elif resource.resource_type == "vpn_gateway":
                # VPN Gateway → VPC
                vpc_id = attrs.get("attached_vpc")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcAttachments[].VpcId",
                    ))

            elif resource.resource_type == "eks":
                # EKS → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="resourcesVpcConfig.vpcId",
                    ))

                # EKS → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="resourcesVpcConfig.subnetIds[]",
                    ))

                # EKS → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="resourcesVpcConfig.securityGroupIds[]",
                    ))

            elif resource.resource_type == "ecs":
                # ECS → ALB/NLB (services with load balancer configuration)
                for lb_arn in attrs.get("load_balancer_arns", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=lb_arn,
                        category="network",
                        derived_from="Services[].LoadBalancers[].TargetGroupArn",
                    ))

            elif resource.resource_type == "elasticache":
                # ElastiCache → VPC (inferred from subnet group or direct attribute)
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="CacheSubnetGroup.VpcId",
                    ))

                # ElastiCache → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="SecurityGroups[].SecurityGroupId",
                    ))

            elif resource.resource_type == "opensearch":
                # OpenSearch → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VPCOptions.VPCId",
                    ))

                # OpenSearch → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="VPCOptions.SubnetIds[]",
                    ))

                # OpenSearch → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="VPCOptions.SecurityGroupIds[]",
                    ))

            elif resource.resource_type == "redshift":
                # Redshift → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

                # Redshift → Security Groups
                for sg_id in attrs.get("security_group_ids", []):
                    sg_arn = self._build_sg_arn(sg_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=sg_arn,
                        category="network",
                        derived_from="VpcSecurityGroups[].VpcSecurityGroupId",
                    ))

            elif resource.resource_type == "api_gateway":
                # API Gateway → VPC Link (if VPC-integrated)
                vpc_link_id = attrs.get("vpc_link_id")
                if vpc_link_id:
                    vpc_link_arn = f"arn:aws:apigateway:{resource.region}::/vpclinks/{vpc_link_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_link_arn,
                        category="network",
                        derived_from="VpcLinkId",
                    ))

            elif resource.resource_type == "cloudfront":
                # CloudFront → S3 (origin buckets)
                for origin_arn in attrs.get("origin_arns", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=origin_arn,
                        category="network",
                        derived_from="Origins[].DomainName",
                    ))

                # CloudFront → ALB/NLB (origin load balancers by DNS name)
                for origin_dns in attrs.get("origin_lb_arns", []):
                    # Resolve DNS name to a load balancer ARN in our index
                    resolved_arn = self._resolve_lb_by_dns(origin_dns)
                    if resolved_arn:
                        relationships.append(Relationship(
                            source_arn=resource.arn,
                            target_arn=resolved_arn,
                            category="network",
                            derived_from="Origins[].DomainName",
                        ))

                # CloudFront → S3 (logging bucket)
                logging_bucket = attrs.get("logging_bucket")
                if logging_bucket:
                    bucket_arn = f"arn:aws:s3:::{logging_bucket}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=bucket_arn,
                        category="data",
                        derived_from="Logging.Bucket",
                    ))

            elif resource.resource_type == "route53":
                # Route53 → ALB/NLB/CloudFront/S3 (alias targets by DNS name)
                for alias_dns in attrs.get("alias_targets", []):
                    resolved_arn = self._resolve_by_dns(alias_dns)
                    if resolved_arn:
                        relationships.append(Relationship(
                            source_arn=resource.arn,
                            target_arn=resolved_arn,
                            category="network",
                            derived_from="AliasTarget.DNSName",
                        ))

            elif resource.resource_type == "asg":
                # ASG → EC2 instances
                for instance_id in attrs.get("instance_ids", []):
                    instance_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:instance/{instance_id}"
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=instance_arn,
                        category="network",
                        derived_from="Instances[].InstanceId",
                    ))

                # ASG → Target Groups
                for tg_arn in attrs.get("target_group_arns", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=tg_arn,
                        category="network",
                        derived_from="TargetGroupARNs[]",
                    ))

                # ASG → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="network",
                        derived_from="VPCZoneIdentifier",
                    ))

            elif resource.resource_type == "target_group":
                # Target Group → ALB/NLB (load balancers it's attached to)
                for lb_arn in attrs.get("load_balancer_arns", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=lb_arn,
                        category="network",
                        derived_from="LoadBalancerArns[]",
                    ))

                # Target Group → EC2 instances / Lambda (registered targets)
                target_type = attrs.get("target_type", "instance")
                for target_id in attrs.get("target_ids", []):
                    if target_type == "instance":
                        target_arn = f"arn:aws:ec2:{resource.region}:{self._account_id}:instance/{target_id}"
                    elif target_type == "lambda":
                        target_arn = target_id  # Already an ARN
                    else:
                        continue  # Skip IP targets
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="network",
                        derived_from="Targets[].Id",
                    ))

                # Target Group → VPC
                vpc_id = attrs.get("vpc_id")
                if vpc_id:
                    vpc_arn = self._build_vpc_arn(vpc_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=vpc_arn,
                        category="network",
                        derived_from="VpcId",
                    ))

        return relationships

    def _resolve_iam_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve IAM relationships: role associations for all services.

        Detects:
        - EC2 → IAM Role (from IamInstanceProfile.Arn)
        - Lambda → IAM Role (from Role)
        - ECS → IAM Role (from TaskDefinition.TaskRoleArn)
        - EKS → IAM Role (from roleArn)
        - Step Functions → IAM Role (from roleArn)
        - Glue → IAM Role (from Role)
        - Kinesis → IAM Role (if configured)
        - CodePipeline → IAM Role (if configured)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            # Generic iam_role field — covers EC2, Lambda, ECS, EKS, Step Functions, Glue
            if resource.iam_role:
                if resource.resource_type == "ec2":
                    derived = "IamInstanceProfile.Arn"
                elif resource.resource_type == "lambda":
                    derived = "Role"
                elif resource.resource_type == "ecs":
                    derived = "TaskDefinition.TaskRoleArn"
                elif resource.resource_type == "eks":
                    derived = "Cluster.RoleArn"
                elif resource.resource_type == "step_functions":
                    derived = "StateMachine.RoleArn"
                elif resource.resource_type == "glue":
                    derived = "Job.Role"
                else:
                    derived = "IamRole"

                relationships.append(Relationship(
                    source_arn=resource.arn,
                    target_arn=resource.iam_role,
                    category="iam",
                    derived_from=derived,
                ))

            # ECS task execution role (separate from task role)
            if resource.resource_type == "ecs":
                exec_role = resource.attributes.get("execution_role_arn")
                if exec_role:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=exec_role,
                        category="iam",
                        derived_from="TaskDefinition.ExecutionRoleArn",
                    ))

        return relationships

    def _resolve_event_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve event-driven relationships between services.

        Detects:
        - SQS → Lambda (from EventSourceMappings)
        - SNS → Lambda/SQS/HTTP (from Subscriptions)
        - S3 → Lambda/SQS/SNS (from NotificationConfiguration)
        - Kinesis → Lambda (from EventSourceMappings)
        - DynamoDB → Lambda (from DynamoDB Streams)
        - API Gateway → Lambda (from integrations)
        - CloudFront → Lambda@Edge (from function associations)
        - Step Functions → Lambda/ECS/SNS/SQS (from state definitions)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            attrs = resource.attributes

            if resource.resource_type == "sqs":
                # SQS → Lambda (event source mappings)
                for target_arn in attrs.get("event_source_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="EventSourceMappings[].FunctionArn",
                    ))

                # SQS dead letter queue → source SQS
                dlq_arn = attrs.get("dead_letter_target_arn")
                if dlq_arn:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=dlq_arn,
                        category="event",
                        derived_from="RedrivePolicy.deadLetterTargetArn",
                    ))

            elif resource.resource_type == "sns":
                # SNS → subscribers (Lambda, SQS, HTTP endpoints)
                for endpoint_arn in attrs.get("subscription_endpoints", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=endpoint_arn,
                        category="event",
                        derived_from="Subscriptions[].Endpoint",
                    ))

            elif resource.resource_type == "s3":
                # S3 → Lambda/SQS/SNS (event notifications)
                for target_arn in attrs.get("notification_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="NotificationConfiguration",
                    ))

            elif resource.resource_type == "kinesis":
                # Kinesis → Lambda (event source mappings)
                for target_arn in attrs.get("event_source_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="EventSourceMappings[].FunctionArn",
                    ))

            elif resource.resource_type == "dynamodb":
                # DynamoDB → Lambda (streams)
                for target_arn in attrs.get("stream_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="StreamSpecification.StreamArn",
                    ))

            elif resource.resource_type == "api_gateway":
                # API Gateway → Lambda/HTTP integrations
                for target_arn in attrs.get("integration_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="Integrations[].Uri",
                    ))

            elif resource.resource_type == "step_functions":
                # Step Functions → referenced services (Lambda, ECS, SNS, SQS, DynamoDB)
                for target_arn in attrs.get("referenced_resources", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="event",
                        derived_from="States[].Resource",
                    ))

            elif resource.resource_type == "lambda":
                # Lambda → event source mappings (the sources that trigger it)
                for source_arn in attrs.get("event_source_arns", []):
                    relationships.append(Relationship(
                        source_arn=source_arn,
                        target_arn=resource.arn,
                        category="event",
                        derived_from="EventSourceMapping.EventSourceArn",
                    ))

        return relationships

    def _resolve_data_relationships(
        self, resources: list[Resource]
    ) -> list[Relationship]:
        """Resolve data-layer relationships between services.

        Detects:
        - RDS → Subnet (from DBSubnetGroup)
        - ElastiCache → Subnet (from CacheSubnetGroup)
        - Redshift → Subnet (from ClusterSubnetGroup)
        - OpenSearch → Subnet (from VPCOptions)
        - S3 → S3 (replication targets)
        - DynamoDB → S3 (export targets)
        - DynamoDB → KMS (encryption key)
        - RDS → KMS (encryption key)
        - EBS → KMS (encryption key)
        - Secrets Manager → KMS (encryption key)
        - ECR → KMS (encryption key)
        - Lambda → DynamoDB/S3/SQS/SNS (environment variable references)
        """
        relationships: list[Relationship] = []

        for resource in resources:
            attrs = resource.attributes

            if resource.resource_type == "rds":
                # RDS → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="data",
                        derived_from="DBSubnetGroup.Subnets[].SubnetIdentifier",
                    ))

                # RDS → KMS encryption key
                kms_key = attrs.get("kms_key_id")
                if kms_key:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=kms_key,
                        category="data",
                        derived_from="KmsKeyId",
                    ))

            elif resource.resource_type == "elasticache":
                # ElastiCache → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="data",
                        derived_from="CacheSubnetGroup.Subnets[]",
                    ))

            elif resource.resource_type == "redshift":
                # Redshift → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="data",
                        derived_from="ClusterSubnetGroup.Subnets[]",
                    ))

                # Redshift → KMS
                kms_key = attrs.get("kms_key_id")
                if kms_key:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=kms_key,
                        category="data",
                        derived_from="KmsKeyId",
                    ))

            elif resource.resource_type == "opensearch":
                # OpenSearch → Subnets
                for subnet_id in attrs.get("subnet_ids", []):
                    subnet_arn = self._build_subnet_arn(subnet_id, resource.region)
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=subnet_arn,
                        category="data",
                        derived_from="VPCOptions.SubnetIds[]",
                    ))

            elif resource.resource_type == "ebs":
                # EBS → KMS (if encrypted)
                kms_key = attrs.get("kms_key_id")
                if kms_key:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=kms_key,
                        category="data",
                        derived_from="KmsKeyId",
                    ))

            elif resource.resource_type == "secrets_manager":
                # Secrets Manager → KMS
                kms_key = attrs.get("kms_key_id")
                if kms_key:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=kms_key,
                        category="data",
                        derived_from="KmsKeyId",
                    ))

            elif resource.resource_type == "s3":
                # S3 → replication target buckets
                for target_arn in attrs.get("replication_targets", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=target_arn,
                        category="data",
                        derived_from="ReplicationConfiguration.Rules[].Destination.Bucket",
                    ))

            elif resource.resource_type == "lambda":
                # Lambda → referenced resources from environment variables
                for ref_arn in attrs.get("environment_resource_arns", []):
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=ref_arn,
                        category="data",
                        derived_from="Environment.Variables",
                    ))

            elif resource.resource_type == "ecr":
                # ECR → KMS
                kms_key = attrs.get("kms_key_arn")
                if kms_key:
                    relationships.append(Relationship(
                        source_arn=resource.arn,
                        target_arn=kms_key,
                        category="data",
                        derived_from="encryptionConfiguration.kmsKey",
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

    def _resolve_lb_by_dns(self, dns_name: str) -> str | None:
        """Resolve a load balancer DNS name to its ARN from the scan index.

        Args:
            dns_name: ELB DNS name (e.g., 'my-lb-123456.us-east-1.elb.amazonaws.com')

        Returns:
            The ARN of the matching load balancer, or None if not found.
        """
        dns_lower = dns_name.lower().rstrip(".")
        for arn, resource in self._arn_index.items():
            if resource.resource_type in ("alb", "nlb"):
                res_dns = resource.attributes.get("dns_name", "")
                if res_dns and res_dns.lower().rstrip(".") == dns_lower:
                    return arn
        return None

    def _resolve_by_dns(self, dns_name: str) -> str | None:
        """Resolve a DNS name to the ARN of a matching resource in the scan index.

        Handles ALB/NLB DNS names, CloudFront domain names, and S3 website endpoints.

        Args:
            dns_name: DNS name to resolve.

        Returns:
            The ARN of the matching resource, or None if not found.
        """
        dns_lower = dns_name.lower().rstrip(".")

        # Try load balancers first
        lb_arn = self._resolve_lb_by_dns(dns_name)
        if lb_arn:
            return lb_arn

        # Try CloudFront distributions
        for arn, resource in self._arn_index.items():
            if resource.resource_type == "cloudfront":
                cf_domain = resource.attributes.get("domain_name", "")
                if cf_domain and cf_domain.lower().rstrip(".") == dns_lower:
                    return arn

        # Try S3 website endpoints: <bucket>.s3-website-<region>.amazonaws.com
        # or <bucket>.s3.amazonaws.com
        if ".s3" in dns_lower and ".amazonaws.com" in dns_lower:
            bucket_name = dns_lower.split(".s3")[0]
            bucket_arn = f"arn:aws:s3:::{bucket_name}"
            if bucket_arn in self._arn_index:
                return bucket_arn

        return None

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
            "autoscaling": "asg",
            "elasticache": "elasticache",
        }

        # Parse service from ARN: arn:aws:SERVICE:region:account:...
        parts = arn.split(":")
        if len(parts) >= 3:
            service = parts[2]
            # Refine ELB type
            if service == "elasticloadbalancing":
                if "loadbalancer/net/" in arn:
                    return "nlb"
                if "targetgroup/" in arn:
                    return "target_group"
                return "alb"
            # Refine EC2 subtypes
            if service == "ec2":
                if "security-group/" in arn:
                    return "security_group"
                if "vpc/" in arn:
                    return "vpc"
                if "subnet/" in arn:
                    return "subnet"
                if "elastic-ip/" in arn:
                    return "elastic_ip"
                if "natgateway/" in arn:
                    return "nat_gateway"
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
