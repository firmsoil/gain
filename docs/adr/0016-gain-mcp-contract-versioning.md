# ADR 0016: GAIN MCP Contract Versioning

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Verification Engineer  

---

## 1. Context

MCP interfaces (tool names, argument schemas, structured output payloads, resource URIs, and prompt names) form the public API boundary consumed by external AI agents and enterprise platforms. Changes to these contracts can silently break downstream agents or cause invalid reasoning.

---

## 2. Decision

We establish strict **MCP Contract Governance & Versioning Rules**:

1. **Immutable Tool Signatures**: Tool names (`get_dora_metrics`, `query_engineering_metrics`, `compare_cohorts`, etc.) and their core argument structures are fixed contracts. Breaking modifications require a new tool name or explicit major protocol revision.
2. **Strongly Typed Structured Output**: All tool responses return Pydantic domain models with strict schema definitions rather than free-form conversational text.
3. **Metric Version Embedding**: Any analytical result returned by an MCP tool or resource must explicitly include `metric_id` and `metric_version`, maintaining parity with the GAIN Metric Catalog.
4. **Automated Contract Tests**: A dedicated contract test suite (`tests/mcp/test_contracts.py`) continuously validates that tool signatures, schemas, resource URI templates, and response models maintain backward compatibility and zero unintended field regressions.

---

## 3. Consequences

- **Positive**: External AI agents can reliably depend on tool contracts without unexpected field deletions or type mutations.
- **Positive**: Strict CI gates prevent accidental schema breakage during internal refactoring.
- **Negative**: Schema enhancements must be backward-compatible (optional fields with defaults).
