"""Pydantic models for tag and resource-type filtering."""

from pydantic import BaseModel, Field

from .diagram import DiagramData


class TagFilter(BaseModel):
    """A single tag key-value filter criterion."""

    key: str = Field(..., max_length=128)
    value: str = Field(..., max_length=256)


class FilterCriteria(BaseModel):
    """Complete filter state (tags + resource types)."""

    tag_filters: list[TagFilter] = Field(default_factory=list, max_length=10)
    type_filters: list[str] = []


class FilteredResult(BaseModel):
    """Diagram data after applying filter criteria."""

    diagram: DiagramData
    filtered_count: int
    total_count: int
    active_filters: FilterCriteria


class TagSuggestion(BaseModel):
    """A tag key-value pair with its frequency in the scan data."""

    key: str
    value: str
    count: int
