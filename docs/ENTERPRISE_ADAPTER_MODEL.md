# Enterprise Source Adapter & Canonical Integration Model

## 1. Executive Summary

As defined in `docs/MASTER_SPEC.md` Section 5:
> **Gate 9**: Future enterprise engineering-system integrations are introduced through source adapters into the canonical GAIN model.

GAIN is designed to serve as the unified, authoritative analytical layer for enterprise software delivery. To analyze cross-functional engineering throughput, lead time to production, and team collaboration, GAIN must ingest operational facts from systems beyond GitHub, including:
- **Work Management & Issue Trackers**: Jira, Linear, GitHub Issues, GitLab Issues.
- **CI/CD & Deployment Telemetry**: GitHub Actions, GitLab CI, ArgoCD, Jenkins.
- **Source Code Management (SCM)**: Git Commits, code churn, and version tags.

---

## 2. Core Architectural Invariants for Enterprise Adapters

1. **Source of Truth Integrity**:
   Each external vendor (e.g. Jira for work items, GitHub Actions for deployment runs) remains the operational system of record.
2. **Lossless Raw Capture**:
   Before any schema normalization occurs, raw JSON payloads from the external API are persisted verbatim in JSONL format with structured provenance metadata (`source_system`, `source_id`, `collected_at`, `ingestion_run_id`).
3. **Transport Independence**:
   Canonical domain models (`CanonicalIssue`, `CanonicalDeployment`, `CanonicalCommit`) are strictly isolated from vendor REST/GraphQL structures, pagination tokens, or custom-field naming conventions.
4. **Error Isolation & Quarantine**:
   Malformed or incomplete source payloads are quarantined into structured error logs with exact item indices without aborting the entire ingestion job.
5. **Deterministic Analytics**:
   Cross-system calculations (DORA Deployment Frequency, DORA Change Failure Rate, DORA Change Lead Time, Issue Cycle Time) are implemented as pure Python deterministic functions with zero LLM reasoning.

---

## 3. Architecture Overview

```
External Enterprise System
(Jira API, Linear API, CI/CD Events)
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Source Adapter Layer                     │
│  - Ingest API responses or webhook events                   │
│  - Write verbatim JSONL payloads with provenance metadata   │
│  - Defensive Normalization with Error Quarantine            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Canonical Domain Models                   │
│  - CanonicalIssue (key, status, type, cycle_time)           │
│  - CanonicalDeployment (env, status, duration, commit_sha)  │
│  - CanonicalCommit (sha, author, timestamp, additions)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Columnar Storage (Parquet)                  │
│  - data/canonical/issues__<source>__*.parquet               │
│  - data/canonical/deployments__*.parquet                    │
│  - data/canonical/commits__*.parquet                        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Deterministic Analytics Services               │
│  - DORAService (Deployment Frequency, Change Fail Rate)     │
│  - IssueAnalyticsService (Cycle Time, Traceability Links)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             MCP Server & Intelligence Agent                 │
│  - Tools: get_dora_metrics, list_canonical_issues           │
│  - Agent: Hypothesis planning, evidence packages            │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Canonical Domain Entity Contracts

### 4.1 CanonicalIssue (`src/gain/model/issue.py`)
Represents a trackable unit of work across any work management platform.
- `id`: Unique global identifier (`jira:PROJ-101`, `linear:ENG-202`).
- `key`: Human-readable identifier (`PROJ-101`, `ENG-202`).
- `source_system`: `SourceSystem` enum (`JIRA`, `LINEAR`, `GITHUB`, `GITLAB`, `CUSTOM`).
- `project_key`: Project or team identifier.
- `title`: Sanitized summary of the issue.
- `issue_type`: Normalized type (`STORY`, `BUG`, `TASK`, `EPIC`, `SUBTASK`).
- `status`: Normalized lifecycle status (`OPEN`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `CLOSED`, `CANCELLED`).
- `priority`: Normalized priority string (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- `author`: Reporter identifier.
- `assignee`: Assigned developer identifier.
- `labels`: List of tag strings.
- `story_points`: Estimated effort/points (if applicable).
- `created_at`: UTC timestamp of creation.
- `updated_at`: UTC timestamp of last update.
- `resolved_at`: UTC timestamp of completion/resolution (or None).
- `linked_pr_keys`: List of linked pull request keys or identifiers.
- `collected_at`: UTC timestamp of ingestion.
- `ingestion_run_id`: Execution run identifier.

### 4.2 CanonicalDeployment (`src/gain/model/deployment.py`)
Represents an observable deployment event of a codebase to an operational environment.
- `id`: Global deployment identifier (`gh_actions:run_8910`, `argocd:sync_123`).
- `source_system`: Deployment source enum (`GITHUB_ACTIONS`, `ARGOCD`, `GITLAB_CI`, `JENKINS`, `CUSTOM`).
- `repository_name_with_owner`: Associated repository (`firmsoil/gain`).
- `environment`: Deployment target (`PRODUCTION`, `STAGING`, `DEVELOPMENT`, `CANARY`).
- `status`: Execution status (`SUCCESS`, `FAILURE`, `IN_PROGRESS`, `CANCELLED`).
- `commit_sha`: Deployed git commit hash.
- `ref_name`: Git branch or release tag.
- `deployed_by`: Actor or service account triggering the deployment.
- `started_at`: UTC timestamp when the deployment job started.
- `completed_at`: UTC timestamp when the deployment finished.
- `duration_seconds`: Total runtime in seconds.
- `collected_at`: UTC timestamp of ingestion.
- `ingestion_run_id`: Execution run identifier.

### 4.3 CanonicalCommit (`src/gain/model/commit.py`)
Represents an immutable git commit.
- `sha`: Git commit SHA.
- `repository_name_with_owner`: Associated repository.
- `author_name`: Author name.
- `author_email`: Author email.
- `author_login`: Optional GitHub/GitLab handle.
- `committed_at`: UTC commit timestamp.
- `message`: Commit message text.
- `additions`: Lines added.
- `deletions`: Lines deleted.
- `files_changed`: Count of files modified.
- `collected_at`: UTC timestamp of ingestion.
- `ingestion_run_id`: Execution run identifier.

---

## 5. Deterministic DORA Metrics Formulation

### 5.1 Deployment Frequency
- **Formula**: Total successful production deployments within the reporting period divided by days or weeks.
- **Grain**: Repository per week.
- **Classification**: `Derived`.

### 5.2 Change Failure Rate
- **Formula**:
  $$\text{Change Failure Rate} = \frac{\text{Count}(\text{Failed Deployments})}{\text{Count}(\text{Total Deployments})} \times 100\%$$
- **Filters**: Environment = `PRODUCTION`.
- **Classification**: `Derived`.

### 5.3 Change Lead Time to Production
- **Formula**:
  $$\text{Lead Time} = \text{Deployment.completed\_at} - \text{Commit.committed\_at}$$
- **Grain**: Deployed commit.
- **Classification**: `Derived`.

---

## 6. Traceability and Claim Classification

When linking work items (`CanonicalIssue`) to code changes (`PullRequest`):
- **Explicit Links**: If the issue payload explicitly contains the PR URL or branch reference, the link is classified as **`Observed`**.
- **Inferred Pattern Matching**: If the link is established by regex pattern matching of the issue key (e.g. `PROJ-123`) in the PR branch name, PR title, or commit message, the claim is classified as **`Associated`**.
- **Causal Claims**: Attributing cycle-time changes to specific work item management practices is classified as **`Attributed`** only under controlled experimental comparisons.
