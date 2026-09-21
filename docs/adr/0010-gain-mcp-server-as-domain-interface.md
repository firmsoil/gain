# ADR 0010: GAIN MCP Server as Domain Interface

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Architect, GAIN Platform Engineer, GAIN Security Engineer  

---

## 1. Context

As external AI coding assistants, orchestrators, and developer tools interact with engineering intelligence platforms, they require structured access to metrics, evidence, and data quality. The Model Context Protocol (MCP) provides an open protocol for exposing tools, resources, and prompts to client hosts.

A critical design choice is whether the GAIN MCP Server acts as a generic backend proxy (forwarding requests directly to GitHub or arbitrary databases) or as a domain-oriented interface over GAIN's analytical platform.

---

## 2. Decision

We establish that the GAIN MCP Server functions strictly as a **domain-oriented Model Context Protocol interface** over existing GAIN analytical capabilities:

```
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

1. **Access Layer Only**: GAIN MCP is strictly an access/interface layer over GAIN's trusted analytical capabilities.
2. **Prohibited Topology**: Under no circumstances shall GAIN MCP serve as a GitHub API proxy, query GitHub on behalf of external agents, or trigger recalculation of analytics from upstream GitHub in response to an MCP tool call.
3. **Domain Semantics**: Tools, resources, and prompts expose domain entities (DORA metrics, PR cycle time, cohort comparisons, evidence packages, data quality, canonical PRs) rather than raw SQL or filesystem primitives.

---

## 3. Consequences

- **Positive**: Strict decoupling protects the platform against unvalidated external queries and preserves GAIN as the authoritative source of engineering intelligence.
- **Positive**: External agents receive validated, structured domain models rather than unstructured text or raw GraphQL JSON.
- **Negative**: Capabilities not yet backed by deterministic domain services cannot be queried through MCP and must return explicit insufficient-data responses.
