# GAIN Vertical Slice Architecture

## Scope

This release implements the first Spec-Driven Development vertical slice only:

`GitHub GraphQL -> resilient paginated collection -> raw JSONL -> canonical PullRequest -> GAIN-PR-001 -> Parquet/JSON outputs`

## GitHub collection

The collector uses the repository Pull Request GraphQL connection, ordered newest-first. It pages until the requested lower `createdAt` bound is crossed. GitHub's GraphQL connections require cursor pagination and a `first`/`last` argument from 1 to 100. The implementation caps the configurable page size at 100.

The query is version controlled in `src/gain/github/queries.py`. The HTTP client handles transient failures, 403/429 rate limiting, bounded exponential backoff, `retry-after`, and rate-limit reset hints. Partial GraphQL errors are logged; a response with no usable `data` fails the run.

## Replayability

Each page is written as JSONL with source provenance. The raw store is separate from canonical analytics so metric changes do not require calling GitHub again.

## Canonical model

The analytics layer consumes `gain.model.pr.PullRequest`, never the GraphQL response directly. Timestamps are normalized to UTC and core semantic constraints are enforced using Pydantic.

## Cycle time

`GAIN-PR-001 = merged_at - created_at`.

This is observable PR lifecycle elapsed time. It is not active coding time or developer effort. Unmerged PRs are excluded from the cycle-time distribution and counted separately by downstream quality/reporting layers.

## Current operational boundary

The vertical slice is batch-oriented. Resumable checkpoints, incremental synchronization, deduplication/upsert behavior, richer data-quality reporting, executive outputs, and review analytics are specified but intentionally remain follow-on implementation phases.
