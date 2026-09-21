# GAIN Architecture Audit Review

**Date:** 2026-09-20
**Reviewer:** GAIN Principal Architecture Specialist (gain-architect)

## 1. Executive Summary

This report documents an independent architectural audit of the GAIN codebase (`src/gain`), measured against the authoritative boundaries and constraints defined in `docs/REFERENCE_ARCHITECTURE.md`. While the fundamental data flow (GraphQL → Raw JSONL → Canonical Entity → Metrics → Analytics) is sound, there are several severe violations of the reference architecture's constraints. Most notably, the inclusion of an entire requirements generation and Jira synchronization capability explicitly violates the mandated "Strict Negative Scope". Additionally, leaky abstractions blur the line between canonical models and metrics.

## 2. Findings by Severity

### CRITICAL: Violation of Strict Negative Scope
- **Description:** The `src/gain/requirements` package implements Jira synchronization (`jira.py`) and AI-based story generation (`generation.py`). There is also a corresponding design document in `docs/architecture/requirements-jira-sdd.md`.
- **Architectural Impact:** This is a direct violation of Section 2, Rule 6 in the Reference Architecture: "Strict Negative Scope (Non-Goals for Slice 1): Upstream Jira synchronization or requirements generation".
- **Recommendation:** Remove the `requirements` package and its CLI commands from this vertical slice, or officially amend the Reference Architecture to expand the system boundary.

### HIGH: Metric Logic Leaking into Canonical Domain Model
- **Description:** The canonical domain model `gain.model.pr.PullRequest` implements the method `cycle_time_seconds()`, containing the business logic for calculating PR cycle time.
- **Architectural Impact:** This couples the transport-independent domain entity to the deterministic Metric Engine layer. According to Section 2.4 and 3.3, metric calculations should reside strictly within `gain.metrics`.
- **Recommendation:** Relocate `cycle_time_seconds()` calculation logic into `gain.metrics.cycle_time.CycleTimeMetric`. The domain model should remain a pure data container for validated external facts.

### HIGH: Monolithic Pipeline Hinders Extensibility
- **Description:** `src/gain/sync.py` (`PullRequestBackfill`) and `src/gain/schema.py` (`normalize_records`) are hardcoded to process only Pull Requests.
- **Architectural Impact:** Section 4 of the Reference Architecture mandates that the architecture be explicitly designed to ingest additional entities (Issues, Commits) by replicating the decoupled pipeline pattern. The current tight coupling in the orchestrator (`sync.py`) prevents straightforward registration of new entity types.
- **Recommendation:** Refactor `sync.py` to use an entity-agnostic `GenericBackfill` orchestrator. It should accept a query, a normalizer function, and a target storage path. Update `schema.py` to use a registry pattern for normalization handlers rather than a single hardcoded PR function.

### MEDIUM: Leaky Transport Abstractions in Domain Entity
- **Description:** `gain.model.pr.PullRequest` exposes `github_node_id`. 
- **Architectural Impact:** The field name leaks the underlying GraphQL transport topology (Nodes/Edges) into the transport-independent domain model.
- **Recommendation:** Rename `github_node_id` to a more transport-agnostic identifier like `platform_id` or `source_id` within the `PullRequest` canonical model, maintaining decoupling from the GraphQL graph structure.

### MEDIUM: Missing Architecture Decision Records (ADRs)
- **Description:** The `docs/adr/` directory does not exist.
- **Architectural Impact:** The agent mandate and architecture refer to ADR consistency and governance. The presence of `docs/architecture/requirements-jira-sdd.md` outside an ADR process suggests architectural drift and a breakdown in formal decision tracking.
- **Recommendation:** Establish a `docs/adr/` directory using a standardized format (e.g., MADR or Nygard) to capture the rationale behind deviations from the reference architecture.

## 3. Concrete Architectural Recommendations

1. **Enforce Layer Isolation:** 
   Modify `gain.model.pr.PullRequest` to remove all metric logic (like `cycle_time_seconds()` and properties like `merged` / `is_bot` if they are strictly metric filters). Ensure `gain.metrics` modules perform these calculations on the raw domain fields.
2. **Abstract the Sync Orchestrator:**
   Redesign `PullRequestBackfill` into a generic `EntityBackfill` that can accept different GraphQL queries (e.g., `ISSUE_BACKFILL_QUERY`) and route to generic raw storage paths.
3. **Reconcile Scope Drift:**
   Immediately determine if the `requirements` package represents an approved expansion of scope. If it is an unapproved regression, isolate or revert it. If approved, formally update `docs/REFERENCE_ARCHITECTURE.md` to remove the restriction and document the updated boundaries.
