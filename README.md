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
