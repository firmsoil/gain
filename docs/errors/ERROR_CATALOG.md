# GAIN Error Catalog & Operational Runbook

This document defines the error code taxonomy, team ownership, retry policy, and operational troubleshooting runbooks for the GAIN platform.

## Error Taxonomy Matrix

| Error Code | Class Name | Team | Severity | Retryable? | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`GAIN-0000`** | `GainError` | `platform` | `ERROR` | No | Base exception for all GAIN system failures. |
| **`GAIN-1001`** | `ConfigurationError` | `platform` | `ERROR` | No | Invalid or missing settings, tokens, filesystem permissions, or environment configuration. |
| **`GAIN-2001`** | `GitHubApiError` | `platform` | `ERROR` | No | Unhandled GitHub GraphQL API response errors, malformed payloads, or network dropouts. |
| **`GAIN-2002`** | `IncompletePaginationError` | `platform` | `ERROR` | No | Cursor desynchronization, unchanged cursors, or premature pagination termination. |
| **`GAIN-2029`** | `RateLimitError` | `platform` | `WARN` | **Yes** | GitHub GraphQL API point quota exhaustion or HTTP 403/429 rate limiting. |
| **`GAIN-3001`** | `DataQualityError` | `data` | `ERROR` | No | Schema mismatch, timestamp corruption, or unparseable raw payloads during normalization. |
| **`GAIN-4001`** | `RequirementsError` | `data` | `ERROR` | No | Base error for human-governed requirements and SDD generation operations. |
| **`GAIN-4002`** | `RequirementValidationError` | `data` | `ERROR` | No | Failed schema validation on user stories, business contexts, or acceptance criteria. |
| **`GAIN-4003`** | `InvalidLifecycleTransitionError` | `data` | `ERROR` | No | Illegal state transition in requirements lifecycle (e.g. Approved -> Draft). |
| **`GAIN-5001`** | `JiraIntegrationError` | `platform` | `ERROR` | No | Upstream Jira REST API communication or payload serialization failure. |
| **`GAIN-5002`** | `JiraAuthenticationError` | `platform` | `ERROR` | No | Invalid or expired Jira bearer token or basic authentication credentials. |

---

## Operational Troubleshooting Runbooks

### `GAIN-1001`: ConfigurationError
- **Symptom**: CLI commands or daemon fails at startup with missing required environment variables.
- **Remediation**:
  1. Check `gain config-check` output.
  2. In production (`GAIN_ENVIRONMENT=production`), verify that `GAIN_GITHUB_TOKEN` or `GAIN_GITHUB_APP_ID`, `GAIN_GITHUB_APP_PRIVATE_KEY_PATH`, and `GAIN_GITHUB_INSTALLATION_IDS` are populated.
  3. Ensure `GAIN_PII_HMAC_SALT` has at least 16 characters if `GAIN_PII_MASK_AUTHORS=true`.
  4. Ensure private key file exists and has permissions `0600`.

### `GAIN-2029`: RateLimitError
- **Symptom**: Ingestion worker logs `worker_rate_limited` or coordinator reports `RateLimitError`.
- **Remediation**:
  1. If using GitHub App authentication, verify token pool has configured multiple installation IDs or tokens.
  2. Inspect `/readyz` probe endpoint: verify if all tokens or a fraction are currently rate-limited.
  3. The worker automatically rotates to an unexhausted token in the pool when available.
  4. If all tokens are exhausted, the worker backs off until the earliest reset epoch indicated by `x-ratelimit-reset`.

### `GAIN-2002`: IncompletePaginationError
- **Symptom**: Worker halts on repository with unchanged cursor error.
- **Remediation**:
  1. Check sharded checkpoint in `data/raw/checkpoints/<run_id>/<owner>__<name>.json`.
  2. Inspect the latest page logged in raw storage for anomalies or repository rename/deletion.
  3. Purge or reset the checkpoint to resume ingestion from the last stable cursor.

### `GAIN-3001`: DataQualityError
- **Symptom**: Normalization pipeline raises error during Parquet conversion.
- **Remediation**:
  1. Inspect the source JSONL payload in `data/raw/<year>/<month>/`.
  2. Verify if unexpected author types or null timestamps bypassed ingestion validation.
  3. Run `gain normalize` with debug logging to isolate the specific line number.
