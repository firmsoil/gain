# GAIN Implementation Tasks

## Phase 0 — Foundation
- [ ] T001 Initialize Python/uv repository and Spec Kit structure.
- [ ] T002 Add typed configuration model for GitHub scope, dates, storage, retry policy, and bot policy.
- [ ] T003 Add structured logging and run ID propagation.
- [ ] T004 Add secure credential loading with no secret logging.

## Phase 1 — Thin Vertical Slice
- [ ] T101 Implement GitHub GraphQL client.
- [ ] T102 Add MVP PullRequest query for id, number, repository, author, createdAt, closedAt, mergedAt, state, isDraft.
- [ ] T103 Implement cursor pagination with checkpoint support.
- [ ] T104 Implement bounded retry/backoff and rate-limit handling.
- [ ] T105 Persist raw response plus ingestion metadata.
- [ ] T106 Implement canonical PullRequest normalization.
- [ ] T107 Implement GAIN-PR-001 cycle-time metric.
- [ ] T108 Add metric catalog loader and schema validation.
- [ ] T109 Add output writer for canonical PR and metric observations.
- [ ] T110 Create synthetic reference fixture and end-to-end test.

## Phase 2 — Reliability
- [ ] T201 Add resumable backfill orchestration.
- [ ] T202 Add incremental sync with recent lookback.
- [ ] T203 Add idempotent upsert/deduplication.
- [ ] T204 Add data-quality rule engine.
- [ ] T205 Add synchronization report.
- [ ] T206 Add data-quality report.

## Phase 3 — Core Metrics
- [ ] T301 Implement merged throughput.
- [ ] T302 Implement close-without-merge rate with explicit cohort semantics.
- [ ] T303 Implement PR aging snapshots.
- [ ] T304 Implement WIP snapshots.
- [ ] T305 Implement p50/p75/p90/p95 cycle-time reporting.
- [ ] T306 Implement PR size metrics when fields are collected.

## Phase 4 — Reporting
- [ ] T401 Create executive KPI output.
- [ ] T402 Create repository diagnostics.
- [ ] T403 Create trend outputs.
- [ ] T404 Add caveat/definition metadata to reports.

## Phase 5 — Review Analytics
- [ ] T501 Extend collection to reviews/review threads.
- [ ] T502 Implement time-to-first-review.
- [ ] T503 Implement review turnaround and approval latency.
- [ ] T504 Add review-level tests and privacy controls.

## Phase 6 — Future Integrations
- [ ] T601 Define deployment/commit correlation extension contract.
- [ ] T602 Define GitHub Actions/CI extension contract.
- [ ] T603 Define incident-system extension contract.
