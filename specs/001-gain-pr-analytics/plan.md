# GAIN Implementation Plan

## Architecture
1. `gain.cli` — user interface
2. `gain.config` — typed configuration
3. `gain.github.auth` — credential/token acquisition
4. `gain.github.graphql` — query definitions and client
5. `gain.github.rest` — justified REST adapters
6. `gain.sync` — backfill/incremental orchestration and checkpoints
7. `gain.raw` — raw payload/provenance persistence
8. `gain.schema` — validation and normalization
9. `gain.model` — canonical entities
10. `gain.quality` — data-quality rules
11. `gain.metrics` — metric registry and calculations
12. `gain.analytics` — distributions/trends
13. `gain.outputs` — Parquet/JSON/CSV/report exports
14. `gain.observability` — structured logging/run telemetry

## Storage
MVP recommendation: raw JSONL/object-style payloads + canonical Parquet + DuckDB views/querying. Revisit relational storage if concurrent multi-user serving becomes a requirement.

## Synchronization
Backfill is date-bounded and checkpointed. Incremental sync uses a configurable recent lookback window to capture late PR changes, plus deterministic upsert semantics keyed by repository + PR number / node ID.

## API query strategy
Use separate queries for PR list/basic attributes and optional detail collections when query size/complexity becomes significant. Keep GraphQL queries under version control. Query response fixtures are used in tests.

## Error strategy
- retry transient failures with bounded exponential backoff
- honor `retry-after` when present
- stop when primary rate limit is exhausted rather than hammering the API
- record partial GraphQL errors
- resume from checkpoint after terminal failure

## Metric strategy
A metric registry loads the versioned YAML catalog. Calculation functions implement metric semantics against canonical data. A validation layer ensures required fields exist before execution.

## Reporting
Executive outputs are aggregate-only by default. Diagnostic outputs support repository/team grains when mappings are available.
