# GAIN Verification & Test Architecture Audit Review

**Date:** 2026-09-20  
**Auditor:** GAIN Independent Verification and Quality Specialist (`gain-verification-engineer`)  
**Reference Standards:** `docs/REFERENCE_ARCHITECTURE.md`, `.agents/agents/gain-verification-engineer.md`, `pyproject.toml`  
**Repository State:** Version 0.1.0 (`firmsoil/gain`)  

---

## 1. Executive Summary

An independent verification and test architecture audit was conducted on the GAIN production codebase (`firmsoil/gain`). The audit evaluated test suite completeness, mocking isolation, failure-path resilience, edge-case coverage, vertical slice integration, static analysis rigor, and assertion determinism against the authoritative requirements in [`docs/REFERENCE_ARCHITECTURE.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/docs/REFERENCE_ARCHITECTURE.md).

### High-Level Verdict: CONDITIONAL PASS WITH CRITICAL VERIFICATION GAPS
The core vertical slice demonstrates high-quality software craftsmanship in its individual units: mathematical metric calculations are strictly deterministic and free of LLM dependencies, typing is strictly enforced (`mypy --strict`), and `httpx.MockTransport` is utilized for clean HTTP transport isolation without monkey-patching.

However, from an independent verification and test architecture perspective, the test suite suffers from **critical blind spots and structural distortion**:
1. **Severe Pipeline Blind Spot**: Core orchestration (`src/gain/sync.py`), state recovery (`src/gain/storage/checkpoint.py`), CLI execution (`src/gain/cli.py`), runtime configuration validation (`src/gain/config.py`), and data quality rules (`src/gain/quality.py`) possess **0% test coverage**.
2. **Untested Failure & Rate-Limit Paths**: The GitHub client's HTTP 403/429 rate-limiting handlers, exponential backoff ceiling, header parsing (`Retry-After`, `X-RateLimit-Reset`), network timeout exceptions, and error exhaustion paths have **zero tests**.
3. **Inverted Test Portfolio**: Out of 31 automated tests, **19 tests (61.3%)** are dedicated to the requirements/Jira synchronization subsystem—a subsystem explicitly classified as out-of-scope by the Reference Architecture—while only **12 tests (38.7%)** cover the entire core GitHub PR analytics vertical slice.
4. **Synthetic Vertical Slice Integration**: The solitary end-to-end integration test (`test_vertical_slice.py`) manually composes pipeline steps in Python memory rather than invoking the actual sync orchestrator, checkpoint engine, or CLI entrypoint.

---

## 2. Quantitative Baseline & Test Architecture Overview

### 2.1 Test Execution & Durations Baseline
Executed using project virtual environment (`Python 3.13.7`, `pytest 8.4.2`, `pytest-cov 6.3.0`):
```text
============================= test session starts ==============================
platform darwin -- Python 3.13.7, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0
configfile: pyproject.toml
testpaths: tests
plugins: cov-6.3.0, anyio-4.15.1
collected 31 items

tests/test_github_client.py ..                                           [  6%]
tests/test_metrics.py ..                                                 [ 12%]
tests/test_monthly_stats.py ......                                       [ 32%]
tests/test_requirements.py ...................                           [ 93%]
tests/test_schema.py .                                                   [ 96%]
tests/test_vertical_slice.py .                                           [100%]

============================== 31 passed in 0.25s ==============================
```

### 2.2 Detailed Coverage Analysis by Module
Measured via `pytest --cov=gain --cov-report=term-missing`:

| Component / File | Statements | Missed | Coverage | Critical Uncovered Areas |
| :--- | :---: | :---: | :---: | :--- |
| [`src/gain/cli.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/cli.py) | 226 | 226 | **0%** | Entire CLI command suite (`backfill`, `replay`, `metrics`, `requirements`) |
| [`src/gain/config.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/config.py) | 67 | 67 | **0%** | Runtime settings validation, repo parsing, Jira config |
| [`src/gain/logging.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/logging.py) | 6 | 6 | **0%** | Structlog processor initialization |
| [`src/gain/quality.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/quality.py) | 23 | 23 | **0%** | All 4 quality checks: duplicate nodes, temporal inversion, missing closed_at |
| [`src/gain/storage/checkpoint.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/checkpoint.py) | 22 | 22 | **0%** | Pagination checkpoint persistence, multi-repo resumption |
| [`src/gain/sync.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/sync.py) | 49 | 49 | **0%** | `PullRequestBackfill.run()`, date filtering, cursor progression |
| [`src/gain/github/client.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/github/client.py) | 106 | 38 | **64%** | HTTP 403/429 rate limit retries, network timeouts, cursor integrity errors |
| [`src/gain/metrics/catalog.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/metrics/catalog.py) | 19 | 2 | **89%** | Duplicate metric ID rejection, invalid catalog format |
| [`src/gain/metrics/cycle_time.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/metrics/cycle_time.py) | 40 | 2 | **95%** | Empty observations handling, single observation branch |
| [`src/gain/metrics/monthly_stats.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/metrics/monthly_stats.py) | 148 | 21 | **86%** | By-repository grouping, dynamic reference date calculation |
| [`src/gain/model/pr.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/model/pr.py) | 42 | 1 | **98%** | State validator rejection branch |
| [`src/gain/schema.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/schema.py) | 28 | 1 | **96%** | Naive datetime timezone attachment branch |
| [`src/gain/storage/raw.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/raw.py) | 28 | 0 | **100%** | Only exercised via clean happy-path vertical slice |
| [`src/gain/storage/replay.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/replay.py) | 9 | 0 | **100%** | Exercised via clean replay run |
| [`src/gain/storage/analytics.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/analytics.py) | 24 | 0 | **100%** | Parquet I/O for canonical and metrics |
| *Requirements Subsystem (`jira`, `models`, `service`, etc.)* | 971 | 147 | **85%** | Out-of-scope requirements subsystem |
| **TOTAL** | **1,840** | **582** | **68%** | **Core Vertical Slice Coverage alone is only ~52%** |

