"""Pydantic models for the pre-computed AWS infrastructure hierarchy tree."""

from typing import Literal

from pydantic import BaseModel


class ContainerMetadata(BaseModel):
    """Metadata for a single container in the hierarchy tree."""

    id: str  # Unique container ID (e.g., "vpc-abc123")
    name: str  # Display label
    type: Literal["cloud", "account", "region", "vpc", "az", "subnet"]
    parent_id: str | None = None  # Parent container ID (None for root)
    subnet_type: Literal["public", "private"] | None = None  # Only for subnet containers
    icon_key: str  # Key for icon resolver
    resources: list[str] = []  # Resource ARNs assigned to this container
    children: list[str] = []  # Child container IDs


class BoundaryServicePlacement(BaseModel):
    """Positioning hint for a boundary service."""

    resource_arn: str
    boundary_type: Literal["igw", "nat", "waf", "vpn"]
    inner_container_id: str  # Container the service is "inside"
    outer_container_id: str | None = None  # Container the service is "outside" (None if N/A)
    edge_position: Literal["top", "bottom", "left", "right"] = "top"


class HierarchyTree(BaseModel):
    """Pre-computed hierarchy tree for the architecture diagram."""

    containers: list[ContainerMetadata]
    root_id: str  # ID of the top-level "cloud" container
    boundary_services: list[BoundaryServicePlacement] = []
