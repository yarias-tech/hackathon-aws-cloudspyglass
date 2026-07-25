"""Context serializer for converting ScanResult into token-budget-aware AI prompts."""

import json
import os
from typing import Any

from ..exceptions import CloudSpyglassError
from ..models.resources import Relationship, Resource
from ..models.scan import ScanResult

# Attribute key substrings that define priority categories for truncation.
# HIGH priority: IAM, security, and encryption-related attributes (kept first).
_HIGH_PRIORITY_KEYWORDS = (
    "policy",
    "iam",
    "security_group",
    "ingress",
    "egress",
    "encryption",
    "kms",
    "ssl",
    "tls",
    "acl",
    "access",
)

# MEDIUM priority: network-related attributes (kept second).
_MEDIUM_PRIORITY_KEYWORDS = (
    "vpc",
    "subnet",
    "network",
    "cidr",
    "route",
    "gateway",
    "dns",
)


class ContextSerializer:
    """Converts a ScanResult into a token-budget-aware string for the AI prompt.

    Filters out external and unresolved resources, serializes the remaining
    infrastructure data into a JSON structure suitable for AI analysis.
    Applies priority-based attribute truncation when exceeding the token budget.
    """

    def serialize(
        self,
        scan_result: ScanResult,
        pillars: list[str],
        max_tokens: int | None = None,
    ) -> str:
        """Serialize a ScanResult into a JSON string for the AI prompt.

        Args:
            scan_result: The completed scan result containing resources and relationships.
            pillars: List of analysis pillars (e.g., ["Security", "Cost_Optimization", "Performance"]).
            max_tokens: Maximum token budget for the output. Defaults to AI_API_MAX_TOKENS
                        env var or 30000 if not set.

        Returns:
            A JSON string containing the serialized infrastructure context and pillars.

        Raises:
            CloudSpyglassError: If zero resources remain after filtering.
        """
        if max_tokens is None:
            max_tokens = int(os.environ.get("AI_API_MAX_TOKENS", "8000"))

        # Filter out external and unresolved resources (Requirement 2.6)
        filtered_resources = [
            r
            for r in scan_result.resources
            if not r.is_external and not r.is_unresolved
        ]

        if len(filtered_resources) == 0:
            raise CloudSpyglassError(
                error_code="NO_RESOURCES_FOR_ANALYSIS",
                message="No resources available for analysis after filtering external and unresolved resources.",
                status_code=400,
            )

        # Serialize resources (Requirement 2.1)
        serialized_resources = [
            self._serialize_resource(r) for r in filtered_resources
        ]

        # Serialize relationships (Requirement 2.2)
        serialized_relationships = [
            self._serialize_relationship(rel) for rel in scan_result.relationships
        ]

        # Build the output structure
        output = {
            "infrastructure": {
                "resources": serialized_resources,
                "relationships": serialized_relationships,
            },
            "analysis_pillars": pillars,
        }

        # Enforce token budget with priority-based truncation (Requirements 2.4, 2.5)
        output_str = json.dumps(output, separators=(",", ":"))
        if self._estimate_tokens(output_str) > max_tokens:
            output = self._truncate_to_budget(output, max_tokens)
            output_str = json.dumps(output, separators=(",", ":"))

        return output_str

    def _serialize_resource(self, resource: Resource) -> dict:
        """Serialize a single resource with its structural fields and attributes.

        Includes: ARN, resource_type, name, region, tags, attributes.
        """
        return {
            "arn": resource.arn,
            "resource_type": resource.resource_type,
            "name": resource.name,
            "region": resource.region,
            "tags": resource.tags,
            "attributes": resource.attributes,
        }

    def _serialize_relationship(self, relationship: Relationship) -> dict:
        """Serialize a single relationship.

        Includes: source_arn, target_arn, category, derived_from.
        """
        return {
            "source_arn": relationship.source_arn,
            "target_arn": relationship.target_arn,
            "category": relationship.category,
            "derived_from": relationship.derived_from,
        }

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using character-based approximation (1 token ≈ 4 chars)."""
        return len(text) // 4

    def _classify_attribute(self, key: str) -> str:
        """Classify an attribute key into a priority category.

        Returns:
            "high" for IAM/security/encryption attributes,
            "medium" for network attributes,
            "low" for everything else.
        """
        key_lower = key.lower()
        for keyword in _HIGH_PRIORITY_KEYWORDS:
            if keyword in key_lower:
                return "high"
        for keyword in _MEDIUM_PRIORITY_KEYWORDS:
            if keyword in key_lower:
                return "medium"
        return "low"

    def _filter_attributes(
        self, attributes: dict[str, Any], keep_priorities: set[str]
    ) -> dict[str, Any]:
        """Filter attributes keeping only those matching the specified priority levels."""
        return {
            key: value
            for key, value in attributes.items()
            if self._classify_attribute(key) in keep_priorities
        }

    def _truncate_to_budget(self, output: dict, max_tokens: int) -> dict:
        """Apply priority-based attribute truncation to fit within token budget.

        Truncation passes:
        1. Remove LOW priority attributes (keep high + medium)
        2. Remove MEDIUM priority attributes (keep high only)
        3. Remove ALL attributes (keep only structural fields)

        Structural fields (ARN, resource_type, name, region, tags) and
        relationships are never removed.
        """
        resources = output["infrastructure"]["resources"]

        # Pass 1: Remove LOW priority attributes (keep high + medium)
        for resource in resources:
            resource["attributes"] = self._filter_attributes(
                resource["attributes"], {"high", "medium"}
            )
        result_str = json.dumps(output, separators=(",", ":"))
        if self._estimate_tokens(result_str) <= max_tokens:
            return output

        # Pass 2: Remove MEDIUM priority attributes (keep high only)
        for resource in resources:
            resource["attributes"] = self._filter_attributes(
                resource["attributes"], {"high"}
            )
        result_str = json.dumps(output, separators=(",", ":"))
        if self._estimate_tokens(result_str) <= max_tokens:
            return output

        # Pass 3: Remove ALL attributes (keep only structural fields)
        for resource in resources:
            resource["attributes"] = {}
        return output