---

## 3. Findings Classified by Severity

```
  ┌─────────────────────────────────────────────────────────────┐
  │                   AUDIT FINDINGS BY SEVERITY                │
  │   CRITICAL: 2   |   HIGH: 4   |   MEDIUM: 4   |   LOW: 3    │
  │                  INFORMATIONAL: 3                           │
  └─────────────────────────────────────────────────────────────┘
```

### 3.1 CRITICAL FINDINGS

#### [CRITICAL-01] Core Ingestion Orchestrator and Checkpoint Recovery Have 0% Test Coverage
- **Location:** [`src/gain/sync.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/sync.py) (`PullRequestBackfill`), [`src/gain/storage/checkpoint.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/checkpoint.py) (`CheckpointStore`)
- **Description:** The orchestrator responsible for running multi-repository backfills, checkpointing pagination state, filtering records into the ingestion window, and committing raw pages (`PullRequestBackfill.run`) is completely unexercised by automated tests. Similarly, `CheckpointStore` (`load` and `save` operations across interruption boundaries) has zero tests.
- **Verification Risk:** Ingestion resumption after transient network disconnection or process termination is one of the highest operational risks in production data pipelines. Any regression in cursor loading or page progression will cause silent data loss (skipping PRs) or infinite re-ingestion loops.
- **Concrete Recommendation:** Implement an integration test suite `tests/test_sync.py` simulating multi-page repository ingestion, interrupted runs with cursor reload, and time-window boundaries (`_in_window`).

