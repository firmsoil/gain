# ADR 0042: Cross-System DORA and Traceability Metrics

## Status
Accepted

## Context
DORA metrics (Deployment Frequency, Change Failure Rate, Change Lead Time) and cross-system flow metrics require correlating deployment telemetry, version control commits, pull requests, and upstream work tracker items.

Prior to Gate 9, GAIN's MCP server returned `status="insufficient_data"` for DORA queries because deployment telemetry was not yet ingested into canonical storage.

## Decision
1. **Deterministic DORA Metric Service (`DORAService`)**:
   - Calculates Deployment Frequency (weekly/daily production deployment count).
   - Calculates Change Failure Rate (failed production deployments / total production deployments).
   - Calculates Change Lead Time (time delta from commit author date to production deployment completion).
   - Zero LLM reasoning or heuristic interpolation in metric computation.
2. **Issue Analytics & Traceability Service (`IssueAnalyticsService`)**:
   - Calculates work item cycle time (`resolved_at - created_at`).
   - Resolves cross-system links: issue keys in PR branch names, PR titles, or commit messages.
3. **Epistemic Claim Classification**:
   - Explicit system links (e.g. Jira issue payload contains linked PR URL) are classified as `Observed`.
   - Inferred pattern links (regex match of issue key in PR branch or title) are classified as `Associated`.
   - All deterministic metric values are classified as `Derived`.

## Consequences
- **Positive**: Enables production-ready DORA metrics across multi-system environments.
- **Positive**: Seamless transition of GAIN MCP `get_dora_metrics` from `insufficient_data` to `available` upon deployment ingestion.
- **Positive**: Transparent claim tagging prevents presenting heuristic traceability as empirical fact.
