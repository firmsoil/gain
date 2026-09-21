# GAIN — GitHub AI Intelligence Network

GAIN is a production-oriented Python data product for turning GitHub Pull Request telemetry into reproducible engineering-flow analytics.

## First implemented vertical slice

```text
GitHub GraphQL API
    -> authenticated paginated PR collection
    -> raw JSONL + provenance
    -> canonical PR records
    -> GAIN-PR-001 cycle-time metric
    -> Parquet outputs + run reports
```

The implementation deliberately treats `createdAt -> mergedAt` as **observable PR lifecycle elapsed time**, not developer coding time.

## Architecture & Platform Design

The complete system architecture is documented in:
* **Architecture Specification**: [`docs/OVERALL_ARCHITECTURE.md`](docs/OVERALL_ARCHITECTURE.md)
* **Interactive Architecture Diagram**: [`docs/architecture/gain_overall_architecture.html`](docs/architecture/gain_overall_architecture.html)
* **Reference Architecture**: [`docs/REFERENCE_ARCHITECTURE.md`](docs/REFERENCE_ARCHITECTURE.md)

### Core Subsystems

- `gain.adapters` — enterprise source adapters (Jira, Linear, CI/CD deployments).
- `gain.github.client` — GraphQL transport, retries, rate-limit handling, pagination.
- `gain.sync` — backfill orchestration and checkpoints.
- `gain.storage.raw` — replayable raw payloads and provenance metadata (`RawStore`).
- `gain.model` — transport-independent canonical domain models (`PullRequest`, `CanonicalIssue`, `CanonicalDeployment`, `CanonicalCommit`, `AiDeveloperTelemetry`).
- `gain.metrics` & `gain.services` — deterministic zero-LLM analytics engines (PR Cycle Time, Monthly Flow, AI Impact, 4-Stage AI ROI, DORA, Issue Velocity).
- `gain.mcp` — governed Model Context Protocol (MCP) server over SSE and Stdio.
- `gain.agent` — autonomous Engineering Intelligence Agent with 7-tier claim classification.
- `gain.quality` — canonical data-quality validation.
- `gain.cli` — unified operator CLI (`gain demo`, `gain backfill`, `gain dora`, `gain issues`, `gain agent`, `gain mcp`).

## Requirements → Jira → SDD

GAIN includes a separate upstream requirements-engineering layer. It does not alter or depend on
the GitHub telemetry pipeline.

```text
Business Context → AI Story Draft → Human Validation → Approved Story
                                                      ├→ Jira (optional)
                                                      └→ SDD Specification Seed → Spec Kit workflow
```

AI output is always a non-authoritative draft. A named human must approve a validated story before
Jira export or promotion to an SDD seed. See
[the requirements/Jira/SDD architecture](docs/architecture/requirements-jira-sdd.md) and
[the feature specification](specs/002-requirements-jira-sdd/README.md).

## Quick start

Requirements: Python 3.12+, a GitHub token with access to the repositories being analyzed, and `uv`.

```bash
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
cp .env.example .env
# edit .env; never commit secrets

# Validate configuration
 gain config-check

# Backfill configured repositories
 gain backfill

# Compute metrics from the canonical dataset
 gain compute
```

The default output directory is `./data` and can be changed through environment variables.

## Live Demo: Spinnaker PR Analytics

GAIN provides an end-to-end live demonstration script ([`scripts/demo_live.py`](scripts/demo_live.py)) that connects directly to the GitHub GraphQL API, ingests real-time pull requests from a live repository, normalizes them into canonical domain models, validates data quality, and outputs both **GAIN-PR-001** cycle-time percentiles and **GAIN-PR-010** monthly flow statistics.

### 1. Run the Live Demo Script against Spinnaker

```bash
# Provide your GitHub token (or authenticate via `gh auth login`)
export GITHUB_TOKEN=$(gh auth token)

# Run live PR telemetry analytics against firmsoil/spinnaker
python scripts/demo_live.py --repo firmsoil/spinnaker --months 2
```

### 2. Live Demo Pipeline Stages

Executing `scripts/demo_live.py` runs the complete 4-tier pipeline against live GitHub GraphQL endpoints:

1. **Live GraphQL Ingestion**: Queries GitHub's `repository.pullRequests` connection with cursor-based pagination and archives raw JSONL payloads with ingestion metadata into `data/raw/live-spinnaker-<timestamp>/`.
2. **Canonical Normalization & Quality Checks**: Maps raw records to typed `gain.model.pr.PullRequest` models, ensuring UTC normalization, and verifies invariants (`merged_at >= created_at`, valid state `OPEN`/`CLOSED`/`MERGED`).
3. **GAIN-PR-001 Cycle Time Computation**: Evaluates observable PR duration from `created_at` to `merged_at` across percentiles (`p50`, `p75`, `p90`, `p95`).
4. **GAIN-PR-010 Monthly Flow Statistics**: Generates tabular balance sheets across trailing months:

```text
Month   | Created |  Merged |  Closed | Unmerged | Merge Rate
--------+---------+---------+---------+----------+-----------
2026-08 |       0 |       0 |       0 |        0 |        N/A
2026-09 |       2 |       1 |       1 |        0 |     100.0%
--------+---------+---------+---------+----------+-----------
TOTAL   |       2 |       1 |       1 |        0 |     100.0%
```

### 3. Alternative: Running via the GAIN CLI

You can also run the individual pipeline commands manually:

