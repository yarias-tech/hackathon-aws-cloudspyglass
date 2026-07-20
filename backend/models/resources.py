"""Pydantic models for AWS resources and relationships."""

from typing import Any, Literal

from pydantic import BaseModel


class Resource(BaseModel):
    """Represents a single discovered AWS resource."""

    arn: str
    resource_type: str  # e.g., "ec2", "lambda", "s3"
    name: str
    region: str
    tags: dict[str, str] = {}
    creation_date: str | None = None  # ISO 8601
    iam_role: str | None = None
    attributes: dict[str, Any] = {}  # service-specific metadata
    is_external: bool = False
    is_unresolved: bool = False


class Relationship(BaseModel):
    """A detected connection between two AWS resources."""

    source_arn: str
    target_arn: str
    category: Literal["network", "iam", "event", "data"]
    derived_from: str  # configuration property name