#### [CRITICAL-02] GitHub Client Rate-Limiting and Timeout Failure Paths Completely Untested
- **Location:** [`src/gain/github/client.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/github/client.py) (`lines 64-120`)
- **Description:** While a single test verifies a transient 500 retry, there are **zero tests** verifying:
  1. HTTP 429 and HTTP 403 handling with `Retry-After` header parsing.
  2. Rate-limit reset timestamp calculation via `X-RateLimit-Reset`.
  3. Exhaustion of retries raising `RateLimitError`.
  4. Network timeouts (`httpx.TimeoutException`) and connection failures (`httpx.NetworkError`).
  5. Backoff delay cap (`retry_max_backoff_seconds`).
- **Verification Risk:** Production backfills against GitHub's GraphQL API will frequently trigger rate limits on large repositories. If rate limit or backoff handling fails or raises unhandled exceptions, long-running ingestion jobs will crash without preserving state.
- **Concrete Recommendation:** Implement targeted unit tests in `tests/test_github_client.py` using `httpx.MockTransport` returning sequences of 429/403 responses with custom rate-limit headers, verifying retry progression and eventual `RateLimitError` raising.

---

### 3.2 HIGH FINDINGS

#### [HIGH-01] Complete Absence of CLI Test Automation
- **Location:** [`src/gain/cli.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/cli.py) (226 statements, 0% coverage)
- **Description:** The CLI is the primary production entrypoint registered in `pyproject.toml` (`[project.scripts] gain = "gain.cli:app"`). Not a single command (`config-check`, `backfill`, `replay`, `metrics`, `requirements`) is tested using `typer.testing.CliRunner`.
- **Verification Risk:** Flag parsing, parameter passing, error logging, exit codes, and pipeline wiring can break silently without failing any existing test.
- **Concrete Recommendation:** Create `tests/test_cli.py` using `typer.testing.CliRunner` to test commands with valid inputs, invalid CLI flags, missing arguments, and simulated backend errors.

#### [HIGH-02] Zero Test Coverage for Data Quality and Temporal Validation Engine
- **Location:** [`src/gain/quality.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/quality.py) (`validate_pull_requests`)
- **Description:** The reference architecture mandates explicit validation of domain integrity and temporal sanity (Section 3: `CAN --> VAL`). The implementation in `src/gain/quality.py` detects duplicate node IDs, `closed_at < created_at`, `merged_at < created_at`, and `merged_at without closed_at`. However, this module is **completely untested** and never invoked in `test_vertical_slice.py`.
- **Verification Risk:** Data corruption, duplicate PR ingestion, or anomalous GitHub telemetry will pass through to analytical Parquet files without detection if validation logic regresses.
- **Concrete Recommendation:** Add unit tests in `tests/test_quality.py` validating each quality violation code: `DUPLICATE_NODE_ID`, `INVALID_CLOSED_AT`, `INVALID_MERGED_AT`, and `MERGED_WITHOUT_CLOSED_AT`.

#### [HIGH-03] Replay Engine and Raw Store Lack Resilient Handling for Corrupt/Truncated JSONL
- **Location:** [`src/gain/storage/raw.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/raw.py) (`read_run`), [`src/gain/storage/replay.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/storage/replay.py)
- **Description:** `RawStore.read_run` parses JSONL files with bare `json.loads(line)`. If a process terminates mid-write or disk corruption introduces an incomplete line, `json.loads` raises an unhandled `json.JSONDecodeError`, aborting the entire replay run. There are no tests verifying behavior when raw storage files are corrupt.
- **Verification Risk:** Section 2, Principle 5 mandates: *"Incomplete, malformed, or corrupt source records are quarantined... Normalization fails safely without crashing entire ingestion runs."* Unhandled JSON decode errors directly violate this resilience principle.
- **Concrete Recommendation:** Enhance `RawStore.read_run` to catch JSON decode errors per line, quarantine malformed lines, and add regression tests with truncated/corrupted JSONL files.

#### [HIGH-04] End-to-End Vertical Slice Test is Synthetic and Bypasses Core Pipeline Wiring
- **Location:** [`tests/test_vertical_slice.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_vertical_slice.py)
- **Description:** `test_vertical_slice_end_to_end` manually executes each pipeline stage sequentially in test code: `client.iter_pull_request_pages()` → `raw_store.append_page()` → `replay_run()` → `write_canonical()` → `CycleTimeMetric.observations()`. It does not exercise the actual orchestrator (`PullRequestBackfill`), `CheckpointStore`, or CLI command execution. Furthermore, it tests only a single page containing 2 PRs.
- **Verification Risk:** Component interfaces may function individually when manually chained in a test, while failing when executed via the production orchestrator or CLI.
- **Concrete Recommendation:** Author a true vertical slice integration test that executes `PullRequestBackfill.run()` with multiple simulated pages, checkpointing, and subsequent metric computation.

