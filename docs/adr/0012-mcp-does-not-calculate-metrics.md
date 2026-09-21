# ADR 0012: MCP Does Not Calculate Metrics

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Analytics Engineer, GAIN Verification Engineer  

---

## 1. Context

GAIN enforces deterministic, pure Python metric definitions (`GAIN-PR-001`, `GAIN-PR-010`) registered in `docs/metrics/metric-catalog.yaml`. When exposing metrics through MCP tools (e.g. `query_engineering_metrics`, `compare_cohorts`, `get_dora_metrics`), the metric evaluation logic must have a clear architectural owner.

---

## 2. Decision

We mandate that **the MCP layer shall never calculate metrics, interpret statistical methods ad-hoc, or run probabilistic LLM inference to compute metrics**:

1. **Analytical Engine Sole Ownership**: All metric formulas, percentiles, outlier exclusions, and cohort aggregations are executed solely by GAIN analytical engines (`gain.metrics.*`, `gain.services.metrics`).
2. **Zero-LLM Enforcement**: The MCP layer passes validated query parameters to GAIN domain services. No LLM reasoning or heuristic interpolation may alter the numbers.
3. **No Synthetic / Fake Values**: If a metric cannot be calculated due to missing upstream data (e.g. DORA deploy timestamps or AI attribution tags), MCP tools must return an explicit `insufficient_data` or `unsupported_capability` status rather than fabricating placeholder numbers.
4. **Metric Version Transparency**: Every metric output returned over MCP must explicitly declare its `metric_id` and `metric_version` referencing the authoritative GAIN Metric Catalog.

---

## 3. Consequences

- **Positive**: Strict mathematical integrity and reproducibility across all MCP clients.
- **Positive**: Complete auditability; numbers returned by MCP match batch analytics Parquet stores exactly.
- **Negative**: Ad-hoc formulas invented by client prompts cannot be executed unless formally defined in the Metric Catalog.
