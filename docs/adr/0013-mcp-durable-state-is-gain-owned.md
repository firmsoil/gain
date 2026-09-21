# ADR 0013: MCP Durable State Is GAIN-Owned

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Platform Engineer, GAIN Security Engineer  

---

## 1. Context

Model Context Protocol (MCP) in Python SDK v2 (`mcp>=2.0.0`) is built upon a stateless protocol core. Session tokens, connection IDs, and transport streams are transient and unsuited for durable enterprise state. Operations such as investigations, evidence packages, and audit trails require long-term persistence across agent restarts or multi-tenant deployments.

---

## 2. Decision

We decide that **all durable business state is owned and persisted exclusively by GAIN application services**:

1. **Application-Owned Identifiers**:
   - `investigation_id`
   - `plan_id`
   - `evidence_package_id`
   - `analysis_version`
   - `result_state`
   are first-class domain identifiers managed by `gain.services.investigation` and stored in GAIN-managed durable persistence (`data/investigations/`).
2. **Session Independence**: Durable business state must never rely on MCP connection IDs, transport sessions, or protocol memory buffers. An investigation created in one MCP session can be resumed, queried, or verified in another session by authorized callers.
3. **No MCP Tasks Dependency**: We do not implement the speculative MCP Tasks extension, relying instead on explicit GAIN domain investigation state management with clear status codes (`INITIATED`, `IN_PROGRESS`, `COMPLETED`, `FAILED`).

---

## 3. Consequences

- **Positive**: Investigations and evidence survive transport disconnects, process restarts, and pod rescheduling.
- **Positive**: MCP server instances remain lightweight and horizontally scalable.
- **Negative**: GAIN must maintain file-system or database storage for investigation artifacts.
