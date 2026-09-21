"""Public schema definitions for GAIN MCP structured outputs."""

from __future__ import annotations

from gain.mcp.schemas.ai import AIImpactResult, ClaimClassification, ROIScenarioResult
from gain.mcp.schemas.dora import DORAMetricItem, DORAMetricsResult
from gain.mcp.schemas.entity import CanonicalEntityResult
from gain.mcp.schemas.evidence import EvidencePackageResult
from gain.mcp.schemas.investigation import InvestigationStatus, InvestigationSummary
from gain.mcp.schemas.lineage import LineageResult, LineageStep
from gain.mcp.schemas.metrics import (
    CohortResult,
    MetricComparison,
    MetricDefinitionResult,
    MetricResult,
)
from gain.mcp.schemas.quality import DataQualityResult

__all__ = [
    "AIImpactResult",
    "CanonicalEntityResult",
    "ClaimClassification",
    "CohortResult",
    "DORAMetricItem",
    "DORAMetricsResult",
    "DataQualityResult",
    "EvidencePackageResult",
    "InvestigationStatus",
    "InvestigationSummary",
    "LineageResult",
    "LineageStep",
    "MetricComparison",
    "MetricDefinitionResult",
    "MetricResult",
    "ROIScenarioResult",
]
