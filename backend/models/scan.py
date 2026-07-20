"""Pydantic models for scan operations and results."""

from pydantic import BaseModel

from .resources import Relationship, Resource


class ScanRequest(BaseModel):
    """Request payload for triggering a scan."""

    regions: list[str] | None = None  # None = all enabled regions


class RegionFailure(BaseModel):
    """Records a failure encountered while scanning a specific region."""

    region: str
    resource_type: str
    error_message: str
    timestamp: str  # ISO 8601


class ScanResult(BaseModel):
    """Complete result of a multi-region infrastructure scan."""

    account_id: str
    scan_timestamp: str  # ISO 8601
    resources: list[Resource]
    relationships: list[Relationship]
    failures: list[RegionFailure] = []
    scanned_regions: list[str]
    total_scan_duration_ms: int
