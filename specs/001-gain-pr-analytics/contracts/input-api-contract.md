# GitHub API Acquisition Contract

## Scope
Supported source: GitHub GraphQL API, with REST adapters only where justified.

## Required acquisition behavior
- authenticate securely
- request only required fields
- paginate all connections
- persist query version
- persist API version
- persist ingestion run ID
- handle GraphQL errors and partial data explicitly
- checkpoint and resume
- observe primary/secondary rate limits

## Minimum PR fields for MVP
id, number, repository{nameWithOwner}, author{...}, createdAt, closedAt, mergedAt, state, isDraft.

## Optional MVP fields
additions, deletions, changedFiles, reviewDecision.

## Phase 2 collections
reviews, reviewThreads, reviewRequests, commits, checks/statuses, deployments.
