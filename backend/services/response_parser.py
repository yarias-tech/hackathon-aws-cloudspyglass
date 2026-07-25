"""Response parser for AI architecture advisor output."""

import json
import logging
from typing import Any

from ..exceptions import CloudSpyglassError
from ..models.advisor import AdvisorResponse, Suggestion

logger = logging.getLogger(__name__)

VALID_PILLARS = {"Security", "Cost_Optimization", "Performance"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_REMEDIATION_LENGTH = 2000
MAX_SUGGESTIONS = 50

REQUIRED_FIELDS = {"pillar", "title", "description", "severity", "affected_resources", "remediation"}


class ResponseParser:
    """Parses and validates AI response into structured suggestions."""

    def parse(self, raw_content: str, valid_arns: set[str]) -> AdvisorResponse:
        """Parse raw AI response JSON into a validated AdvisorResponse.

        Args:
            raw_content: Raw JSON string from the AI response.
            valid_arns: Set of ARNs from the original ScanResult.

        Returns:
            AdvisorResponse with validated and sorted suggestions.

        Raises:
            CloudSpyglassError: If the response is not valid JSON.
        """
        data = self._parse_json(raw_content)
        raw_suggestions = self._extract_suggestions(data)

        suggestions: list[Suggestion] = []
        for raw in raw_suggestions:
            suggestion = self._validate_and_build(raw, valid_arns)
            if suggestion is not None:
                suggestions.append(suggestion)

        # Cap at 50 suggestions
        suggestions = suggestions[:MAX_SUGGESTIONS]

        # Sort by severity descending then title ascending
        suggestions.sort(key=lambda s: (SEVERITY_ORDER[s.severity], s.title))

        return AdvisorResponse(
            suggestions=suggestions,
            task_id="",
            status="completed",
        )

    def _parse_json(self, raw_content: str) -> Any:
        """Parse raw string as JSON."""
        try:
            return json.loads(raw_content)
        except (json.JSONDecodeError, TypeError) as e:
            raise CloudSpyglassError(
                error_code="AI_RESPONSE_PARSE_ERROR",
                message="Failed to parse AI response as JSON",
                details=str(e),
                recoverable=False,
                status_code=500,
            )

    def _extract_suggestions(self, data: Any) -> list[dict[str, Any]]:
        """Extract the list of suggestion dicts from parsed JSON."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try common response structures
            if "suggestions" in data and isinstance(data["suggestions"], list):
                return data["suggestions"]
            # Fallback: treat the dict as a single suggestion
            return [data]
        raise CloudSpyglassError(
            error_code="AI_RESPONSE_PARSE_ERROR",
            message="AI response is not a valid JSON structure",
            details="Expected a JSON array or object with a 'suggestions' key",
            recoverable=False,
            status_code=500,
        )

    def _validate_and_build(
        self, raw: Any, valid_arns: set[str]
    ) -> Suggestion | None:
        """Validate a single suggestion dict and return a Suggestion or None."""
        if not isinstance(raw, dict):
            logger.warning("Discarding suggestion: not a JSON object")
            return None

        # Check required fields
        missing = REQUIRED_FIELDS - raw.keys()
        if missing:
            logger.warning("Discarding suggestion: missing required fields %s", missing)
            return None

        pillar = raw.get("pillar")
        severity = raw.get("severity")

        # Validate pillar
        if pillar not in VALID_PILLARS:
            logger.warning(
                "Discarding suggestion with unrecognized pillar: %r", pillar
            )
            return None

        # Validate severity
        if severity not in VALID_SEVERITIES:
            logger.warning(
                "Discarding suggestion with unrecognized severity: %r", severity
            )
            return None

        # Truncate fields
        title = self._truncate(str(raw.get("title", "")), MAX_TITLE_LENGTH)
        description = self._truncate(str(raw.get("description", "")), MAX_DESCRIPTION_LENGTH)
        remediation = self._truncate(str(raw.get("remediation", "")), MAX_REMEDIATION_LENGTH)

        # Filter ARNs against valid set
        affected_resources = raw.get("affected_resources", [])
        if not isinstance(affected_resources, list):
            affected_resources = []
        filtered_arns = [arn for arn in affected_resources if arn in valid_arns]

        # Build optional fields
        estimated_impact = raw.get("estimated_impact")
        if estimated_impact is not None:
            estimated_impact = str(estimated_impact)

        return Suggestion(
            pillar=pillar,
            title=title,
            description=description,
            severity=severity,
            affected_resources=filtered_arns,
            remediation=remediation,
            estimated_impact=estimated_impact,
        )

    def _truncate(self, value: str, max_length: int) -> str:
        """Truncate a string to max_length characters."""
        if len(value) > max_length:
            return value[:max_length]
        return value
