# GAIN Feature Package: 001-gain-pr-analytics

This package defines the baseline feature specification for the **GAIN PR Analytics** vertical slice and core metric pipeline. It encompasses GitHub GraphQL pull request ingestion, raw payload archiving, canonical data normalization, data quality enforcement, and flow metric calculations.

For the overarching Spec-Driven Development (SDD) guide and cross-package workflows, see the parent [specs/README.md](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/README.md).

---

## Package Directory Map

```text
specs/001-gain-pr-analytics/
├── README.md                      # This package orientation guide
├── spec.md                        # Product Specification (Goals, non-goals, user stories, FRs, NFRs)
├── clarifications.md              # Architectural decisions (auth, 365d backfill, 30d lookback, bot handling)
├── plan.md                        # Technical Implementation Plan (packages, storage, retry strategies)
├── tasks.md                       # Atomic task list organized across Phases 0 through 6
├── data-model.md                  # Canonical schema, natural keys, entity relations, and invariants
├── quickstart.md                  # Local CLI quickstart commands for backfill, compute, and testing
├── research.md                    # Research notes on GraphQL vs REST, DuckDB/Parquet, and DORA
├── responsible-use.md             # Ethical guidelines, prohibited use cases, and interpretation warnings
├── spec-kit-command-sequence.md   # Exact Spec Kit slash-command order for this feature
├── implementation-prompts.md      # LLM agent prompts for each phase of Spec Kit execution
├── checklists/
│   └── requirements.md            # 12-point requirements quality gate checklist
└── contracts/
    ├── api-contracts.md           # API query versioning and provenance rules
    ├── input-api-contract.md      # GraphQL input fields, pagination limits, and error handling
    └── outputs.md                 # Schemas for canonical PRs, metric observations, and reports
```

---

## Artifact Index & Role Guide

| Document | Primary Audience | Key Contents & Practical Usage |
|---|---|---|
| [`spec.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/spec.md) | PM & Lead Eng | Defines user personas (CTO to Platform Engineer), functional requirements (FR-001 through FR-010), and strict non-goals (no individual productivity scoring). |
| [`clarifications.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/clarifications.md) | PM & Developer | Documents standard defaults: GitHub App for orgs / PAT for dev, 365-day backfill, 30-day incremental re-scan, bot classification (`HUMAN`/`BOT`), Parquet + DuckDB storage. |
| [`plan.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/plan.md) | Developer | Architectural blueprint mapping the 14 functional layers (from `gain.cli` to `gain.observability`), DuckDB/Parquet storage recommendations, and API error budget handling. |
| [`tasks.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/tasks.md) | Developer & PM | Phase-by-phase implementation checklist (Phase 0 Foundation, Phase 1 Vertical Slice, Phase 2 Reliability, Phase 3 Core Metrics, Phase 4 Reporting, Phase 5 Review, Phase 6 Integrations). |
| [`data-model.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/data-model.md) | Data Eng & Dev | Defines canonical entities: `Organization`, `Repository`, `Actor`, `PullRequest`, `Review`, `IngestionRun`, and `MetricObservation`. Lists semantic invariants and natural keys. |
| [`contracts/input-api-contract.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/contracts/input-api-contract.md) | Developer | Specifies required GraphQL PR fields (`id`, `number`, `createdAt`, `closedAt`, `mergedAt`, `state`, `isDraft`), pagination requirements (max 100 per page), and rate-limit controls. |
| [`contracts/outputs.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/contracts/outputs.md) | Data Eng & Analyst | Output schemas for `canonical_pull_requests`, `metric_observations`, `synchronization_report`, `data_quality_report`, and `executive_kpis`. |
| [`contracts/api-contracts.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/contracts/api-contracts.md) | Developer | Links to [`docs/github-api/api-field-catalog.yaml`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/docs/github-api/api-field-catalog.yaml) and defines query version-control rules. |
| [`checklists/requirements.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/checklists/requirements.md) | PM | 12-point gate checking observability, pagination, bot handling, metric IDs, and testability before implementation begins. |
| [`responsible-use.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/responsible-use.md) | PM & Leadership | Explicit boundaries: metrics are signals, not verdicts. Forbids developer stack-ranking, lines-of-code evaluations, or treating cycle time as developer effort. |
| [`research.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/research.md) | Developer & PM | Technology evaluation: GraphQL vs REST tradeoffs, rate-limit reset handling, Polars/DuckDB rationale, and clarification on why PR lifecycle is adjacent to, but distinct from, DORA metrics. |
| [`quickstart.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/quickstart.md) | Developer | Quick setup commands: environment setup, backfilling, running validations, computing metrics, and executing tests. |
| [`spec-kit-command-sequence.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/spec-kit-command-sequence.md) | PM & Developer | The canonical 9-step execution sequence: `constitution` → `specify` → `clarify` → `plan` → `checklist` → `tasks` → `analyze` → `implement` → `converge`. |
| [`implementation-prompts.md`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/specs/001-gain-pr-analytics/implementation-prompts.md) | AI Agent / Dev | Exact prompts used by LLM agents when regenerating or verifying each Spec Kit stage. |

---

## Core Invariants & Rules

1. **Natural Key**: A Pull Request is uniquely identified across time by `repository_id + number`.
2. **Timestamps**: All timestamps must be converted to UTC ISO-8601 strings or UTC datetime objects. Negative durations (`merged_at < created_at`) are invalid and must be flagged by [`gain.quality`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/src/gain/quality.py).
3. **Replayability**: Raw responses must be stored in `data/raw/<run_id>/` as JSONL before canonical normalization so that metrics can be recomputed without incurring API costs.
4. **Metrics Authority**: Metric calculations must implement formulas and filters strictly as documented in [`docs/metrics/metric-catalog.yaml`](file:///Users/mp/Downloads/GAIN-Production-Codebase-v0.1.0/docs/metrics/metric-catalog.yaml).
5. **Responsible Aggregation**: Metric outputs default to repository- and team-level distributions. Individual developer leaderboards are explicitly barred.

---

## How to Run & Verify

To test the current implementation against this specification package:

```bash
# Activate virtual environment
source .venv/bin/activate

# Execute the offline vertical slice demo
python scripts/demo_offline.py

# Run unit and integration tests
pytest

# Validate linting and typing
ruff check .
mypy src
```
