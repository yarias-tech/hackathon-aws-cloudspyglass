"""Pydantic models for AI architecture advisor suggestions and requests."""

from typing import Literal

from pydantic import BaseModel, Field


class Suggestion(BaseModel):
    """A single architecture recommendation from the AI advisor."""

    pillar: Literal["Security", "Cost_Optimization", "Performance"]
    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=2000)
    severity: Literal["critical", "high", "medium", "low"]
    affected_resources: list[str] = Field(default_factory=list, max_length=50)
    remediation: str = Field(..., max_length=2000)
    estimated_impact: str | None = None  # Cost_Optimization only


class AdvisorResponse(BaseModel):
    """Complete response from an architecture analysis run."""

    suggestions: list[Suggestion] = Field(default_factory=list, max_length=50)
    task_id: str
    status: Literal["idle", "in_progress", "completed", "failed"]
    error: str | None = None


class AdvisorStatus(BaseModel):
    """Current state of the advisor analysis task."""

    status: Literal["idle", "in_progress", "completed", "failed"]
    task_id: str | None = None


class AnalyzeRequest(BaseModel):
    """Request payload for triggering an architecture analysis."""

    pillars: list[Literal["Security", "Cost_Optimization", "Performance"]] | None = Field(
        None, max_length=3
    )
