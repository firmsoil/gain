# Analytics & Deterministic Metrics Review Report

## Executive Summary
An independent audit was conducted on the GAIN codebase by the Engineering Analytics and Deterministic Metrics Specialist (`gain-analytics-engineer`). The review focused on the deterministic metric engine, specifically the cycle-time definition (`GAIN-PR-001`), monthly stats aggregation (`GAIN-PR-010`), metric catalog adherence, edge cases, and future DORA compatibility.

The architecture fundamentally adheres to the strict zero-LLM calculation directive and correctly implements transport-independent canonical domain representations. However, multiple edge-case and contract-adherence issues were identified, particularly regarding timezone normalization, data anomaly handling, and alignment with the Metric Catalog specifications.

---

## Findings

### 1. Metric Catalog Adherence & Summary Counting (GAIN-PR-001)
**Severity:** **HIGH**
*   **Observation:** The Metric Catalog for `GAIN-PR-001` specifies a `null_policy` of `exclude_from_cycle_time_but_report_count`. However, `src/gain/metrics/cycle_time.py` entirely skips PRs with `merged_at is None` during observation extraction. As a result, the `count` provided in the `summary()` method reflects *only* the merged PRs, completely omitting the total volume of evaluated PRs or unmerged PRs.
*   **Recommendation:** `CycleTimeMetric.summary` must be updated to explicitly report the total considered PR count versus the merged PR count, or the extraction phase must track non-merged entities to fulfill the `report_count` contract constraint.

### 2. Timezone Normalization at Boundaries (GAIN-PR-010)
**Severity:** **HIGH**
*   **Observation:** The Reference Architecture strictly mandates UTC normalization for the `PullRequest` model (Section 3.2: `created_at`, `closed_at`, `merged_at` as UTC). The Pydantic model (`src/gain/model/pr.py`) enforces type `datetime` but does not enforce UTC conversion or normalization via validators. Consequently, in `src/gain/metrics/monthly_stats.py`, the grouping logic `pr.created_at.strftime("%Y-%m")` relies on whatever timezone offset was parsed. A PR created on `2023-01-31T23:00:00-08:00` would bin into `2023-01` instead of the correct UTC bin `2023-02`.
*   **Recommendation:** Introduce Pydantic `@field_validator` hooks on all `datetime` fields in `PullRequest` to strictly enforce `datetime.astimezone(UTC)` or reject non-UTC datetimes, ensuring deterministic monthly bucket aggregation.

### 3. Negative Cycle Time Anomaly Handling
**Severity:** **MEDIUM**
*   **Observation:** `CycleTimeMetric.observations` explicitly discards records where `seconds < 0`. While this protects the mathematical aggregation, the Metric Catalog for `GAIN-PR-001` states `outlier_policy: retain_raw; visualize_with_percentiles`. Silently dropping negative values masks upstream data integrity issues or clock-skew anomalies.
*   **Recommendation:** If a PR has a negative cycle time, it violates causality and should ideally be failed at the Validation/Normalization layer (`validate_pull_requests`), generating a structured error quarantine record, rather than being silently filtered out in the metric engine.

### 4. Determinism & Numerical Reproducibility
**Severity:** **INFORMATIONAL** / **PASS**
*   **Observation:** The statistical logic explicitly implements deterministic percentile interpolation (`_percentile` in `cycle_time.py`) using rank-based fractional weighting rather than relying on external non-deterministic libraries. 
*   **Observation:** Grouping and cohort extraction in `monthly_stats.py` uses `sorted()` on deterministic keys (repositories, authors), ensuring consistent output across architectures.
*   **Conclusion:** Zero-LLM enforcement is intact. The metric generation is mathematically sound and strictly reproducible.

### 5. Future DORA and Flow Metric Compatibility
**Severity:** **INFORMATIONAL**
*   **Observation:** The Metric Catalog reserves `GAIN-DORA-001` (Change Lead Time to Production) and identifies the need for deployment/commit data. The `PullRequest` domain model is inherently limited to GitHub's PR lifecycle. 
*   **Observation:** `GAIN-PR-004` (PR WIP) identifies a limitation requiring snapshot collection. Currently, WIP inventory cannot be accurately retroactively modeled from state boundaries alone without explicit event logs or daily snapshot persistence.
*   **Recommendation:** To support `GAIN-DORA-001`, the Acquisition layer must be expanded to pull `Deployment` and `Commit` GraphQL entities, with relational mapping to `PullRequest`. To support `GAIN-PR-004`, introduce a dedicated `InventorySnapshot` routine that captures active `OPEN` states periodically.

---

## Action Plan
1. **Model Layer:** Add UTC enforcement validators to `gain.model.pr.PullRequest`.
2. **Validation Layer:** Enforce temporal causality (`merged_at >= created_at`) during canonical validation to quarantine negative elapsed times.
3. **Metric Engine:** Adjust `GAIN-PR-001` summary to return `total_prs_evaluated` and `merged_prs_count` to align with the catalog's null policy contract.
