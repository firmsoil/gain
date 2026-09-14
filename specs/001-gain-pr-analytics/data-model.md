# GAIN Canonical Data Model

## Layers
RAW API → NORMALIZED → CANONICAL → METRIC OBSERVATION

## Core entities
### Organization
- organization_id
- login
- source_node_id

### Repository
- repository_id
- github_node_id
- name
- name_with_owner
- url
- owner_login
- is_archived
- default_branch
- source_updated_at

### Actor
- actor_id
- github_node_id
- login
- actor_type {HUMAN,BOT,UNKNOWN}

### PullRequest
- pull_request_id
- github_node_id
- repository_id
- number
- author_actor_id
- created_at
- closed_at
- merged_at
- state
- is_draft
- additions
- deletions
- changed_files
- review_decision
- is_cross_repository
- head_repository_id nullable
- source_collected_at
- source_ingestion_run_id

### Review
- review_id
- github_node_id
- pull_request_id
- author_actor_id
- state
- submitted_at

### ReviewThread
- review_thread_id
- github_node_id
- pull_request_id
- is_resolved
- created_at
- resolved_at nullable

### Commit
- commit_id
- pull_request_id
- oid
- committed_at

### IngestionRun
- ingestion_run_id
- started_at
- completed_at
- scope
- start_date
- end_date
- api_type
- api_version
- query_version
- status
- requests
- errors
- retries
- records_retrieved
- checkpoint

### MetricObservation
- metric_id
- metric_version
- observation_date
- grain_type
- grain_id
- value
- numerator nullable
- denominator nullable
- sample_size
- computation_run_id
- source_data_version

## Keys and invariants
- `repository_id + number` is the natural PR key within a repository.
- GitHub node IDs are preserved where available.
- Negative lifecycle durations are invalid.
- `merged_at` implies a merge outcome; a closed-but-unmerged PR has `merged_at = null`.
- Actor identity may be absent; do not fabricate it.

## Lineage
Every canonical row must retain ingestion provenance. Every MetricObservation must identify the source-data version and Metric Catalog version.
