# ADR 0021: Dual MCP Tool Routing and Failure Modes

## Status
Accepted

## Context
Investigating software delivery questions often requires both historical analytical metrics (e.g. 90th percentile cycle time over 6 months) and live qualitative repository context (e.g. commit messages, pull request review comments).

We must define the routing boundary between GAIN MCP and GitHub MCP and specify failure handling behaviors when either system is unavailable.

## Decision
1. We establish an explicit **Tool Router** with two target interfaces:
   - **GAIN MCP**: Authoritative for analytical intelligence (metrics, distributions, cohort deltas, metric catalog, data quality, data lineage).
   - **GitHub MCP**: Authoritative for live operational context (specific PR review comments, commit details, live status).
2. **Failure Isolation Principles**:
   - **GitHub MCP Unavailable**: The Agent operates in degraded analytical mode, answering questions based on GAIN metrics while explicitly noting that live qualitative context could not be verified. Under no circumstances will live context be fabricated or simulated.
   - **GAIN MCP Unavailable**: The Agent halts execution and reports analytical service unavailability. Under no circumstances will the Agent attempt to query GitHub APIs directly and compute metrics ad-hoc within the agent layer.
   - **Incomplete / Insufficient Data**: If telemetry is missing (e.g., DORA deployments, Copilot logs), the Agent surfaces an explicit `insufficient_data` finding and states the prerequisites.

## Consequences
- **Positive**: Strict prevention of unauthorized analytical recalculation; clear transparency when upstream systems are offline; zero synthetic operational context.
- **Negative**: The Agent cannot answer questions requiring live qualitative context if GitHub MCP is unconfigured or unreachable.