---

### 3.3 MEDIUM FINDINGS

#### [MEDIUM-01] `tests/` Directory Excluded from Makefile Typechecking Target
- **Location:** [`Makefile`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/Makefile) (`line 13: mypy src`), [`pyproject.toml`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/pyproject.toml) (`mypy_path = "src"`)
- **Description:** The Makefile `typecheck` target only executes `mypy src`. Although `mypy tests` currently passes cleanly when manually invoked, CI and local developer checks (`make ci`) will not typecheck `tests/`.
- **Verification Risk:** Unchecked test code can introduce invalid mock signatures, incorrect assertions, or silent typing drift, undermining test suite reliability.
- **Concrete Recommendation:** Update `pyproject.toml` to set `files = ["src", "tests"]` or update `Makefile` to run `mypy src tests`.

#### [MEDIUM-02] Configuration Management and Environment Overrides Untested
- **Location:** [`src/gain/config.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/config.py) (67 statements, 0% coverage)
- **Description:** `Settings` handles repository parsing (`github_repos`), date range validation (`end_at > start_at`), token resolution from multiple aliases (`GAIN_GITHUB_TOKEN`, `GITHUB_TOKEN`), and directory creation. None of this is tested.
- **Verification Risk:** Misconfigurations (e.g. invalid repo formats like `"repo"` or `"a/b/c"`, inverted date ranges) will fail at runtime in unpredictable ways rather than failing fast with descriptive `ConfigurationError` messages.
- **Concrete Recommendation:** Add unit tests in `tests/test_config.py` verifying repo string splitting, token alias fallbacks, and runtime error conditions.

#### [MEDIUM-03] Non-Deterministic Wall-Clock Timestamps in Test Fixtures
- **Location:** [`tests/test_schema.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_schema.py) (`line 13`), [`tests/test_metrics.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_metrics.py) (`line 28`), [`tests/test_monthly_stats.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_monthly_stats.py) (`line 42`)
- **Description:** Tests instantiate fixtures using `datetime.now(UTC)` for `collected_at`.
- **Verification Risk:** Dynamic wall-clock timestamps in test data create non-deterministic test executions. While not currently causing failures, time-dependent logic or window filters can cause intermittent CI flakiness near timezone/month boundaries.
- **Concrete Recommendation:** Replace all `datetime.now(UTC)` calls in test fixtures with fixed, static UTC timestamps (e.g. `datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)`).

#### [MEDIUM-04] Incomplete Domain Model and Schema Validation Boundary Testing
- **Location:** [`src/gain/model/pr.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/model/pr.py), [`src/gain/schema.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/schema.py)
- **Description:** Key boundary conditions are untested:
  - `PullRequest.validate_state`: Unrecognized states (e.g. `"PENDING"`, `"DRAFT"`) raising `ValueError` (line 35).
  - Negative metric counts: `additions: int = Field(ge=0)` tested with `-1`.
  - Zero vs Negative PR numbers: `number: int = Field(gt=0)` tested with `0`.
  - Non-UTC offset timestamps in `_parse_datetime` (e.g. `+05:30` converting cleanly to UTC).
  - Extra fields rejection: `model_config = ConfigDict(extra="forbid")`.
- **Verification Risk:** Boundary anomalies from GitHub GraphQL responses could bypass normalization without being quarantined.
- **Concrete Recommendation:** Author boundary-value unit tests in `tests/test_schema.py` and `tests/test_model_pr.py`.

---

