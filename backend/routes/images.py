"""API routes for serving static image assets (icons and logo)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..exceptions import CloudSpyglassError

router = APIRouter(prefix="/api/images", tags=["images"])

# Project root is two levels up from this file (backend/routes/images.py → project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Base paths for assets
_ICONS_BASE = _PROJECT_ROOT / "assets" / "icons"
_LOGO_PATH = _PROJECT_ROOT / "assets" / "logo" / "logo.PNG"

# Architecture-Service-Icons base directory
_ARCH_ICONS = _ICONS_BASE / "Architecture-Service-Icons_07312025"
_RES_ICONS = _ICONS_BASE / "Resource-Icons_07312025"

# Known resource types supported by CloudSpyglass
KNOWN_RESOURCE_TYPES: set[str] = {
    "ec2",
    "lambda",
    "s3",
    "rds",
    "dynamodb",
    "vpc",
    "subnet",
    "security_group",
    "alb",
    "nlb",
    "ecs",
    "sns",
    "sqs",
    "cloudfront",
    "route53",
    "apigateway",
    "iam_role",
}

# Mapping of service_type → relative SVG file path from project root
ICON_PATH_MAP: dict[str, Path] = {
    "ec2": _ARCH_ICONS / "Arch_Compute" / "48" / "Arch_Amazon-EC2_48.svg",
    "lambda": _ARCH_ICONS / "Arch_Compute" / "48" / "Arch_AWS-Lambda_48.svg",
    "s3": _ARCH_ICONS / "Arch_Storage" / "48" / "Arch_Amazon-Simple-Storage-Service_48.svg",
    "rds": _ARCH_ICONS / "Arch_Database" / "48" / "Arch_Amazon-RDS_48.svg",
    "dynamodb": _ARCH_ICONS / "Arch_Database" / "48" / "Arch_Amazon-DynamoDB_48.svg",
    "vpc": (
        _ARCH_ICONS
        / "Arch_Networking-Content-Delivery"
        / "48"
        / "Arch_Amazon-Virtual-Private-Cloud_48.svg"
    ),
    "cloudfront": (
        _ARCH_ICONS
        / "Arch_Networking-Content-Delivery"
        / "48"
        / "Arch_Amazon-CloudFront_48.svg"
    ),
    "route53": (
        _ARCH_ICONS
        / "Arch_Networking-Content-Delivery"
        / "48"
        / "Arch_Amazon-Route-53_48.svg"
    ),
    "apigateway": (
        _ARCH_ICONS
        / "Arch_Networking-Content-Delivery"
        / "48"
        / "Arch_Amazon-API-Gateway_48.svg"
    ),
    "alb": (
        _RES_ICONS
        / "Res_Networking-Content-Delivery"
        / "Res_Elastic-Load-Balancing_Application-Load-Balancer_48.svg"
    ),
    "nlb": (
        _RES_ICONS
        / "Res_Networking-Content-Delivery"
        / "Res_Elastic-Load-Balancing_Network-Load-Balancer_48.svg"
    ),
    "ecs": (
        _ARCH_ICONS
        / "Arch_Containers"
        / "48"
        / "Arch_Amazon-Elastic-Container-Service_48.svg"
    ),
    "sns": (
        _ARCH_ICONS
        / "Arch_App-Integration"
        / "48"
        / "Arch_Amazon-Simple-Notification-Service_48.svg"
    ),
    "sqs": (
        _ARCH_ICONS
        / "Arch_App-Integration"
        / "48"
        / "Arch_Amazon-Simple-Queue-Service_48.svg"
    ),
    "iam_role": (
        _ARCH_ICONS
        / "Arch_Security-Identity-Compliance"
        / "48"
        / "Arch_AWS-Identity-and-Access-Management_48.svg"
    ),
    "subnet": (
        _RES_ICONS
        / "Res_Networking-Content-Delivery"
        / "Res_Amazon-VPC_Virtual-private-cloud-VPC_48.svg"
    ),
    "security_group": (
        _ARCH_ICONS
        / "Arch_Security-Identity-Compliance"
        / "48"
        / "Arch_AWS-Network-Firewall_48.svg"
    ),
}


@router.get("/icons/{service_type}")
async def get_service_icon(service_type: str) -> FileResponse:
    """Serve the SVG icon for a given AWS service type.

    Validates the service_type against known resource types and returns
    the corresponding SVG file with appropriate Content-Type headers.

    Requirements: 13.1, 13.2, 13.3, 13.6
    """
    if service_type not in KNOWN_RESOURCE_TYPES:
        raise CloudSpyglassError(
            error_code="INVALID_SERVICE_TYPE",
            message=f"Unknown service type: '{service_type}'",
            details=f"Valid service types are: {', '.join(sorted(KNOWN_RESOURCE_TYPES))}",
            recoverable=False,
            status_code=400,
        )

    icon_path = ICON_PATH_MAP.get(service_type)
    if icon_path is None or not icon_path.is_file():
        raise CloudSpyglassError(
            error_code="ICON_NOT_FOUND",
            message=f"Icon file not found for service type: '{service_type}'",
            details=f"Expected file at: {icon_path}",
            recoverable=False,
            status_code=404,
        )

    return FileResponse(
        path=str(icon_path),
        media_type="image/svg+xml",
    )


@router.get("/logo")
async def get_logo() -> FileResponse:
    """Serve the CloudSpyglass application logo.

    Returns the logo PNG file with appropriate Content-Type headers.

    Requirements: 13.7
    """
    if not _LOGO_PATH.is_file():
        raise CloudSpyglassError(
            error_code="ICON_NOT_FOUND",
            message="Application logo file not found",
            details=f"Expected file at: {_LOGO_PATH}",
            recoverable=False,
            status_code=404,
        )

    return FileResponse(
        path=str(_LOGO_PATH),
        media_type="image/png",
    )
