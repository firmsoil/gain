# ADR 0041: Canonical Work Item, Deployment, and Commit Entities

## Status
Accepted

## Context
Third-party work management platforms (Jira, Linear, GitHub Issues) and CI/CD tools (GitHub Actions, ArgoCD, Jenkins) represent concepts with differing terminologies, status taxonomies, and relational structures (e.g. Jira `statusCategory` vs Linear `state.type`; GitHub Actions `conclusion` vs ArgoCD `healthStatus`).

GAIN analytical metrics require consistent, transport-independent canonical entities to calculate cross-system engineering flow metrics.

## Decision
1. **Canonical Issue (`CanonicalIssue`)**:
   - Encapsulates work items across Jira, Linear, and other trackers.
   - Normalizes state into `OPEN`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `CLOSED`, `CANCELLED`.
   - Normalizes type into `STORY`, `BUG`, `TASK`, `EPIC`, `SUBTASK`.
   - Enforces UTC timezone on all timestamps (`created_at`, `updated_at`, `resolved_at`).
2. **Canonical Deployment (`CanonicalDeployment`)**:
   - Encapsulates deployment events across CI/CD platforms.
   - Normalizes environment into `PRODUCTION`, `STAGING`, `DEVELOPMENT`, `CANARY`.
   - Normalizes status into `SUCCESS`, `FAILURE`, `IN_PROGRESS`, `CANCELLED`.
   - Captures `commit_sha`, execution duration, and trigger identity.
3. **Canonical Commit (`CanonicalCommit`)**:
   - Encapsulates version control changes across Git providers.
4. **Immutability & Strict Typing**:
   - All canonical models are defined with Pydantic v2 `ConfigDict(extra="forbid", frozen=True)` to prevent accidental post-ingestion mutation.

## Consequences
- **Positive**: Uniform schema across multiple enterprise vendors.
- **Positive**: Immutability guarantees analytical consistency.
- **Positive**: Columnar Parquet persistence with PyArrow/Polars interoperability.