```bash
# Configure repository and date window
export GITHUB_TOKEN=$(gh auth token)
export GAIN_GITHUB_REPOS="firmsoil/spinnaker"
export GAIN_START_AT="2026-07-01T00:00:00Z"
export GAIN_END_AT="2026-09-15T00:00:00Z"

# 1. Backfill live pull requests from GitHub GraphQL
gain backfill

# 2. Normalize raw ingestion into canonical Parquet
gain normalize --run-id <run_id>

# 3. Compute cycle time metrics
gain compute --canonical-path data/canonical/pull_requests__<run_id>.parquet

# 4. Generate monthly created, merged, and closed flow statistics
gain monthly-stats --canonical-path data/canonical/pull_requests__<run_id>.parquet
```

> **Offline Demo**: For offline or CI environments without a live GitHub token or network connection, run `python scripts/demo_offline.py` to execute against synthetic pre-recorded fixtures.

## Tests

```bash
pytest
ruff check src tests
mypy src tests
```

## GAIN Model Context Protocol (MCP) Server

Phase 6 introduces the production-quality **GAIN MCP Server** (`src/gain/mcp`), exposing GAIN's trusted analytical capabilities to external AI agents and orchestrators through the official Model Context Protocol (SDK v2, protocol `2026-07-28`).

### Core Architectural Principle

GAIN MCP is strictly an **interface/access layer** over GAIN domain services. It is **NOT** a data plane, ingestion pipeline, generic SQL executor, GitHub API proxy, or LLM reasoning engine.

```text
            External AI Agents
                   │
                   ▼
             GAIN MCP Server (Interface Boundary)
                   │
                   ▼
          GAIN Domain Services
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
 Metrics        Evidence       Lineage
    │              │              │
    └──────────────┼──────────────┘
                   │
                   ▼
            GAIN Data Product
```

### Supported Transports

1. **Local CLI / Development (`stdio`)**:
   ```bash
   gain mcp --transport stdio
   ```
2. **Production Service (`Streamable HTTP`)**:
   ```bash
   gain mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
   ```
3. **MCP Inspector Interactive Validation**:
   ```bash
   .venv/bin/mcp dev src/gain/mcp/server/app.py:server
   ```

### Domain Tool Catalog (12 Tools)

| Tool Name | Scope Required | Description |
| :--- | :--- | :--- |
| `get_dora_metrics` | `gain:metrics:read` | Evaluates DORA metrics; returns explicit data gap requirements for missing deployment telemetry. |
| `query_engineering_metrics` | `gain:metrics:read` | Deterministically executes approved metrics (`pr_cycle_time`, `monthly_pr_flow_summary`). |
| `compare_cohorts` | `gain:metrics:read` | Computes statistical deltas across repository or team cohorts. |
| `analyze_ai_impact` | `gain:metrics:read` | Governed AI impact taxonomy (Observed vs Derived vs Modeled); reports insufficient data safely. |
| `calculate_ai_roi` | `gain:metrics:read` | Modeled economic scenario analysis with explicit cost and sensitivity assumptions. |
| `explain_metric` | `gain:metrics:read` | Retrieves authoritative metric definition and formula from Metric Catalog. |
| `get_metric_lineage` | `gain:metrics:read` | Traverses end-to-end lineage from observation to canonical PR and raw JSONL payload. |
| `get_evidence` | `gain:evidence:read` | Retrieves structured, auditable evidence packages by ID. |
| `start_investigation` | `gain:investigation:write` | Creates durable, application-owned investigation records independent of MCP session state. |
| `get_investigation` | `gain:investigation:read` | Retrieves investigation status with strict tenant isolation. |
| `get_data_quality` | `gain:quality:read` | Reports freshness, completeness, validity scores, and data quality flags. |
| `get_canonical_entity` | `gain:entity:read` | Retrieves canonical `PullRequest` representation by authorized identifier. |

### Addressable MCP Resources

- `gain://metric-definitions/{metric_id}/{version}` — Metric definition from catalog.
- `gain://metrics/{metric_id}` — Current summary distribution for a metric.
- `gain://cohorts/{cohort_id}` — Cohort summary.
- `gain://evidence/{evidence_id}` — Structured evidence package.
- `gain://investigations/{investigation_id}` — Durable investigation state.
- `gain://lineage/{target_id}` — Provenance and data pipeline trace.
- `gain://data-quality/{dataset_id}` — Dataset health, freshness, and validity.
- `gain://contracts/{contract_id}` — Public metric and interface contracts.

### Methodological MCP Prompts

- `dora-executive-brief` — Executive briefing on DORA engineering metrics and delivery flow.
- `dora-investigation` — Investigation into delivery lead time and deployment anomalies.
- `ai-impact-investigation` — Framework for evaluating engineering differences across cohorts.
- `ai-roi-analysis` — Economic ROI scenario analysis with explicit assumptions.
- `metric-change-investigation` — Root-cause inquiry into sudden metric shifts.
- `repository-engineering-investigation` — Holistic repository engineering flow analysis.
- `evidence-review` — Claim integrity review and evidence package audit.
- `engineering-health-briefing` — Cross-repository flow and health synthesis.

### Python Client Integration Example (MCP SDK v2)

```python
import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def query_gain_mcp() -> None:
    async with streamable_http_client("http://127.0.0.1:8000/mcp") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # 1. Discover tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")
            
            # 2. Query PR cycle time
            result = await session.call_tool(
                "query_engineering_metrics",
                {"metric_name": "pr_cycle_time", "repository": "firmsoil/gain"}
            )
            print("Cycle Time Result:", result.structured_content)

anyio.run(query_gain_mcp)
```

## Security

Do not place GitHub tokens in source code or command-line history. The CLI reads `GITHUB_TOKEN` from the environment. Tokens and secrets are redacted from logs automatically via `gain.logging.mask_secrets`. MCP requests enforce fine-grained policy authorization and tenant isolation before data access.

