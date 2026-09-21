# GAIN Development Guidelines & Core Directives

## Authoritative Reference Architecture
The authoritative reference architecture for this codebase is [`docs/REFERENCE_ARCHITECTURE.md`](docs/REFERENCE_ARCHITECTURE.md).
All agents and contributors must strictly adhere to the boundaries, interfaces, and constraints defined therein.

## Core Non-Negotiable Directives
1. **GitHub Remains Source of Truth**: All metrics and downstream models derive from observable GitHub telemetry. Raw API responses must be captured losslessly and preserved for provenance and replayability.
2. **Deterministic, Zero-LLM Metrics**: Metric calculations (including PR cycle time `GAIN-PR-001`) must be pure Python deterministic computations with explicit versions. No LLM reasoning or heuristic inference is permitted in metric execution.
3. **Transport Independence**: Canonical domain models (`gain.model.*`) must never expose GraphQL-specific artifacts (cursors, pageInfo, edges, connection wrappers).
4. **Preserve Validated Vertical Slice**: Under no circumstance may the existing validated vertical slice (GraphQL -> Raw JSONL -> Canonical PullRequest -> Cycle Time -> Automated Tests) be rewritten, regressed, or broken.
5. **Strict Negative Scope**: Do not implement:
   - LLM agents or autonomous production engines
   - GitHub MCP or GAIN MCP servers
   - AI attribution or AI ROI modeling
   - UI or dashboards
6. **Code Quality Standards**:
   - Production Python >=3.12
   - Strict typing with `mypy` (`strict = true`)
   - Strict linting with `ruff`
   - Structured logging via `structlog`
   - Zero hardcoded credentials or logged secrets
