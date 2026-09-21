# GAIN MCP Server Architecture Review

**Date:** 2026-09-20
**Reviewer:** GAIN Principal Architecture Specialist
**Target:** GAIN MCP Server Layer (`src/gain/mcp/`, `src/gain/services/`, ADRs 0010-0016)

---

## 1. Executive Summary

An architectural audit of the GAIN MCP Server vertical slice was conducted to evaluate its conformance to the authoritative GAIN architecture. The objective was to verify that the MCP layer strictly acts as a transport-independent, domain-oriented interface, maintaining deep separation from the primary data plane, metric computation engines, and external GitHub integration boundaries.

The implementation is highly conformal. It adheres successfully to the negative architectural scope, effectively enforcing a deterministic boundary that protects the integrity of GAIN's analytical engine against downstream AI hallucinations or unintended data proxies.

---

## 2. Architectural Findings

### 2.1 Conformance with Authoritative Architecture
**Status: CONFORMAL**
**Severity: INFORMATIONAL**
- The topology `External AI Agents -> GAIN MCP Server -> GAIN Domain Services -> GAIN Data Product` is perfectly reflected in the codebase.
- MCP tools (e.g., `src/gain/mcp/tools/metrics.py`) cleanly delegate execution to `gain.services.metrics.MetricService`, entirely avoiding direct access to the `gain.storage` data product or the `gain.github` acquisition client.

### 2.2 Strict Separation of Concerns
**Status: CONFORMAL**
**Severity: INFORMATIONAL**
- The MCP boundary (`src/gain/mcp/`) isolates protocol transport logic (Pydantic schemas, resource templates, tool definitions) from canonical domain services (`src/gain/services/`).
- The `gain.mcp.schemas` strictly typed responses enforce the transport adapter pattern, translating the canonical GAIN analytical responses into the MCP protocol format.

### 2.3 Exclusion of Metrics Calculation, Data Plane, and LLMs
**Status: CONFORMAL**
**Severity: INFORMATIONAL**
- **No Metrics Calculation:** All metric derivations occur via `gain.services.metrics`. The MCP layer operates strictly as a read-only transport layer.
- **No Data Plane Proxying:** The MCP layer does not stream raw big-data artifacts or persist telemetry (in accordance with ADR 0011).
- **No LLM Computation:** The MCP layer relies on pure Python execution and explicitly rejects fabricating metrics. For example, `get_dora_metrics` deterministically returns `insufficient_data` and clearly identifies missing upstream dependencies (e.g., "GitHub Deployments API") instead of hallucinating values.

### 2.4 Contract Stability and Versioning
**Status: CONFORMAL**
**Severity: INFORMATIONAL**
- A robust contract testing suite (`tests/mcp/test_contracts.py`) programmatically enforces the immutability of the public MCP interface.
- It explicitly validates the exact inventory requested: **12 domain tools**, **8 addressable resources**, and **8 methodological prompts**.
- Structural invariants (e.g., presence of `metric_id` and `metric_version` in outputs) are codified into tests, ensuring compliance with ADR 0016.

### 2.5 Future GitHub MCP Integration Boundary
**Status: CONFORMAL**
**Severity: LOW** (Recommendation attached)
- The implementation and `src/gain/mcp/server/instructions.py` effectively establish an explicit negative constraint: GAIN MCP will NOT act as a generic proxy for GitHub API mutations or live operational state lookups.
- By utilizing `github_node_id` purely as an analytical identifier passed down to the lineage and entity services, the MCP server is structurally insulated from upstream GitHub protocol dynamics.

---

## 3. Concrete Architectural Recommendations

1. **Schema Snapshot Testing (MEDIUM):** While `test_contracts.py` accurately asserts presence of expected tools/resources and top-level schema fields, consider introducing full JSON schema snapshot tests to guarantee that nested structures and enum definitions do not implicitly drift over time.
2. **Streamable HTTP Concurrency Profiling (LOW):** As external AI agents can execute highly concurrent workflows (e.g., fan-out artifact analysis), recommend defining load testing requirements specifically for the Starlette/Uvicorn Streamable HTTP transport to ensure stable ASGI lifecycle management under concurrent stress.
3. **Tenant-Aware Telemetry Guardrails (LOW):** Ensure the `trace_mcp_request` consistently propagates tenant identifiers across all backend boundaries to guarantee clear separation in observability platforms, especially as complex cohort comparisons (`compare_cohorts`) potentially scan massive multi-tenant datasets.

---
**Verdict:** The GAIN MCP Server layer is approved. It successfully implements the mandated decoupled, zero-LLM, domain-oriented architecture.
