# ADR 0015: GAIN MCP Authorization Boundary

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Security Engineer, GAIN Architect  

---

## 1. Context

AI agents operating over MCP may possess varying levels of clearance, represent different tenant organizations, or request sensitive developer-level engineering data. Authenticating a caller does not imply universal data access. We must establish a strict authorization boundary within the MCP server.

---

## 2. Decision

We establish a first-class **Policy-Based Authorization Boundary** within `gain.mcp.auth`:

1. **Pre-Invocation Authorization**: Authorization checks occur *before* accessing protected GAIN analytical services or storage.
2. **Context Attributes**: Every MCP request is evaluated against:
   - `principal_id` (caller identity)
   - `tenant_id` (caller organization)
   - `scopes` (e.g. `gain:metrics:read`, `gain:evidence:read`, `gain:quality:read`, `gain:entity:read`, `gain:investigation:read`, `gain:investigation:write`)
   - `target_domain` (repository or data product scope)
   - `operation` (tool, resource, or prompt invoked)
3. **Tenant Isolation**: Multi-tenant isolation is strictly enforced. Cross-tenant access, investigation listing across tenants, or querying repositories outside a caller's tenant boundary is immediately rejected with `403 Forbidden` (`AuthorizationError`).
4. **No LLM Decision Making**: Authorization decisions are pure Python policy evaluations based on cryptographic or explicit context tokens, never based on model self-attestation or natural language requests.
5. **No Mutation Capabilities**: The initial MCP catalog contains exclusively read-oriented tools and application-managed investigation creation. No repository mutation, pull request merge, or external code modifications are exposed.

---

## 3. Consequences

- **Positive**: Prevents data leakage between organizations and unauthorized developer tracking.
- **Positive**: Provides clear audit trails for all MCP interactions.
- **Negative**: Callers must supply valid authentication context (or utilize the explicit local development mode).
