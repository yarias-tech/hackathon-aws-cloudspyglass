"""Maps AWS resource types and container types to their official architecture icon paths."""


class ArchitectureIconResolver:
    """Maps AWS resource types to their official architecture icon paths.

    Returns relative paths from the project root to SVG icon files.
    Service icons use 48px variants; group/container icons use 32px variants.

    Requirements: 2.1, 2.4
    """

    SERVICE_ICON_BASE = "assets/icons/Architecture-Service-Icons_07312025"
    GROUP_ICON_BASE = "assets/icons/Architecture-Group-Icons_07312025"
    RESOURCE_ICON_BASE = "assets/icons/Resource-Icons_07312025"
    PLACEHOLDER = "assets/icons/placeholder.svg"

    # Resource type → relative path to 48px SVG icon
    SERVICE_ICON_MAP: dict[str, str] = {
        "ec2": f"{SERVICE_ICON_BASE}/Arch_Compute/48/Arch_Amazon-EC2_48.svg",
        "lambda": f"{SERVICE_ICON_BASE}/Arch_Compute/48/Arch_AWS-Lambda_48.svg",
        "s3": f"{SERVICE_ICON_BASE}/Arch_Storage/48/Arch_Amazon-Simple-Storage-Service_48.svg",
        "rds": f"{SERVICE_ICON_BASE}/Arch_Database/48/Arch_Amazon-RDS_48.svg",
        "dynamodb": f"{SERVICE_ICON_BASE}/Arch_Database/48/Arch_Amazon-DynamoDB_48.svg",
        "vpc": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Amazon-Virtual-Private-Cloud_48.svg",
        "cloudfront": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Amazon-CloudFront_48.svg",
        "route53": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Amazon-Route-53_48.svg",
        "apigateway": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Amazon-API-Gateway_48.svg",
        "api_gateway": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Amazon-API-Gateway_48.svg",
        "ecs": f"{SERVICE_ICON_BASE}/Arch_Containers/48/Arch_Amazon-Elastic-Container-Service_48.svg",
        "sns": f"{SERVICE_ICON_BASE}/Arch_App-Integration/48/Arch_Amazon-Simple-Notification-Service_48.svg",
        "sqs": f"{SERVICE_ICON_BASE}/Arch_App-Integration/48/Arch_Amazon-Simple-Queue-Service_48.svg",
        "iam_role": f"{SERVICE_ICON_BASE}/Arch_Security-Identity-Compliance/48/Arch_AWS-Identity-and-Access-Management_48.svg",
        "eks": f"{SERVICE_ICON_BASE}/Arch_Containers/48/Arch_Amazon-EKS-Cloud_48.svg",
        "elasticache": f"{SERVICE_ICON_BASE}/Arch_Database/48/Arch_Amazon-ElastiCache_48.svg",
        "ebs": f"{SERVICE_ICON_BASE}/Arch_Storage/48/Arch_Amazon-Elastic-Block-Store_48.svg",
        "nat_gateway": f"{RESOURCE_ICON_BASE}/Res_Networking-Content-Delivery/Res_Amazon-VPC_NAT-Gateway_48.svg",
        "transit_gateway": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_AWS-Transit-Gateway_48.svg",
        "step_functions": f"{SERVICE_ICON_BASE}/Arch_App-Integration/48/Arch_AWS-Step-Functions_48.svg",
        "kinesis": f"{SERVICE_ICON_BASE}/Arch_Analytics/48/Arch_Amazon-Kinesis_48.svg",
        "secrets_manager": f"{SERVICE_ICON_BASE}/Arch_Security-Identity-Compliance/48/Arch_AWS-Secrets-Manager_48.svg",
        "ecr": f"{SERVICE_ICON_BASE}/Arch_Containers/48/Arch_Amazon-Elastic-Container-Registry_48.svg",
        "waf": f"{SERVICE_ICON_BASE}/Arch_Security-Identity-Compliance/48/Arch_AWS-WAF_48.svg",
        "subnet": f"{RESOURCE_ICON_BASE}/Res_Networking-Content-Delivery/Res_Amazon-VPC_Virtual-private-cloud-VPC_48.svg",
        "security_group": f"{SERVICE_ICON_BASE}/Arch_Security-Identity-Compliance/48/Arch_AWS-Network-Firewall_48.svg",
        "alb": f"{RESOURCE_ICON_BASE}/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Application-Load-Balancer_48.svg",
        "nlb": f"{RESOURCE_ICON_BASE}/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Network-Load-Balancer_48.svg",
        "elastic_ip": f"{RESOURCE_ICON_BASE}/Res_Compute/Res_Amazon-EC2_Elastic-IP-Address_48.svg",
        "vpn_gateway": f"{RESOURCE_ICON_BASE}/Res_Networking-Content-Delivery/Res_Amazon-VPC_VPN-Gateway_48.svg",
        "redshift": f"{SERVICE_ICON_BASE}/Arch_Analytics/48/Arch_Amazon-Redshift_48.svg",
        "opensearch": f"{SERVICE_ICON_BASE}/Arch_Analytics/48/Arch_Amazon-OpenSearch-Service_48.svg",
        "codepipeline": f"{SERVICE_ICON_BASE}/Arch_Developer-Tools/48/Arch_AWS-CodePipeline_48.svg",
        "glue": f"{SERVICE_ICON_BASE}/Arch_Analytics/48/Arch_AWS-Glue_48.svg",
        "asg": f"{SERVICE_ICON_BASE}/Arch_Compute/48/Arch_Amazon-EC2-Auto-Scaling_48.svg",
        "target_group": f"{SERVICE_ICON_BASE}/Arch_Networking-Content-Delivery/48/Arch_Elastic-Load-Balancing_48.svg",
    }

    # Container type → relative path to 32px SVG group icon
    GROUP_ICON_MAP: dict[str, str] = {
        "cloud": f"{GROUP_ICON_BASE}/AWS-Cloud_32.svg",
        "account": f"{GROUP_ICON_BASE}/AWS-Account_32.svg",
        "region": f"{GROUP_ICON_BASE}/Region_32.svg",
        "vpc": f"{GROUP_ICON_BASE}/Virtual-private-cloud-VPC_32.svg",
        "public_subnet": f"{GROUP_ICON_BASE}/Public-subnet_32.svg",
        "private_subnet": f"{GROUP_ICON_BASE}/Private-subnet_32.svg",
        "az": f"{GROUP_ICON_BASE}/Region_32.svg",
    }

    def resolve_service_icon(self, resource_type: str) -> str:
        """Return relative path to the 48px SVG icon for a service type.

        Args:
            resource_type: The AWS resource type key (e.g. "ec2", "lambda", "s3").

        Returns:
            Relative path from project root to the SVG icon file,
            or the placeholder path if no mapping exists.
        """
        return self.SERVICE_ICON_MAP.get(resource_type, self.PLACEHOLDER)

    def resolve_group_icon(self, container_type: str) -> str:
        """Return relative path to the 32px SVG group icon for a container type.

        Args:
            container_type: The container type key (e.g. "cloud", "vpc", "public_subnet").

        Returns:
            Relative path from project root to the SVG group icon file,
            or the placeholder path if no mapping exists.
        """
        return self.GROUP_ICON_MAP.get(container_type, self.PLACEHOLDER)
