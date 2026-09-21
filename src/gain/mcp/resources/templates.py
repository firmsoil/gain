"""Resource registration for addressable GAIN analytical artifacts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import NotFoundError
from gain.services.evidence import EvidenceService
from gain.services.investigation import InvestigationService
from gain.services.lineage import LineageService
from gain.services.metrics import MetricService
from gain.services.quality import QualityService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def register_resources(server: MCPServer) -> None:
    """Register addressable URI templates with the MCPServer."""

    @server.resource("gain://metric-definitions/{metric_id}/{version}")
    def get_metric_definition_resource(metric_id: str, version: str) -> str:
        """Addressable metric definition from GAIN Metric Catalog."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.METRICS_READ,
            operation="read_resource:metric_definition",
        )
        service = MetricService()
        try:
            v_int = int(version)
            defn = service.get_metric_definition(metric_id, version=v_int)
        except (KeyError, ValueError):
            raise NotFoundError(f"Metric definition {metric_id} v{version} not found") from None
        return json.dumps(defn, indent=2)

    @server.resource("gain://metrics/{metric_id}")
    def get_metric_summary_resource(metric_id: str) -> str:
        """Addressable current summary for a named metric."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.METRICS_READ,
            operation="read_resource:metrics",
        )
        service = MetricService()
        if metric_id in ("GAIN-PR-001", "pr_cycle_time"):
            res = service.query_pr_cycle_time()
            return json.dumps(
                {
                    "metric_id": res.metric_id,
                    "metric_version": res.metric_version,
                    "metric_name": res.metric_name,
                    "summary_stats": res.summary_stats,
                    "data_freshness_utc": res.data_freshness_utc,
                },
                indent=2,
            )
        elif metric_id in ("GAIN-PR-010", "monthly_pr_flow_summary"):
            stats = service.query_monthly_stats()
            return json.dumps([s.to_dict() for s in stats], indent=2)
        else:
            raise NotFoundError(f"Metric '{metric_id}' not found")

    @server.resource("gain://cohorts/{cohort_id}")
    def get_cohort_resource(cohort_id: str) -> str:
        """Addressable cohort analytical summary."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.METRICS_READ,
            operation="read_resource:cohorts",
        )
        service = MetricService()
        # cohort_id can be a repository name (e.g. org__repo)
        repo_name = cohort_id.replace("__", "/")
        res = service.query_pr_cycle_time(repository=repo_name)
        return json.dumps(
            {
                "cohort_id": cohort_id,
                "repository": repo_name,
                "population_count": res.total_evaluated,
                "summary_stats": res.summary_stats,
            },
            indent=2,
        )

    @server.resource("gain://evidence/{evidence_id}")
    def get_evidence_resource(evidence_id: str) -> str:
        """Addressable previously generated evidence package."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.EVIDENCE_READ,
            operation="read_resource:evidence",
        )
        service = EvidenceService()
        pkg = service.get_evidence(evidence_id)
        if not pkg:
            raise NotFoundError(f"Evidence package '{evidence_id}' not found")
        return json.dumps(pkg.to_dict(), indent=2)

    @server.resource("gain://investigations/{investigation_id}")
    def get_investigation_resource(investigation_id: str) -> str:
        """Addressable durable investigation record."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.INVESTIGATION_READ,
            operation="read_resource:investigations",
        )
        service = InvestigationService()
        record = service.get_investigation(investigation_id, tenant_id=principal.tenant_id)
        if not record:
            raise NotFoundError(f"Investigation '{investigation_id}' not found")
        return json.dumps(record.to_dict(), indent=2)

    @server.resource("gain://lineage/{target_id}")
    def get_lineage_resource(target_id: str) -> str:
        """Addressable lineage trace for an entity or observation."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.METRICS_READ,
            operation="read_resource:lineage",
        )
        service = LineageService()
        trace = service.get_pr_lineage(target_id)
        if not trace:
            raise NotFoundError(f"Lineage trace for '{target_id}' not found")
        return json.dumps(
            {
                "target_id": trace.target_id,
                "target_type": trace.target_type,
                "provenance_chain": trace.provenance_chain,
                "steps": [
                    {"layer": n.layer, "id": n.identifier, "meta": n.metadata} for n in trace.nodes
                ],
            },
            indent=2,
        )

    @server.resource("gain://data-quality/{dataset_id}")
    def get_data_quality_resource(dataset_id: str) -> str:
        """Addressable data quality assessment for a dataset."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.QUALITY_READ,
            operation="read_resource:data-quality",
        )
        service = QualityService()
        eval_res = service.get_dataset_quality(dataset_id)
        return json.dumps(
            {
                "dataset_id": eval_res.dataset_id,
                "total_records": eval_res.total_records,
                "validity_score": eval_res.validity_score,
                "source_status": eval_res.source_status,
                "population_sufficiency": eval_res.population_sufficiency,
                "known_gaps": eval_res.known_gaps,
            },
            indent=2,
        )

    @server.resource("gain://contracts/{contract_id}")
    def get_contracts_resource(contract_id: str) -> str:
        """Addressable public contract definition."""
        principal = get_current_principal()
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.METRICS_READ,
            operation="read_resource:contracts",
        )
        contracts: dict[str, Any] = {
            "GAIN-PR-001": {
                "name": "pr_cycle_time",
                "formula": "merged_at - created_at",
                "unit": "seconds",
                "version": 1,
            },
            "GAIN-PR-010": {
                "name": "monthly_pr_flow_summary",
                "formula": "monthly aggregation of created, merged, closed PRs",
                "version": 1,
            },
        }
        if contract_id not in contracts:
            raise NotFoundError(f"Contract '{contract_id}' not found")
        return json.dumps(contracts[contract_id], indent=2)
