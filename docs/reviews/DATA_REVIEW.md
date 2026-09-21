# GAIN Data Platform & Domain Model Audit

## Executive Summary
This independent audit evaluates the first production vertical slice of the GAIN system's data architecture, focusing on the ingestion of GitHub raw payloads, normalization, domain modeling, and analytics persistence. The audit was conducted against the constraints defined in `docs/REFERENCE_ARCHITECTURE.md` and the roles outlined for the `gain-data-engineer`. Overall, the implementation aligns well with the lossless ingestion and deterministic metric principles. However, a few structural enhancements are required to guarantee immutability, improve type safety at the storage boundary, and prepare the system for multi-entity extensibility.

## Findings by Severity

### HIGH
- **Immutability of Canonical Domain Models:** The `PullRequest` domain entity (`src/gain/model/pr.py`) enforces strict validation and forbids extra fields, but it lacks the `frozen=True` configuration. According to the Reference Architecture, canonical representations must have strict immutability guarantees.

### MEDIUM
- **Polars/Parquet Schema Inference Dependency:** In `src/gain/storage/analytics.py`, `write_canonical` relies on Polars' automatic schema inference from Python dictionaries (`pl.DataFrame(rows).write_parquet(path)`). If data is sparse or missing in early rows, Polars may incorrectly infer types (e.g., `Null` instead of `Int64` for optional fields like additions/deletions). Explicit PyArrow schemas should be enforced at the write boundary.
- **Entity Hardcoding in Schema & Storage:** `src/gain/schema.py` and `src/gain/storage/analytics.py` are heavily coupled to `PullRequest`. To support `Issue`, `Commit`, or `Repository`, the normalizer and storage layers require a generic dispatch mechanism or explicit abstractions to avoid monolithic growth.

### LOW
- **Provenance Timestamp Granularity:** In `src/gain/storage/raw.py`, the `collected_at` timestamp is generated inside `append_page()`. This means all nodes within a page share the identical ingestion timestamp. While acceptable, injecting the timestamp from the HTTP client response object would be more precise.

### INFORMATIONAL
- **Quarantine Resilience:** The error isolation mechanism in `normalize_records` (`src/gain/schema.py`) perfectly handles exceptions without crashing the ingestion run, adhering to the required resilience patterns.
- **UTC Enforcement:** Timezone awareness and normalization to UTC via `_parse_datetime` are correctly implemented, preventing temporal skew in metric calculations.

---

## Detailed Audit

### 1. Raw Data Model and Storage
- **File Hierarchy & Format:** The JSONL storage partitioned by `ingestion_run_id` (`{owner}__{name}__page-{page_number:05d}.jsonl`) properly supports lossless capture.
- **Replayability:** The exact GraphQL `node` payload is encapsulated under a top-level key alongside metadata. This fulfills the requirement for zero-API replay testing.
- **Partitioning Consideration:** As the system scales to incremental fetching rather than pure backfills, partitioning strictly by `run_id` may yield too many small files. Long-term, Hive-style partitioning (e.g., `year=/month=/day=`) may be preferable.

### 2. Provenance Metadata Completeness
- **Metadata Captured:** `ingestion_run_id`, `owner`, `name`, `page_number`, `cursor`, `repository_id`, `repository_name_with_owner`, and `collected_at`.
- **Verdict:** Highly complete. The system can definitively trace any canonical entity back to its exact API request, page number, and GraphQL cursor. 

### 3. Canonical PullRequest Entity Model (`src/gain/model/pr.py`)
- **Pydantic Validation:** Correctly leverages Pydantic v2. Field constraints (`gt=0`, `ge=0`) are appropriately defensive against upstream anomalies.
- **State Normalization:** `validate_state` successfully clamps string inputs to canonical upper-case enums.
- **Missing Feature:** `frozen=True` must be added to `model_config` to ensure that entities are read-only once instantiated.

### 4. Normalization Pipeline & Quarantine (`src/gain/schema.py`)
- **Resilience:** The try/except block wrapping `normalize_raw_record` successfully routes failures (`KeyError`, `ValidationError`, etc.) to an error array alongside the record index, keeping the ingestion job alive.
- **Safety:** Handles missing authors (`node.get("author") or {}`) gracefully, which is essential since GitHub regularly returns `null` for deleted users.

### 5. Persistence Layer (`src/gain/storage/analytics.py`)
- **Interface:** Encapsulates the serialization logic. Maps domain models to flat dicts (`pr.to_record()`) for Polars.
- **Parquet Outputs:** Polars successfully writes standard Parquet files. However, explicit schema definitions via `pyarrow` types should be introduced in future iterations to prevent inference errors on sparsely populated datasets (e.g., PRs with missing review decisions or metrics).

### 6. Future Entity Extensibility
- The current implementation is vertically sliced specifically for `PullRequest`.
- **Design Path Forward:** 
  1. Refactor `normalize_records` into a generic function: `normalize_records(records, model_class, normalizer_func)`.
  2. Implement an Entity Registry in the storage layer to map classes (`Issue`, `Review`, `User`) to their explicit PyArrow schemas for safe Parquet serialization.
  3. Keep `RawStore` as-is, as its signature is already completely entity-agnostic.

---

## Recommendations

1. **Enforce Immutability:** Update `PullRequest.model_config` to include `frozen=True`.
2. **Abstract Normalization:** Generalize `src/gain/schema.py` so it can accept multiple normalizer functions mapped to specific GraphQL type endpoints.
3. **Explicit Schemas:** Move away from Polars' automatic inference by maintaining a mapping of Pydantic models to exact PyArrow/Polars schemas in `write_canonical`.
4. **Pass Timestamps from Client:** Update `RawStore.append_page` to accept `collected_at` as a parameter, generated immediately after the HTTP API request returns, rather than at the moment of file writing.
