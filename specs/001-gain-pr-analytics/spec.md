# GAIN PR Analytics — Product Specification

## 1. Purpose
GAIN converts GitHub Pull Request activity into a trustworthy engineering-flow analytics data product for technology leadership, engineering management, developer productivity, platform engineering, and analysts.

## 2. Goals
- Establish a reproducible GitHub-derived engineering-flow baseline.
- Measure PR throughput, lifecycle/cycle time, WIP, aging, and defensible PR-derived signals.
- Preserve source lineage from GitHub API fields through canonical data to metrics.
- Support historical backfill and incremental synchronization.
- Make metric definitions versioned and machine-readable.

## 3. Non-goals
- Individual developer productivity scoring.
- Measuring active coding time from PR timestamps alone.
- Reproducing full DORA/SPACE measurement models from GitHub PR data alone.
- Building a real-time event platform in the MVP.

## 4. Users and user stories
### CTO / CIO
As a technology executive, I want a small set of trustworthy trend indicators so I can identify systemic delivery bottlenecks without relying on anecdotal evidence.

### VP Engineering / Director
As an engineering leader, I want repository/team-level flow trends so I can target process improvements.

### Engineering Manager
As an engineering manager, I want cycle-time distributions and PR aging so I can understand queue and review bottlenecks.

### Developer Productivity Analyst
As an analyst, I want versioned metrics and raw lineage so I can reproduce findings and investigate anomalies.

### Platform/Data Engineer
As an engineer, I want resilient API synchronization and stable contracts so the system can run repeatedly and scale.

## 5. Core capabilities
1. Authenticate to GitHub.
2. Discover configured repositories.
3. Backfill PR history for a configured period.
4. Incrementally synchronize changed PRs.
5. Persist raw source payloads and provenance.
6. Normalize to a canonical model.
7. Validate data quality.
8. Compute versioned metrics.
9. Produce stable analytical outputs.
10. Emit synchronization and data-quality reports.

## 6. Metric scope
Initial release SHOULD include, subject to actual API data:
- PRs created
- PRs merged
- PRs closed
- merge rate
- close-without-merge rate
- PR cycle/lifecycle time
- p50/p75/p90/p95 cycle time
- PR aging
- WIP/open PR inventory
- throughput trend
- PR size metrics when available

Review and deeper collaboration metrics require review-level data and are Phase 2 unless collected by MVP.

## 7. Analytical guardrails
GAIN MUST describe `created_at → merged_at` as observable PR lifecycle elapsed time, not coding time. Any decomposition into review wait, CI wait, or active work MUST be based on actual event data and clearly labeled.

## 8. Functional requirements
### FR-001 API collection
The system shall collect configured GitHub PR data through GraphQL and, where justified, REST.

### FR-002 Scope
The system shall support organization/repository scope and configurable start/end timestamps.

### FR-003 Pagination
The system shall fully traverse cursor-based API connections and fail loudly on incomplete pagination.

### FR-004 Resumability
The system shall checkpoint collection and resume safely after interruption.

### FR-005 Raw provenance
Each collected object shall be attributable to an ingestion run and source object identifier.

### FR-006 Canonical normalization
Analytics shall operate on canonical entities rather than raw API response shapes.

### FR-007 Metric versioning
Each published metric shall have a stable ID and version.

### FR-008 Data quality
The system shall report invalid, incomplete, duplicate, and inconsistent records without silently discarding them.

### FR-009 Determinism
Identical source data/configuration/catalog versions shall yield deterministic results.

### FR-010 Outputs
The system shall emit canonical data, metric observations, data-quality reports, synchronization reports, and executive-ready aggregates.

## 9. Non-functional requirements
- Secure secret handling.
- Idempotent synchronization.
- Structured logs.
- Fixture-driven tests.
- Clean separation of acquisition and analytics.
- Scalable from thousands to millions of PRs.

## 10. Acceptance criteria
- Initial backfill can be completed from a clean checkout using documented configuration.
- API pagination is fully covered by tests.
- A forced interruption can resume without creating duplicates.
- Core cycle-time metric matches reference values.
- Every metric has documented lineage and version.
- Data-quality failures are visible in run outputs.
- No credential appears in logs or source code.
