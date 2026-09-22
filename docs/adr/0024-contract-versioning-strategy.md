# ADR 0024: Contract Versioning Strategy for GAIN MCP Interface

## Status
Accepted

## Context
As GAIN scales across 40,000+ repositories and multiple external AI agent clients (Claude Code, Cursor, GitHub Copilot, custom enterprise agent orchestrators), breaking schema changes in MCP tool parameters or resource outputs risk destabilizing production agent workflows.

We require a formalized contract versioning strategy that:
1. Prevents uncoordinated breaking schema changes from degrading external agent tools.
2. Allows additive changes without forcing consumers to update schemas immediately.
3. Provides explicit envelope metadata for telemetry provenance and schema negotiation.

## Decision
1. **Versioned Response Envelope**:
   All GAIN MCP tool evaluations and resource reads return a standardized `VersionedResponse[T]` envelope containing:
   - `api_version`: Major/minor protocol revision (e.g. `1.0`).
   - `contract_version`: ISO-date-based contract release tag (e.g. `2026-06-01`).
   - `timestamp`: UTC ISO timestamp.
   - `data`: Canonical domain payload model.
   - `metadata`: Provenance tags, execution duration, and pagination markers.

2. **Schema Evolution Rules**:
   - **Additive Changes (Backwards Compatible)**: New optional fields may be added to payloads with default values at any time without incrementing `contract_version`.
   - **Breaking Changes**: Renaming fields, removing fields, or altering validation bounds requires a new date-stamped `contract_version` (e.g. `2026-12-01`). Older contract versions remain supported for a minimum 6-month deprecation window.
   - **Zero In-Band Mutation**: Canonical domain models (`gain.model.*`) remain separate from transport envelopes.

## Consequences
- **Positive**: External agent clients can inspect `contract_version` and safely parse payload structures. Deprecations are transparent and predictable.
- **Negative**: Adds lightweight serialization overhead for the envelope structure.