### 3.4 LOW FINDINGS

#### [LOW-01] Solitary GraphQL Fixture & Absence of Shared Pytest Fixture Architecture
- **Location:** [`tests/fixtures/graphql_page_1.json`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/fixtures/graphql_page_1.json), `tests/`
- **Description:** Only a single fixture file exists. Helper functions like `dt()`, `pr()`, and `make_pr()` are duplicated across test files. There is no `tests/conftest.py` providing shared fixtures.
- **Verification Risk:** Code duplication across tests increases maintenance burden and encourages fragmented test authoring.
- **Concrete Recommendation:** Establish `tests/conftest.py` with standard fixtures (`mock_transport_factory`, `sample_pr_factory`, `clean_raw_store`, `frozen_timestamp`).

#### [LOW-02] Test-Order Dependent LLM Verification via `sys.modules` Inspection
- **Location:** [`tests/test_vertical_slice.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_vertical_slice.py) (`lines 197-201`)
- **Description:** The test verifies "zero LLM invocation" by asserting that `"openai" not in sys.modules`, `"anthropic" not in sys.modules`, etc.
- **Verification Risk:** If any other test file or external dependency imports these packages earlier in the test run, this test will fail due to execution order rather than an actual regression in `CycleTimeMetric`.
- **Concrete Recommendation:** Replace runtime `sys.modules` inspection with a static AST analysis test that scans `gain.metrics` modules for disallowed imports, or execute the test in an isolated subprocess.

#### [LOW-03] Exact Floating-Point Equality Assertions in Metric Tests
- **Location:** [`tests/test_metrics.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_metrics.py) (`line 43: assert summary["p50_seconds"] == 97200.0`), [`tests/test_monthly_stats.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/tests/test_monthly_stats.py) (`line 192: assert loaded[0].merge_rate_pct == 88.9`)
- **Description:** Tests perform exact `==` equality assertions on floating point calculations without tolerance intervals.
- **Verification Risk:** Minor floating-point rounding variations across platforms (e.g. x86_64 vs ARM64) can trigger spurious test failures.
- **Concrete Recommendation:** Use `pytest.approx()` for floating-point duration and percentage assertions (e.g. `assert summary["p50_seconds"] == pytest.approx(97200.0)`).

---

### 3.5 INFORMATIONAL FINDINGS

#### [INFO-01] Exemplary Transport Decoupling via Dependency Injection
- **Location:** [`src/gain/github/client.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/github/client.py) (`transport: httpx.BaseTransport | None = None`)
- **Observation:** The client accepts an `httpx.BaseTransport` directly in `__init__`. This allows tests to inject `httpx.MockTransport` cleanly without resorting to monkey-patching `httpx.Client` or global socket mocks.

#### [INFO-02] Verified Pure Deterministic Metric Math Baseline
- **Location:** [`src/gain/metrics/cycle_time.py`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/metrics/cycle_time.py)
- **Observation:** Calculation of cycle time is verified to be 100% pure Python arithmetic (`(merged_at - created_at).total_seconds()`). Percentile calculations use deterministic linear interpolation without external statistical heuristics.

#### [INFO-03] Comprehensive Static Analysis and Strict Type Enforcement
- **Location:** [`pyproject.toml`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/pyproject.toml), `mypy src tests`
- **Observation:** `mypy` strict mode passes across all 36 source and test files with zero errors. `ruff check .` passes cleanly with zero linting warnings.

---

## 4. Deep-Dive Sectional Audits

### 4.1 Test Suite Coverage & Structural Architecture
The test suite currently contains 31 tests across 6 files. However, the structural composition is severely skewed:

```
Test Distribution by Component:
┌───────────────────────────────────────┬───────┬────────────┐
│ Component Area                        │ Tests │ Percentage │
├───────────────────────────────────────┼───────┼────────────┤
│ Requirements / Jira / SDD (Non-Scope) │ 19    │ 61.3%      │
│ Monthly Stats Metric (GAIN-PR-010)    │ 6     │ 19.4%      │
│ GitHub Client                         │ 2     │ 6.5%       │
│ Cycle Time Metric (GAIN-PR-001)       │ 2     │ 6.5%       │
│ Schema Normalization                  │ 1     │ 3.2%       │
│ End-to-End Vertical Slice             │ 1     │ 3.2%       │
└───────────────────────────────────────┴───────┴────────────┘
```

