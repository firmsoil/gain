# GAIN Security and Agent Safety Audit Report

**Date:** 2026-09-20  
**Auditor:** GAIN Security & Safety Specialist (`gain-security-engineer`)  
**Status:** COMPLETE  

## 1. Executive Summary

An independent security and agent-safety audit was conducted on the GAIN (GitHub AI Intelligence Network) codebase. The audit focused on credential handling, authorization boundaries, untrusted content processing, and future readiness for MCP/Agent integrations. 

Overall, the architectural design establishes a strong baseline for security, particularly through **strict data minimization** (excluding PR titles and bodies from domain models, completely preventing prompt injection). However, a significant gap exists in the logging pipeline, which lacks secret redaction and poses a risk of credential leakage.

## 2. Audit Findings

### 2.1 Credential Handling and Token Isolation
**Finding:** Missing Secret Redaction in Logging Pipeline  
**Severity:** **HIGH**  
**Description:** `src/gain/logging.py` configures `structlog` with `JSONRenderer` but lacks a custom processor to redact sensitive credentials. The tokens (`GITHUB_TOKEN`, `GAIN_GITHUB_TOKEN`, `GAIN_JIRA_TOKEN`) are securely loaded via environment variables in `src/gain/config.py`, but if an exception occurs that captures local variables (such as the `Settings` object) or if `httpx` logs debug HTTP headers, the tokens will be emitted in plaintext into the application logs.  
**Recommendation:** Implement a custom `structlog` processor that intercepts the event dictionary and masks values for known sensitive keys (e.g., keys containing `token`, `secret`, `authorization`, `password`). Ensure HTTP client configurations disable raw header logging.

### 2.2 Authorization Boundaries and Least-Privilege Scopes
**Finding:** Lack of Enforcement for Read-Only Scopes  
**Severity:** **MEDIUM**  
**Description:** The application requires a GitHub token and a Jira token to operate. While GAIN's architecture only performs read operations against GitHub (via `PR_BACKFILL_QUERY`), there is no runtime validation to ensure the provided token adheres to least-privilege (read-only) principles. A token with broad write access increases the blast radius if the host environment is compromised.  
**Recommendation:** Explicitly document the exact fine-grained Personal Access Token (PAT) permissions required (e.g., `Contents: Read-only`, `Pull Requests: Read-only`). Consider adding a startup validation query that checks the `X-OAuth-Scopes` or `X-Accepted-OAuth-Scopes` headers to proactively reject overly permissive tokens.

### 2.3 Handling of Untrusted Repository Content
**Finding:** Exceptional Defense-by-Design (Implicit Sanitization)  
**Severity:** **INFORMATIONAL (Positive Finding)**  
**Description:** The `PullRequest` domain model (`src/gain/model/pr.py`) and the corresponding GraphQL query (`src/gain/github/queries.py`) successfully omit free-text fields such as `title` and `body`. This architectural choice completely neutralizes risks related to script injection, untrusted evaluation, and prompt injection for downstream systems.  
**Recommendation:** Maintain this strict constraint. If future requirements mandate fetching PR titles, comments, or bodies, they must be routed through a dedicated sanitization function before being admitted into the Pydantic model.

### 2.4 Secrets Exposure in Serialized Payloads
**Finding:** Safe Persistence of Raw and Canonical Data  
**Severity:** **LOW**  
**Description:** The data extracted via the GitHub GraphQL API is limited to entity IDs, timestamps, and metric counts. As such, the resulting JSONL and Parquet payloads inherently do not contain application secrets.  
**Recommendation:** Continue enforcing strict schema validation (`normalize_records`) to guarantee no unexpected nodes (which could theoretically contain secrets) pass into the canonical layer.

### 2.5 Security Boundaries for Future MCP Integrations
**Finding:** Agent Interface Isolation  
**Severity:** **INFORMATIONAL**  
**Description:** Autonomous LLM agents are strictly excluded from the current vertical slice. When MCP integrations are eventually introduced, they must not inherit the raw environment variables (e.g., `GITHUB_TOKEN`).  
**Recommendation:** Future MCP servers must run as constrained wrappers around specific CLI subcommands (e.g., `gain compute`). The MCP boundary must not provide agents with arbitrary execution capabilities or access to the raw ingestion commands (`gain backfill`).

### 2.6 Data Minimization and PII Indirect Exposure
**Finding:** Plaintext Storage of Author Logins  
**Severity:** **LOW**  
**Description:** The system persists `author_login` in plaintext within both the raw storage and the canonical Parquet files. While necessary for some developer-level analytics, it exposes Personally Identifiable Information (PII) if the datasets are broadly shared.  
**Recommendation:** Depending on compliance requirements (e.g., GDPR), consider implementing a one-way cryptographic hash with a deterministic salt for `author_login` during the schema normalization phase (`gain.schema`). This allows correlation (e.g., monthly stats by author) without exposing the underlying identities.

## 3. Summary of Action Items

1. **[HIGH]** Add a secret-scrubbing processor to `structlog` in `src/gain/logging.py`.
2. **[MEDIUM]** Document required fine-grained PAT scopes and enforce least-privilege token usage.
3. **[LOW]** Evaluate the necessity of plaintext `author_login` persistence and implement hashing if PII obfuscation is required.
4. **[INFORMATIONAL]** Preserve the existing zero-text-field Pydantic design to maintain immunity against prompt injection.
