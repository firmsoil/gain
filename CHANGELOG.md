# Changelog

All notable changes to the GAIN (GitHub AI Intelligence Network) platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-21

### Added
- **Scale Ingestion Pipeline (40,000+ Repositories)**:
  - Repository Registry backed by Parquet (`gain.registry`) with tier assignments (`critical`, `standard`, `archive`) and automated GitHub organization discovery.
  - GitHub App authentication (`gain.github.auth`) with RS256 JWT generation and token caching, alongside PAT authentication.
  - Health-aware token pool (`GitHubTokenPool`) with quota routing, reset-time recovery, and round-robin fallback.
  - Asynchronous GraphQL client (`AsyncGitHubGraphQLClient`) featuring persistent connection pooling (`httpx.AsyncClient`), retry backoff, and jitter.
  - Distributed work queue (`gain.ingestion.queue`) and fan-out coordinator (`IngestionCoordinator`) supporting concurrent multi-worker backfills.
  - Graceful shutdown signal traps (`SIGTERM`, `SIGINT`) preserving atomic checkpoint progress without data loss.
- **Storage & Query Engine Redesign**:
  - Hive-partitioned storage (`gain.storage.partitioning`) organizing Parquet datasets by `year=YYYY/month=MM/org=ORG/` with predicate pushdown.
  - Compaction service (`gain.storage.compaction`) atomically merging small partition files into optimal row-group files.
  - Polars-native analytics pipeline streaming LazyFrames for microsecond-precision quantiles and vectorized quality validations.
  - Per-repository sharded checkpoint store with POSIX atomic renames.
  - Inverted entity indexing (`EntityIndex`) and relationship store for $O(1)$ lineage joins.
- **Deployment & Production Readiness**:
  - Multi-stage hardened Dockerfile with non-root security context (`gain:gain`, UID 10001).
  - Production Helm chart under `deploy/helm/gain/` (MCP Server Deployment, HPA autoscaling, CronJob sync, PDB, NetworkPolicy).
  - Hardened GitHub Actions CI pipeline with Python 3.12 and 3.13 matrix, `pip-audit`, and container validation.
  - Kubernetes liveness (`/healthz`), readiness (`/readyz`), and Prometheus metrics (`/metrics`) probe endpoints.
- **Observability & Operations**:
  - OpenTelemetry and Prometheus instrumentation (`gain.telemetry`) tracking ingestion pages, nodes, durations, and rate limits.
  - Service Level Objectives (SLOs) specification (`docs/operations/SLOS.md`) and alerting rules (`deploy/monitoring/alerts.yaml`).
  - Maintenance CLI (`gain maintenance stats`, `purge-raw`, `purge-checkpoints`, `compact`).
- **Governance & Compliance**:
  - Salted HMAC-SHA256 author pseudonymization (`gain.privacy`) for PII governance and right-to-be-forgotten compliance.
  - Comprehensive Data Governance specification (`docs/operations/DATA_GOVERNANCE.md`).

### Fixed
- Replaced broad bare exception handlers across storage and service layers with structured `structlog` calls and typed `GainError` hierarchy.
- Enforced strict layer boundary isolating canonical `PullRequest` domain entity from calculation logic.
- Resolved race conditions in checkpoint listing through isolated repository shard keys.
