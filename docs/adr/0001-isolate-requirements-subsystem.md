# ADR 0001: Isolate Upstream Requirements Subsystem from Core Telemetry Pipeline

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Platform Engineer, GAIN Security Engineer  

---

## 1. Context

GAIN's primary mission is turning GitHub engineering activity into reproducible, deterministic engineering-flow analytics (`docs/REFERENCE_ARCHITECTURE.md`).

An upstream requirements-engineering subsystem was developed under `specs/002-requirements-jira-sdd/` and implemented in `src/gain/requirements/`. It provides human-governed business context tracking, draft story generation, optional Jira synchronization, and Spec-Driven Development (SDD) seeds.

During the architecture audit (`docs/reviews/ARCHITECTURE_REVIEW.md`), `gain-architect` flagged that the requirements subsystem includes optional AI story drafting and Jira synchronization, which could risk violating the "Strict Negative Scope" of the core PR analytics pipeline if coupled.

---

## 2. Decision

We establish strict architectural isolation between the **Core GitHub PR Telemetry Pipeline** and the **Upstream Requirements Engineering Subsystem**:

1. **Complete Decoupling**: The core telemetry pipeline (`gain.github`, `gain.sync`, `gain.storage`, `gain.schema`, `gain.model.pr`, `gain.metrics`) MUST NOT import or depend on `gain.requirements`.
2. **Deterministic Telemetry Guarantee**: All telemetry metrics (`GAIN-PR-001`, `GAIN-PR-010`, future DORA) derive exclusively from observable GitHub API telemetry and pure Python computation. No LLM reasoning or heuristic inference is permitted anywhere in the telemetry runtime.
3. **Non-Authoritative AI Drafts**: In `gain.requirements`, AI story generation is strictly non-authoritative. A named human must validate and approve any story before export or promotion.
4. **Independent CLI Commands**: Upstream requirements commands reside exclusively under the `gain requirements` sub-typer command namespace and do not interfere with `gain backfill`, `gain normalize`, or `gain compute`.

---

## 3. Consequences

- **Positive**: The core telemetry pipeline remains 100% deterministic, zero-LLM, and fully compliant with `docs/REFERENCE_ARCHITECTURE.md`.
- **Positive**: Teams needing upstream human-governed SDD and Jira projections can utilize `gain requirements` without corrupting metric integrity.
- **Negative**: Maintainers must ensure no cross-layer imports are introduced in future pull requests. This constraint is continuously validated by `gain-architect` and static analysis.
