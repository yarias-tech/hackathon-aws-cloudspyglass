"""Pydantic models for diagram node/edge representation."""

from typing import Literal

from pydantic import BaseModel

from .scan import RegionFailure


class DiagramNode(BaseModel):
    """A node in the infrastructure diagram (represents one resource)."""

    id: str  # ARN
    resource_type: str
    name: str
    region: str
    is_external: bool = False
    is_unresolved: bool = False
    icon_url: str  # /api/images/icons/{service_type}


class DiagramEdge(BaseModel):
    """An edge in the infrastructure diagram (represents one relationship)."""

    id: str  # source_arn + target_arn hash
    source: str  # source ARN
    target: str  # target ARN
    category: Literal["network", "iam", "event", "data"]
    derived_from: str
    label: str | None = None


class DiagramData(BaseModel):
    """Complete diagram payload sent to the frontend."""

    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    account_id: str
    scan_timestamp: str
    total_resources: int
    scanned_regions: list[str]
    failures: list[RegionFailure] = []