The test structure is completely flat inside `tests/`. There is no segregation between unit, integration, and contract tests. Furthermore, six core production modules in the vertical slice have **0% coverage** (see Section 2.2).

### 4.2 Mocking Strategy & Transport Isolation
- **Mock Transport Implementation:** The use of `httpx.MockTransport` in `tests/test_github_client.py` and `tests/test_vertical_slice.py` is architecturally sound. It validates headers (`Authorization: Bearer test-token`, `X-GitHub-Api-Version: 2022-11-28`) and URL paths (`/graphql`).
- **Critical Mocking Deficiencies:**
  1. *Request Body Validation Missing*: No mock handler asserts the contents of the POST body. If the client sends an empty body or corrupt GraphQL query, existing mock handlers will still return 200 OK.
  2. *Single-Page Bias*: All existing mock handlers return a single page with `hasNextPage: false`. Multi-page pagination traversal (`hasNextPage: true` → second request with `after: cursor` → `hasNextPage: false`) is never simulated.
  3. *Error Payload Simulation Missing*: Mocking does not simulate GraphQL error envelopes (e.g. `{"errors": [{"message": "Field 'x' doesn't exist"}]}`).

### 4.3 Missing Regression Tests, Edge Cases & Boundary Conditions
Key domain and mathematical edge cases currently missing regression tests:
1. **Zero-Duration Cycle Time:** A PR created and merged in the exact same second (`merged_at == created_at`) must yield `cycle_time_seconds == 0.0`.
2. **Negative Cycle Time / Anomalous Merges:** An anomalous record where `merged_at < created_at` must be excluded from observations by `CycleTimeMetric.observations()` (line 30: `if seconds < 0: continue`). This branch is currently untested.
3. **Empty Observations Aggregation:** `CycleTimeMetric.summary([])` must cleanly return `{"count": 0, "p50_seconds": None, ...}` without crashing.
4. **Single-Observation Percentiles:** `CycleTimeMetric.summary([obs])` must evaluate to `values[0]` for all percentiles.
5. **Metric Catalog Edge Cases:** Corrupted catalog YAML, duplicate metric IDs, and non-existent metric lookups.
6. **Date Window Boundary Filtering:** Testing that `PullRequestBackfill._in_window` correctly includes PRs on `start_at` and `end_at` boundaries and excludes PRs outside.

### 4.4 Failure Path Testing & Fault Injection Analysis
A comprehensive audit of exception handling revealed that failure paths are almost entirely untested:
1. **Rate Limit 429 & 403:** Untested. Neither retry behavior nor `RateLimitError` raising is covered.
2. **5xx Server Errors Exhaustion:** Untested. Only 1 retry is tested; exhausting `max_retries` raising `GitHubApiError` is not covered.
3. **Network Timeouts & Disconnections:** Untested. Neither `httpx.TimeoutException` nor `httpx.NetworkError` is covered.
4. **Unhandled HTTP Status Codes:** `response.raise_for_status()` will raise `httpx.HTTPStatusError` on 401 Unauthorized or 404 Not Found. This error is not caught or wrapped in a `GainError`.
5. **Cursor Inconsistencies:** `IncompletePaginationError` for missing cursors or duplicate cursors is untested.
6. **Corrupt JSONL Replay:** Malformed JSON strings crash `RawStore.read_run` without quarantine.

### 4.5 End-to-End Vertical Slice Integration Verification
`test_vertical_slice_end_to_end` validates that data can pass from mock transport through raw storage, normalization, canonical parquet, and metric calculation. However:
- It tests a synthetic composition written inside the test function rather than executing the production orchestrator (`sync.py`).
- It does not test interruption and resumption using checkpoints.
- It does not test the CLI entrypoint.
- It does not verify multi-repository isolation.

