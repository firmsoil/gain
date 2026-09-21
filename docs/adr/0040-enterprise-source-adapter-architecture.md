# ADR 0040: Enterprise Source Adapter Architecture

## Status
Accepted

## Context
GAIN's mission is to provide high-integrity, deterministic engineering intelligence. In previous phases, the data ingestion pipeline was coupled to GitHub GraphQL PR telemetry and Copilot AI telemetry. To support cross-system flow metrics, DORA delivery metrics, and end-to-end traceability, GAIN must ingest data from enterprise work trackers (Jira, Linear) and CI/CD deployment systems (GitHub Actions, ArgoCD, GitLab CI).

Directly ingesting third-party vendor models into downstream metrics would couple GAIN's analytical engine to vendor-specific APIs, unstable pagination semantics, and proprietary schema definitions.

## Decision
1. **Source Adapter Pattern**: All external engineering systems connect through dedicated `BaseSourceAdapter` implementations in `gain.adapters.*`.
2. **Lossless Raw Capture**: Source adapters must persist raw vendor JSON responses verbatim in JSONL format with structured provenance metadata (`source_system`, `source_id`, `collected_at`, `ingestion_run_id`) before performing normalization.
3. **Defensive Normalization & Quarantine**: Source adapters normalize raw records into canonical models, isolating malformed or incomplete records in structured error lists without failing the entire ingestion batch.
4. **Columnar Canonical Persistence**: Validated canonical records are persisted to partitioned Parquet files in `data/canonical/`.

## Consequences
- **Positive**: Complete decoupling between third-party API transports and GAIN analytics.
- **Positive**: Full historical replayability and audit provenance for external systems.
- **Positive**: Consistent quarantine and failure modes across all enterprise sources.
- **Negative**: Requires maintaining adapter mapping logic when upstream vendor APIs evolve.
