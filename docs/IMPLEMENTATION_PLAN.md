# GAIN Implementation Plan — Production Vertical Slice 1

## 1. Executive Summary

This implementation plan specifies the technical execution, engineering requirements, and verification criteria for **Vertical Slice 1** of the GAIN (GitHub AI Intelligence Network) platform.

Vertical Slice 1 establishes the baseline production data pipeline:
```
GitHub GraphQL -> Acquisition -> Raw API Capture -> Validation -> Canonical PullRequest -> Deterministic Cycle Time (GAIN-PR-001) -> Persisted Observations -> Automated Tests
```

---

## 2. Engineering Requirements & Standards

The implementation adheres to strict production engineering standards:

1. **Packaging & Configuration**:
   - Centralized `pyproject.toml` managing dependencies, build tools (`hatchling`), pytest configuration, and static analysis settings.
   - Pydantic-based settings management (`gain.config.Settings`) supporting environment variables (`GAIN_*`), `.env` files, and defaults.

2. **Type Safety & Static Analysis**:
   - Strict `mypy` compliance across `src` and `tests` (`strict = true`).
   - Strict `ruff` compliance for formatting, unused imports, modern syntax (`UP`), bug prevention (`B`), and flake8 conventions (`E`, `F`, `I`, `SIM`).

3. **Structured Logging & Observability**:
   - Contextual JSON structured logging via `structlog`.
   - Ingestion run ID propagation across raw storage, normalization reports, and metric persistence.

4. **Credential Security**:
   - Tokens loaded from environment (`GITHUB_TOKEN` / `GAIN_GITHUB_TOKEN`).
   - Zero credential logging; tokens excluded from representations, payloads, and error messages.

5. **Resilience & Fault Tolerance**:
   - Bounded exponential backoff with jitter ceiling.
   - Proactive handling of GitHub rate limits (HTTP 403, 429) using `Retry-After` and `x-ratelimit-reset` headers.
   - Graceful pagination with cursor validation to prevent infinite loops.

6. **Deterministic Verification & Testing**:
   - Zero reliance on external network calls during test execution (`httpx.MockTransport` and synthetic JSON fixtures).
   - Strict percentile calculation algorithm with reproducible numerical outputs.
   - Isolated integration tests covering end-to-end execution.

---

## 3. Scope Boundaries (Non-Goals)

To preserve architectural focus and integrity, the following capabilities are explicitly deferred to later milestones:
- No LLM agent workflows, prompt chains, or generative models.
- No GitHub or GAIN Model Context Protocol (MCP) servers.
- No AI developer attribution or AI ROI modeling.
- No web UI or interactive frontend dashboards.
- No Jira bidirectional synchronization or requirements expansion.

---

## 4. Acceptance Criteria Verification Matrix

| AC # | Acceptance Criterion | Implementation Component | Verification Test |
|:---|:---|:---|:---|
| **AC-1** | GitHub GraphQL response acquired | `GitHubGraphQLClient.iter_pull_request_pages` | `test_github_client.py`, `test_vertical_slice.py` |
| **AC-2** | Raw response persisted | `RawStore.append_page` | `test_vertical_slice.py` |
| **AC-3** | Associated provenance metadata | `RawStore` metadata envelope | `test_vertical_slice.py` |
| **AC-4** | Canonical normalization | `normalize_records` -> `PullRequest` | `test_schema.py`, `test_vertical_slice.py` |
| **AC-5** | Deterministic cycle time | `CycleTimeMetric.observations` & `summary` | `test_metrics.py`, `test_vertical_slice.py` |
| **AC-6** | Identifies metric ID and version | `GAIN-PR-001` v1 in `MetricCatalog` | `test_metrics.py`, `test_vertical_slice.py` |
| **AC-7** | Explicit invalid data handling | `normalize_records` error collection | `test_schema.py`, `test_vertical_slice.py` |
| **AC-8** | Zero LLM requirement | Pure Python arithmetic & statistics | `test_vertical_slice.py` (runtime assertion) |
| **AC-9** | All automated tests pass | Full test suite across unit & integration | `pytest -v` (31+ tests passing) |
| **AC-10**| Extensible to other entities | Generic `RawStore` & domain model pattern | `test_vertical_slice.py` (Entity test) |

---

## 5. Execution Steps

1. **Configure Linting & Typing**:
   - Update `pyproject.toml` with `ruff` per-file ignores for Typer CLI options and `mypy` overrides for `yaml`.
2. **Implement GitHub API Version Tracking**:
   - Add `X-GitHub-Api-Version: 2022-11-28` to `GitHubGraphQLClient`.
3. **Refactor Code for Strict Typing & Clean Linting**:
   - Fix line lengths, type annotations, and `datetime.UTC` across `src/gain` and `tests`.
4. **Author End-to-End Vertical Slice Test**:
   - Create `tests/test_vertical_slice.py` directly exercising and asserting all 10 acceptance criteria in a unified integration suite.
5. **Execute Static Analysis & Test Suite**:
   - Run `ruff check src tests`, `mypy src tests`, and `pytest -v`.
6. **Audit & Document Results**:
   - Document files created/modified, test results, and compliance.
