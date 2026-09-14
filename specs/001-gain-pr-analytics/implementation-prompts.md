# Spec Kit Execution Prompts

## /speckit.constitution
Create the GAIN constitution from the supplied constitution draft. Preserve the principles of analytical integrity, GitHub semantic correctness, API-first replayable ingestion, deterministic computation, Metric Catalog authority, responsible use, least privilege, pre-code quality gates, testable mathematics, thin vertical slices, extensibility without premature complexity, and observable operations.

## /speckit.specify
Create/update the GAIN PR analytics feature specification from `spec.md`. Focus on what and why. Require GitHub GraphQL-first acquisition, resilient synchronization, raw provenance, canonical normalization, versioned metrics, data-quality reporting, and responsible-use boundaries. Do not add implementation technologies during this step.

## /speckit.clarify
Inspect the GAIN specification for ambiguity. Focus on API scope, authentication, historical lookback, incremental lookback, bot handling, team mapping, raw retention, metric cohort semantics, and privacy. Record recommended defaults rather than blocking implementation.

## /speckit.plan
Create the implementation plan using the GAIN API Field Catalog, Metric Catalog, data model, and research. Use a GraphQL-first acquisition layer, REST adapters only where justified, raw payload retention, canonical Parquet/DuckDB analytics, typed metric registry, resilient checkpoints, and fixture-driven tests.

## /speckit.checklist
Create a requirements-quality checklist focused on: metric definitional completeness, field lineage, GitHub semantic correctness, API pagination, retries/rate limits, synchronization idempotency, data quality, responsible use, and testability.

## /speckit.tasks
Generate atomic implementation tasks from the plan. Start with the thin vertical slice: authenticated GraphQL request → paginated PR retrieval → raw persistence → canonical normalization → GAIN-PR-001 → output → tests. Do not implement broad features before validating this path.

## /speckit.analyze
Perform read-only cross-artifact consistency analysis. Check spec.md, plan.md, tasks.md, constitution, API Field Catalog, Metric Catalog, data model, and contracts. Flag unsupported metrics, missing API fields, contradictory assumptions, orphaned tasks, and untested formulas.

## /speckit.implement
Implement tasks in dependency order. Execute the thin vertical slice first, run tests, then continue by phase. Do not silently reinterpret metric definitions or API semantics; surface any conflict with the artifacts.

## /speckit.converge
Assess implementation against spec.md, plan.md, tasks.md, Metric Catalog, API Field Catalog, contracts, and constitution. Append concrete remediation tasks for any gaps. Repeat implementation and convergence until no material requirements or quality gaps remain.
