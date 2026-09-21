# ADR 0011: MCP Does Not Become the GAIN Data Plane

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Data Engineer, GAIN Platform Engineer  

---

## 1. Context

In distributed intelligence architectures, there is a temptation to route telemetry ingestion, event streaming, data transformations, or persistent dataset storage through the MCP protocol interface. We must determine the explicit boundaries between GAIN's core data plane and the MCP protocol layer.

---

## 2. Decision

We mandate that **MCP must NOT become the GAIN data plane**:

1. **No Data Ingestion**: GAIN MCP shall not ingest telemetry from GitHub, Jira, CI systems, or external providers. Ingestion belongs exclusively to the GAIN acquisition pipeline (`gain.sync`, `gain.github`).
2. **No Canonical Data Store**: GAIN MCP does not maintain its own persistence format for canonical entities. It reads from the GAIN analytical store (`gain.storage.analytics`, Parquet/JSONL) via domain services.
3. **No Heavy Payloads**: MCP responses must favor structured metadata, summary statistics, and URI references over transferring multi-megabyte raw event streams.
4. **Data Plane Independence**: If the MCP server is restarted, scaled, or taken offline, GAIN ingestion pipelines, normalization jobs, and scheduled analytics computations continue unimpeded.

---

## 3. Consequences

- **Positive**: Preserves data plane scalability, performance, and replayability guarantees.
- **Positive**: Prevents coupling protocol session mechanics with big-data Parquet storage.
- **Negative**: Client hosts needing bulk raw data must use dedicated batch export mechanisms rather than streaming raw rows over MCP tool calls.
