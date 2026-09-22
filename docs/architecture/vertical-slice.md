# GAIN Enterprise Vertical Slice Architecture — Production Hardening

## 1. Scope & System Mission

This specification defines the production-hardened vertical slice of GAIN for enterprise-scale telemetry ingestion (40,000+ repositories):

```
GitHub GraphQL / REST Endpoints
              │
              ▼
  Distributed Work Coordination (RedisWorkQueue / InProcessQueue, TokenPool Lock)
              │
              ▼
  Resilient Paginated Collection (rate-limits, jittered backoff, live telemetry tap)
              │
              ▼
  Lossless Raw JSONL Capture (exact payloads + immutable run UUID provenance)
              │
              ▼
  Defensive Normalization & Quarantine (Pydantic v2, UTC enforcement, error containment)
              │
              ▼
  Canonical Domain Representation (gain.model.pr.PullRequest, transport-independent)
              │
              ▼
  Deterministic Metric Calculation (GAIN-PR-001 Cycle Time & GAIN-PR-010 Monthly Flow)
              │
              ▼
  Concurrency-Safe Columnar Storage (UUID .tmp files, atomic rename, .compaction.lock)
              │
              ▼
  Observability & Operational Verification (Prometheus registry, Error Catalog, 308 tests)
```

---

## 2. Ingestion & Distributed Work Coordination

At enterprise scale, single-process in-memory execution is insufficient. The vertical slice features:
- **`WorkQueue` Protocol**: Decouples job dispatching from worker execution (`enqueue`, `dequeue`, `mark_done`, `mark_failed`, `qsize`).
- **`RedisWorkQueue`**: Coordinates multi-pod worker pools across Kubernetes clusters with distributed acknowledgment and retry semantics.
- **`InProcessQueue`**: Provides a bounded-memory (`maxsize`) queue for development, testing, and single-host runs.
- **`GitHubTokenPool` Thread Safety**: Multi-worker token rotation synchronized via `threading.Lock`, preventing quota race conditions.
- **Live Rate-Limit Quota Tap**: Inspects `x-ratelimit-remaining` response headers and updates the `GITHUB_RATE_LIMIT_REMAINING` gauge in real time.

---

## 3. Lossless Raw Persistence & Replay Guarantee

Each fetched page is persisted verbatim in JSONL format with structured metadata:
- `ingestion_run_id`: Unique UUID per execution run
- `repository_name_with_owner`: Target repository identity
- `page_number` and `cursor`: Traversal pagination state
- `collected_at`: UTC timestamp of acquisition

The raw store is completely decoupled from canonical storage. If metric formulas or aggregation logic are revised, historical metrics can be deterministically re-evaluated via `gain.storage.replay.replay_run()` with zero network calls to GitHub.

---

## 4. Defensive Normalization & Error Quarantine

The normalization engine (`gain.schema.normalize_records`) maps raw GitHub nodes into canonical domain entities. Malformed or corrupted records are safely segregated into `normalization_errors.json` without aborting the batch run.

---

## 5. Transport-Independent Canonical Domain Model

The analytics engine operates exclusively on `gain.model.pr.PullRequest`:
- Strictly isolated from GraphQL artifacts (no cursors, edges, pageInfo, or connection wrappers).
- Enforces semantic invariants: `merged_at >= created_at`, `closed_at >= created_at`, and valid lifecycle states (`OPEN`, `CLOSED`, `MERGED`).
- Normalizes all timestamps to UTC.

---

## 6. Deterministic Numerical Analytics

- **`GAIN-PR-001` (Cycle Time)**:
  $$\text{CycleTime} = \text{merged\_at} - \text{created\_at}$$
  Calculates distribution percentiles (`p50`, `p75`, `p90`, `p95`, mean). Unmerged PRs are strictly excluded from cycle time.
- **`GAIN-PR-010` (Monthly PR Flow)**:
  Computes monthly balance-sheet flow (created, merged, closed, unmerged, and merge rate).
- **Zero-LLM Guardrail**: All analytics are pure Python algorithms explicitly bound to `docs/metrics/metric-catalog.yaml`.

---

## 7. Concurrency-Safe & Atomic Storage

- **Atomic Writes**: `write_canonical()`, `write_cycle_time_observations()`, and `write_monthly_stats()` write to temporary files (`<target>.tmp.<uuid>`) before performing an atomic POSIX rename (`replace()`), ensuring readers never observe incomplete or corrupted Parquet datasets.
- **Compaction Mutex Locking**: The dataset compactor (`gain.storage.compaction.Compactor`) protects partition compaction with an exclusive `.compaction.lock` file, preventing race conditions between concurrent worker pods.
- **Atomic Checkpoint Management**: Checkpoint persistence in `gain.storage.checkpoint` uses unique UUID temporary files to eliminate cursor write races.

---

## 8. Observability & Operational Governance

- **Prometheus Metrics Registry**: Modules expose operational metrics via `gain.telemetry.metrics.REGISTRY` (`INGESTION_PAGES_TOTAL`, `INGESTION_NODES_TOTAL`, `INGESTION_DURATION_SECONDS`, `GITHUB_RATE_LIMIT_REMAINING`, `MCP_REQUESTS_TOTAL`, `MCP_REQUEST_DURATION_SECONDS`).
- **Operational Error Catalog**: Structured runbooks in [`docs/errors/ERROR_CATALOG.md`](../errors/ERROR_CATALOG.md) define root cause analysis, mitigation actions, and alert rules.
- **Automated Verification**: The vertical slice is validated by 308 automated tests with 100% strict type safety across 193 files.
