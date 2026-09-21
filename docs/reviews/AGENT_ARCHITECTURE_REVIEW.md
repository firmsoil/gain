# Multi-Agent Specialist Review: Engineering Intelligence Agent Architecture

**Reviewer:** `gain-architect` (Principal GAIN Architecture Specialist)  
**Date:** 2026-09-20  
**Phase/Gate:** Gate 7 — Engineering Intelligence Agent  
**Authoritative Reference:** `docs/MASTER_SPEC.md`, `docs/REFERENCE_ARCHITECTURE.md`, `docs/adr/0020-engineering-intelligence-agent-architecture.md`  
**Verdict:** **CONFORMANT**

---

## 1. Scope of Audit

The architecture specialist conducted an independent audit of the newly introduced Engineering Intelligence Agent subsystem (`src/gain/agent/`) and its integration with GAIN MCP and GitHub MCP.

Audited dimensions:
1. **Three-Tier Separation of Truth**:
   - GitHub = Operational Truth.
   - GAIN = Analytical Truth.
   - Agent = Interpretive Intelligence.
2. **Interface Encapsulation**:
   - Does the Agent consume GAIN exclusively through the GAIN MCP interface?
   - Is there any direct leakage or ad-hoc calculation in the agent layer?
3. **Dual MCP Routing & Failure Isolation**:
   - Routing rules between GAIN MCP (analytical) and GitHub MCP (operational context).
   - Fault tolerance and graceful degradation behavior.
4. **Evidence & Lineage Contract**:
   - Traceability of claims to evidence packages.
   - Enforcement of the 7-tier claim classification taxonomy.

---

## 2. Findings & Architectural Conformance

### 2.1 Three-Tier Separation of Truth: CONFORMANT
- The Agent orchestrator (`EngineeringIntelligenceAgent`) strictly acts as a consumer of domain services via `ToolRouter`.
- **Zero LLM in Analytics**: No Python mathematical calculations, cycle times, percentiles, or cohort deltas are computed within prompt templates or by the LLM. All numbers originate from `gain.mcp.tools.query_engineering_metrics`.
- Interpretive summaries explicitly ground all statements in verified claims (`Claim` instances).

### 2.2 Interface Encapsulation: CONFORMANT
- `GainMcpClient` interacts strictly with the registered tools in `gain.mcp.tools`.
- Canonical storage and raw store internals are not imported or queried directly by the agent; all data access traverses the MCP authorization policy and telemetry boundary.

### 2.3 Dual MCP Tool Routing: CONFORMANT
- `ToolRouter` dispatches analytical questions to `gain_mcp` and qualitative inquiries to `github_mcp`.
- **Failure Handling**: When GitHub MCP is offline or unconfigured, the router degrades gracefully, noting the limitation without halting execution or fabricating live context. When GAIN MCP fails, the router raises an explicit `GainMcpUnavailableError` and halts, preventing unauthorized recalculation via raw GitHub APIs.

### 2.4 Evidence & Lineage Preservation: CONFORMANT
- Every investigation automatically constructs a durable `EvidencePackage` persisted via `EvidenceService`.
- The 7-tier claim classification (`Observed`, `Derived`, `Associated`, `Attributed`, `Modeled`, `Assumed`, `Unknown`) is strictly adhered to. Missing AI attribution telemetry correctly results in `ClaimType.UNKNOWN` rather than speculative inferences.

---

## 3. Specialist Recommendation
Gate 7 architecture conforms to all architectural directives in `docs/MASTER_SPEC.md`. Proceed to security and verification sign-offs.