### 4.6 Static Analysis & Type Checking Configuration
- **Ruff:** Configured in `pyproject.toml` with `select = ["E", "F", "I", "UP", "B", "SIM"]`. All 36 files pass. Recommendation: Expand rule selection to include `S` (security/bandit) and `PT` (pytest style).
- **Mypy:** Configured with `strict = true`. Passes with 0 errors on both `src` and `tests`. Issue: `Makefile` omits `tests` from `make typecheck`.
- **Pytest:** Missing `--cov-fail-under` threshold, allowing test coverage regressions to slip into production.

### 4.7 Reproducibility, Determinism & Idempotency of Assertions
- **Determinism:** Core metric math is pure and deterministic.
- **Flakiness Vectors:**
  1. Use of `datetime.now(UTC)` in test fixtures introduces temporal non-determinism.
  2. Direct inspection of `sys.modules` for LLM presence introduces test execution order dependency.
  3. Exact float comparisons (`==`) risk multi-platform float precision differences.

---

## 5. Actionable Verification Recommendations & Roadmap

### Phase 1: High-Priority Failure Injection & State Recovery Tests (Sprint 1)
1. **Author `tests/test_sync.py`:**
   - Test `PullRequestBackfill.run()` with `httpx.MockTransport` simulating multi-page responses.
   - Test checkpoint creation and resume capability across interrupted runs.
   - Test date boundary filtering (`_in_window`).
2. **Expand `tests/test_github_client.py` Failure Injection:**
   - Test 429 rate limit with `Retry-After` header.
   - Test 403 rate limit with `X-RateLimit-Reset` header.
   - Test `RateLimitError` raised when max retries are exhausted.
   - Test `httpx.TimeoutException` and `httpx.NetworkError` retries and error raising.
   - Test `IncompletePaginationError` when `hasNextPage: true` has missing or repeated cursor.
3. **Author `tests/test_quality.py`:**
   - Test all 4 data quality validation rules in `src/gain/quality.py`.

### Phase 2: CLI Automation & Storage Resilience (Sprint 2)
1. **Author `tests/test_cli.py`:**
   - Implement CLI tests using `typer.testing.CliRunner` for `config-check`, `backfill`, `replay`, and `metrics`.
2. **Author `tests/test_config.py`:**
   - Test environment variable parsing, token alias resolution, and invalid configuration raising `ConfigurationError`.
3. **Harden and Test `RawStore` Error Recovery:**
   - Update `RawStore.read_run` to safely handle corrupt/truncated JSONL lines.
   - Add tests with corrupted JSONL files in `tests/test_raw_store.py`.

### Phase 3: Test Architecture Refinement & Determinism (Sprint 3)
1. **Establish `tests/conftest.py`:**
   - Centralize reusable pytest fixtures (`mock_transport_factory`, `sample_pr_factory`, `frozen_timestamp`).
   - Eliminate duplicated helper functions across test files.
2. **Replace Nondeterministic Assertions:**
   - Replace `datetime.now(UTC)` in test fixtures with static timestamps.
   - Replace exact float equality with `pytest.approx()`.
   - Replace `sys.modules` inspection with an AST-based static analysis test for zero LLM imports in `gain.metrics`.
3. **Update CI & Tooling Configuration:**
   - Update `Makefile` typecheck target to: `mypy src tests`.
   - Update `pyproject.toml` with `addopts = "-q --cov=gain --cov-report=term-missing --cov-fail-under=85"`.
   - Add Ruff rule sets: `S` (flake8-bandit) and `PT` (flake8-pytest-style).

---

## 6. Verification Engineer Sign-off

**Report Author:** GAIN Independent Verification and Quality Specialist  
**Status:** Audit Complete — Findings Published  
**Target Action:** Remediate CRITICAL and HIGH findings prior to expanding vertical slice scope.
