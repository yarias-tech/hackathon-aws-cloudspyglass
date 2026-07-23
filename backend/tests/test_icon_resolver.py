"""Unit tests for the ArchitectureIconResolver service.

Validates:
- Requirements 2.1: Maps each supported resource type to an SVG icon from the 48/ subdirectory
- Requirements 2.3: Unknown resource type returns a generic placeholder icon
- Requirements 2.4: Maps container types to SVG icons from Architecture-Group-Icons_07312025
"""

import pytest

from backend.services.icon_resolver import ArchitectureIconResolver


@pytest.fixture
def resolver() -> ArchitectureIconResolver:
    """Create an ArchitectureIconResolver instance."""
    return ArchitectureIconResolver()


class TestServiceIconMapping:
    """Validates Requirement 2.1: Each supported resource type maps to correct SVG path."""

    @pytest.mark.parametrize(
        "resource_type,expected_path",
        [
            ("ec2", "assets/icons/Architecture-Service-Icons_07312025/Arch_Compute/48/Arch_Amazon-EC2_48.svg"),
            ("lambda", "assets/icons/Architecture-Service-Icons_07312025/Arch_Compute/48/Arch_AWS-Lambda_48.svg"),
            ("s3", "assets/icons/Architecture-Service-Icons_07312025/Arch_Storage/48/Arch_Amazon-Simple-Storage-Service_48.svg"),
            ("rds", "assets/icons/Architecture-Service-Icons_07312025/Arch_Database/48/Arch_Amazon-RDS_48.svg"),
            ("dynamodb", "assets/icons/Architecture-Service-Icons_07312025/Arch_Database/48/Arch_Amazon-DynamoDB_48.svg"),
            ("vpc", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_Amazon-Virtual-Private-Cloud_48.svg"),
            ("cloudfront", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_Amazon-CloudFront_48.svg"),
            ("route53", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_Amazon-Route-53_48.svg"),
            ("apigateway", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_Amazon-API-Gateway_48.svg"),
            ("api_gateway", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_Amazon-API-Gateway_48.svg"),
            ("ecs", "assets/icons/Architecture-Service-Icons_07312025/Arch_Containers/48/Arch_Amazon-Elastic-Container-Service_48.svg"),
            ("sns", "assets/icons/Architecture-Service-Icons_07312025/Arch_App-Integration/48/Arch_Amazon-Simple-Notification-Service_48.svg"),
            ("sqs", "assets/icons/Architecture-Service-Icons_07312025/Arch_App-Integration/48/Arch_Amazon-Simple-Queue-Service_48.svg"),
            ("iam_role", "assets/icons/Architecture-Service-Icons_07312025/Arch_Security-Identity-Compliance/48/Arch_AWS-Identity-and-Access-Management_48.svg"),
            ("eks", "assets/icons/Architecture-Service-Icons_07312025/Arch_Containers/48/Arch_Amazon-EKS-Cloud_48.svg"),
            ("elasticache", "assets/icons/Architecture-Service-Icons_07312025/Arch_Database/48/Arch_Amazon-ElastiCache_48.svg"),
            ("ebs", "assets/icons/Architecture-Service-Icons_07312025/Arch_Storage/48/Arch_Amazon-Elastic-Block-Store_48.svg"),
            ("nat_gateway", "assets/icons/Resource-Icons_07312025/Res_Networking-Content-Delivery/Res_Amazon-VPC_NAT-Gateway_48.svg"),
            ("transit_gateway", "assets/icons/Architecture-Service-Icons_07312025/Arch_Networking-Content-Delivery/48/Arch_AWS-Transit-Gateway_48.svg"),
            ("step_functions", "assets/icons/Architecture-Service-Icons_07312025/Arch_App-Integration/48/Arch_AWS-Step-Functions_48.svg"),
            ("kinesis", "assets/icons/Architecture-Service-Icons_07312025/Arch_Analytics/48/Arch_Amazon-Kinesis_48.svg"),
            ("secrets_manager", "assets/icons/Architecture-Service-Icons_07312025/Arch_Security-Identity-Compliance/48/Arch_AWS-Secrets-Manager_48.svg"),
            ("ecr", "assets/icons/Architecture-Service-Icons_07312025/Arch_Containers/48/Arch_Amazon-Elastic-Container-Registry_48.svg"),
            ("waf", "assets/icons/Architecture-Service-Icons_07312025/Arch_Security-Identity-Compliance/48/Arch_AWS-WAF_48.svg"),
            ("subnet", "assets/icons/Resource-Icons_07312025/Res_Networking-Content-Delivery/Res_Amazon-VPC_Virtual-private-cloud-VPC_48.svg"),
            ("security_group", "assets/icons/Architecture-Service-Icons_07312025/Arch_Security-Identity-Compliance/48/Arch_AWS-Network-Firewall_48.svg"),
            ("alb", "assets/icons/Resource-Icons_07312025/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Application-Load-Balancer_48.svg"),
            ("nlb", "assets/icons/Resource-Icons_07312025/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Network-Load-Balancer_48.svg"),
            ("elastic_ip", "assets/icons/Resource-Icons_07312025/Res_Compute/Res_Amazon-EC2_Elastic-IP-Address_48.svg"),
            ("vpn_gateway", "assets/icons/Resource-Icons_07312025/Res_Networking-Content-Delivery/Res_Amazon-VPC_VPN-Gateway_48.svg"),
            ("redshift", "assets/icons/Architecture-Service-Icons_07312025/Arch_Analytics/48/Arch_Amazon-Redshift_48.svg"),
            ("opensearch", "assets/icons/Architecture-Service-Icons_07312025/Arch_Analytics/48/Arch_Amazon-OpenSearch-Service_48.svg"),
            ("codepipeline", "assets/icons/Architecture-Service-Icons_07312025/Arch_Developer-Tools/48/Arch_AWS-CodePipeline_48.svg"),
            ("glue", "assets/icons/Architecture-Service-Icons_07312025/Arch_Analytics/48/Arch_AWS-Glue_48.svg"),
        ],
    )
    def test_service_icon_mapping(self, resolver: ArchitectureIconResolver, resource_type: str, expected_path: str):
        """Each supported resource type resolves to its correct SVG path."""
        assert resolver.resolve_service_icon(resource_type) == expected_path

    def test_all_service_icons_end_with_svg(self, resolver: ArchitectureIconResolver):
        """All service icon paths end with .svg extension."""
        for resource_type, path in ArchitectureIconResolver.SERVICE_ICON_MAP.items():
            result = resolver.resolve_service_icon(resource_type)
            assert result.endswith(".svg"), f"Icon for '{resource_type}' does not end with .svg: {result}"

    def test_service_icons_use_48px_directory(self, resolver: ArchitectureIconResolver):
        """Service icons come from 48px directories (either /48/ or _48.svg naming)."""
        for resource_type, path in ArchitectureIconResolver.SERVICE_ICON_MAP.items():
            result = resolver.resolve_service_icon(resource_type)
            assert "_48" in result or "/48/" in result, (
                f"Icon for '{resource_type}' does not reference 48px variant: {result}"
            )


class TestGroupIconMapping:
    """Validates Requirement 2.4: Each container type maps to correct group icon path."""

    @pytest.mark.parametrize(
        "container_type,expected_path",
        [
            ("cloud", "assets/icons/Architecture-Group-Icons_07312025/AWS-Cloud_32.svg"),
            ("account", "assets/icons/Architecture-Group-Icons_07312025/AWS-Account_32.svg"),
            ("region", "assets/icons/Architecture-Group-Icons_07312025/Region_32.svg"),
            ("vpc", "assets/icons/Architecture-Group-Icons_07312025/Virtual-private-cloud-VPC_32.svg"),
            ("public_subnet", "assets/icons/Architecture-Group-Icons_07312025/Public-subnet_32.svg"),
            ("private_subnet", "assets/icons/Architecture-Group-Icons_07312025/Private-subnet_32.svg"),
            ("az", "assets/icons/Architecture-Group-Icons_07312025/Region_32.svg"),
        ],
    )
    def test_group_icon_mapping(self, resolver: ArchitectureIconResolver, container_type: str, expected_path: str):
        """Each container type resolves to its correct group icon SVG path."""
        assert resolver.resolve_group_icon(container_type) == expected_path

    def test_all_group_icons_end_with_svg(self, resolver: ArchitectureIconResolver):
        """All group icon paths end with .svg extension."""
        for container_type, path in ArchitectureIconResolver.GROUP_ICON_MAP.items():
            result = resolver.resolve_group_icon(container_type)
            assert result.endswith(".svg"), f"Icon for '{container_type}' does not end with .svg: {result}"

    def test_group_icons_use_32px_directory(self, resolver: ArchitectureIconResolver):
        """Group icons come from the 32px Architecture-Group-Icons directory."""
        for container_type in ArchitectureIconResolver.GROUP_ICON_MAP:
            result = resolver.resolve_group_icon(container_type)
            assert "Architecture-Group-Icons_07312025" in result, (
                f"Icon for '{container_type}' not from group icons directory: {result}"
            )
            assert "_32" in result, f"Icon for '{container_type}' does not reference 32px variant: {result}"


class TestPlaceholderFallback:
    """Validates Requirement 2.3: Unknown resource type returns placeholder path."""

    def test_unknown_service_type_returns_placeholder(self, resolver: ArchitectureIconResolver):
        """Unknown resource type returns the placeholder icon path."""
        assert resolver.resolve_service_icon("unknown_service") == "assets/icons/placeholder.svg"

    def test_unknown_group_type_returns_placeholder(self, resolver: ArchitectureIconResolver):
        """Unknown container type returns the placeholder icon path."""
        assert resolver.resolve_group_icon("unknown_container") == "assets/icons/placeholder.svg"

    def test_empty_string_returns_placeholder_for_service(self, resolver: ArchitectureIconResolver):
        """Empty string resource type returns the placeholder icon path."""
        assert resolver.resolve_service_icon("") == "assets/icons/placeholder.svg"

    def test_empty_string_returns_placeholder_for_group(self, resolver: ArchitectureIconResolver):
        """Empty string container type returns the placeholder icon path."""
        assert resolver.resolve_group_icon("") == "assets/icons/placeholder.svg"

    def test_placeholder_ends_with_svg(self, resolver: ArchitectureIconResolver):
        """The placeholder path itself ends with .svg."""
        assert ArchitectureIconResolver.PLACEHOLDER.endswith(".svg")
