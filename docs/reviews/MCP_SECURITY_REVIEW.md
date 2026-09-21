# GAIN MCP Security Review & Safety Audit
**Date:** 2026-09-20
**Auditor:** GAIN Security & Safety Specialist
**Status:** **PASS**

## Overview
This security review evaluates the implementation of the GAIN Model Context Protocol (MCP) server against the directives established in `ADR 0015` and the `REFERENCE_ARCHITECTURE.md`. The primary goal is to ensure robust authorization boundaries, strict tenant isolation, information leakage prevention, prompt injection mitigation, and write-plane isolation.

---

## 1. Authorization Boundary
- **Pre-invocation Checks:** Every MCP tool and resource operation begins with an explicit policy enforcement call (`AuthorizationPolicy.authorize(...)`). Pre-invocation checks are correctly positioned ahead of all data access operations.
- **Role-Based Scope Enforcement:** Scopes like `gain:metrics:read`, `gain:evidence:read`, `gain:quality:read`, and `gain:investigation:write` are strictly evaluated. Unscoped principal requests result in an immediate `403 AuthorizationError`.
- **Repository Domain Scoping:** The `AuthorizationPolicy.authorize` method successfully checks `principal.is_repository_allowed(repository)` when repository context is requested, preventing broad repository crawling.

## 2. Tenant Isolation
- **Tenant Context Verification:** The `AuthorizationPolicy` explicitly enforces that the requested operation aligns with the caller's assigned `tenant_id`. Cross-tenant operations are rejected.
- **No Tenant Enumeration:** Functions handling potentially multi-tenant identifiers (e.g., `get_investigation`) query records scoped solely to the authorized `tenant_id`. When a record belonging to another tenant is requested, the system safely throws a `NotFoundError` (404) rather than an `AuthorizationError` (403), effectively mitigating cross-tenant enumeration.

## 3. Information Leakage & Secret Protection
- **Masking Controls:** `src/gain/logging.py` implements a robust `mask_secrets` structlog processor that correctly redacts values associated with sensitive keys (`token`, `secret`, `authorization`, `password`, `api_key`, `access_token`).
- **Telemetry Boundaries:** `trace_mcp_request` correctly logs operational attributes (e.g., `request_id`, `operation_type`, `principal`, `tenant`) without serializing entire payload bodies or exceptions into raw logs.
- **Error Payloads:** The `MCPError` hierarchy (`src/gain/mcp/errors.py`) is structured to return predictable, safe error codes (e.g., `AUTHORIZATION_FAILURE`, `INSUFFICIENT_DATA`) rather than unchecked Python stack traces.

## 4. Prompt Injection & Untrusted Content Handling
- **Untrusted Content Mitigation:** The current architectural slice exclusively handles structured metrics, metadata (e.g., cycle times, additions/deletions), and node IDs. Vulnerable fields prone to adversarial prompt injection—such as Pull Request titles, bodies, and issue comments—are intentionally absent from the returned domain objects (e.g., `CanonicalEntityResult`).
- **Safety Affirmation:** Because no raw text content from the repository is returned or executed, agents interacting with GAIN MCP tools are fundamentally protected against repo-originated prompt injection attacks in this release.

## 5. Future Write-Plane Isolation
- **Read-Only Posture:** 11 of the 12 tools exposed in the MCP server strictly evaluate to read operations (e.g., querying statistics, lineage, and definitions).
- **Controlled State Mutation:** The solitary write operation (`start_investigation`) requires explicit `Scope.INVESTIGATION_WRITE` permission. Its mutations are completely limited to application-controlled, durable investigation planning state (creating an investigation record).
- **No External Mutation Paths:** There are precisely zero endpoints or tools wired to mutate GitHub repositories, commit code, or manipulate PR states. 

---

## Verdict
The GAIN MCP implementation adheres strictly to the non-negotiable security requirements outlined in ADR 0015. Policy enforcement is correctly decoupled from AI decision-making, strict multi-tenant isolation is present, and secrets are actively redacted from telemetry outputs. 

**Result: PASS**
