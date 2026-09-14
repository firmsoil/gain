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

## Architecture

- `gain.github.client` — GraphQL transport, retries, rate-limit handling, pagination.
- `gain.github.queries` — version-controlled GraphQL query definitions.
- `gain.sync` — backfill orchestration and checkpoints.
- `gain.storage.raw` — replayable raw payloads and provenance.
- `gain.model` — canonical domain models.
- `gain.metrics` — versioned metric registry/calculations.
- `gain.storage.analytics` — Parquet outputs.
- `gain.quality` — canonical data-quality validation.
- `gain.cli` — operator interface.
- `gain.requirements` — human-governed business context, AI story drafts, Jira mapping, and SDD seeds.

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
ruff check .
mypy src
```

## Spec-driven source of truth

The SDD artifacts from the implementation package are retained under `specs/` and `docs/`. The implementation should be evaluated against those artifacts using the current Spec Kit workflow: constitution -> specify -> clarify -> plan -> checklist -> tasks -> analyze -> implement -> converge. GitHub documents cursor-based pagination and connection page sizes of up to 100 items, which the collector handles explicitly. See the GitHub GraphQL pagination documentation.

## Security

Do not place GitHub tokens in source code or command-line history. The CLI reads `GITHUB_TOKEN` from the environment. Tokens are never logged.
