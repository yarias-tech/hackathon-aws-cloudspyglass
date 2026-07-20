"""Pydantic models for diagram export operations."""

from enum import Enum

from pydantic import BaseModel

from .filters import FilterCriteria


class ExportFormat(str, Enum):
    """Supported export file formats."""

    PDF = "pdf"
    PNG = "png"
    SVG = "svg"


class ExportRequest(BaseModel):
    """Request payload for exporting a diagram."""

    format: ExportFormat
    filters: FilterCriteria | None = None


class ExportResult(BaseModel):
    """Result of a successful export operation."""

    filename: str
    format: ExportFormat
    size_bytes: int
    path: str
