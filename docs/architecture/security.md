# GAIN Enterprise Security Architecture & Posture Specification

---

## 1. Executive Summary & Security Philosophy

The **GAIN (GitHub AI Intelligence Network) Platform** is designed under a **Zero-Trust, Least-Privilege, Defense-in-Depth** security philosophy. Because GAIN ingests, stores, and evaluates engineering telemetry across 40,000+ repositories in Fortune 100 enterprise environments, the security perimeter must strictly guarantee:
1. **Zero Secret Exposure**: Credentials, private keys, and tokens are never logged, persisted in raw caches, or leaked via exceptions or error stacks.
2. **Cryptographic PII Protection**: Developer identities and sensitive identifiers are de-identified via salted cryptographic hashing with zero static or shared salt fallbacks.
3. **Fail-Closed Production Validation**: The platform will not start in production mode if security invariants (key permissions, salt entropy, transport encryption) are violated.
4. **Governed Interface Boundaries**: MCP and Agent interfaces enforce strict RBAC, tenant isolation, step budgeting, and prompt injection defense.

---

## 2. PII Privacy & Salt Lifecycle Management

GAIN enforces deterministic anonymization of developer identities (e.g. `author_login`, committer emails) across canonical storage and downstream analytical exports.

### 2.1 Cryptographic Salt Generation
- **Static Salt Eradication**: The legacy static fallback salt (`gain_default_salt`) has been entirely removed from the codebase.
- **Ephemeral Non-Production Salt**: In local development, testing, and CI environments, `gain.privacy._get_ephemeral_salt()` dynamically generates a 256-bit cryptographically secure random salt using `secrets.token_bytes(32)`. The salt is scoped strictly to the process memory lifetime, preventing cross-session correlation in test environments.
- **Production Salt Enforcement**: In production environments (`GAIN_ENVIRONMENT=production` or `prod`), `gain.config.Settings.validate_production_readiness()` verifies that:
  * `GAIN_PII_SALT` is explicitly configured.
  * The salt string is at least 16 characters in length.
  * The salt possesses sufficient entropy (rejecting trivial repetitions or common weak strings).

```python
# src/gain/privacy.py
def _get_ephemeral_salt() -> bytes:
    global _EPHEMERAL_SALT
    if _EPHEMERAL_SALT is None:
        _EPHEMERAL_SALT = secrets.token_bytes(32)
    return _EPHEMERAL_SALT
```

---

## 3. Credential & Secret Management

GAIN supports multiple authentication modes for GitHub telemetry extraction:
- **Personal Access Tokens (PAT)**
- **GitHub App Private Keys** (Recommended for enterprise deployments)
- **Multi-Token Pools** for distributed quota rotation

### 3.1 Private Key File Permissions
When configured with `GAIN_GITHUB_APP_PRIVATE_KEY_PATH`, GAIN loads the PEM private key from the local filesystem. To prevent privilege escalation on multi-tenant worker nodes:
- `gain.github.auth._load_private_key()` inspects POSIX file permissions.
- In non-Windows environments, the key file must not have group or world read permissions (enforcing `0600` or `0400` semantics).
- If permissions are overly permissive (e.g. `0644` or `0777`), initialization fails immediately with an `AuthenticationError`.

```python
# src/gain/github/auth.py
mode = key_path.stat().st_mode
if mode & (stat.S_IRWXG | stat.S_IRWXO):
    raise AuthenticationError(
        f"Private key file {key_path} has insecure permissions. "
        "File must only be readable by owner (e.g., chmod 0600)."
    )
```

### 3.2 PAT Masking & Display Redaction
- In all string representations, auth logs, and status displays, tokens are masked.
- Standard GitHub tokens (`ghp_...`, `github_pat_...`) display only their prefix and trailing four characters.
- Short tokens (<8 characters) are safely masked as `pat-***` without exposing characters.

### 3.3 Thread-Safe Token Rotation
In high-throughput distributed ingestion pipelines, `GitHubTokenPool` synchronizes token checkout and rate-limit tracking across asynchronous tasks using `threading.Lock`, preventing race conditions, double-checkout, or quota exhaustion.

---

## 4. Telemetry Sanitization & Log Redaction

All logging in GAIN is structured JSON via `structlog` and routed through an automated redactor pipeline before output.

### 4.1 Keyword-Based Scrubbing
The structured logger inspects dictionary keys and redacts known sensitive parameter names (`SENSITIVE_KEYS`), including:
- `token`, `secret`, `password`, `api_key`, `authorization`
- `access_token`, `client_secret`, `private_key`, `key_pem`, `certificate`

### 4.2 Regex-Based Pattern Scrubbing
The `TOKEN_PATTERN` regex processor scans all log values and messages for recognizable credential prefixes:
- `ghp_[A-Za-z0-9_]{36,}` (GitHub Personal Access Tokens)
- `ghs_[A-Za-z0-9_]{36,}` (GitHub App Server-to-Server Tokens)
- `github_pat_[A-Za-z0-9_]{82}` (GitHub Fine-Grained Personal Access Tokens)
Any match is replaced with `[REDACTED_TOKEN]`.

---

## 5. Network Security & Container Isolation

GAIN provides production-ready deployment manifests in `deploy/helm/gain` incorporating container and network security controls:

### 5.1 Kubernetes NetworkPolicy Egress Control
- Worker and server pods are governed by strict Kubernetes NetworkPolicies (`deploy/helm/gain/templates/security.yaml`).
- All ingress is disabled by default for worker pods.
- Egress is restricted to DNS (port 53), HTTPS (port 443) to GitHub endpoints, and configurable internal network ranges (`.Values.networkPolicy.egress.allowedCIDRs`) for enterprise forward proxies and Redis work queues.
- Hardcoded RFC1918 exclusions are avoided in favor of templated, perimeter-specific CIDRs.

### 5.2 Container Runtime Hardening
- **Non-Root Execution**: Pods run as non-root user `uid=10001` (`gainuser`).
- **Capability Dropping**: Container security context sets `drop: ["ALL"]`.
- **Dual-Probe Healthchecks**: Container probes support both HTTP `/healthz` and offline/batch `gain config-check` fallback verification.

---

## 6. Governed Interface & Agent Security Boundaries

### 6.1 Model Context Protocol (MCP) Security Gate
The GAIN MCP server (`src/gain/mcp`) acts as a governed domain gateway:
- **RBAC Scopes**: Access requires specific OAuth/Bearer scopes (`gain:metrics:read`, `gain:evidence:read`, `gain:investigation:write`).
- **Tenant Isolation**: Multi-tenant isolation is enforced on every call (`tenant_id`). Requests targeting unassigned tenant partitions are rejected.
- **Rate Limiting**: In-memory token bucket rate limiter (default 100 rpm per client).

### 6.2 PolicyGuard & Prompt Injection Defenses
When autonomous AI agents interact with GAIN via `gain.agent`:
- **Read-Only Enforcement**: The agent cannot execute mutating actions on authoritative GitHub or Jira repositories.
- **Prompt Injection Defense**: `gain.agent.guard.PolicyGuard` inspects synthesized queries and untrusted inputs for jailbreak signatures, system prompt overrides, and role confusion attacks, rejecting compromised execution steps.
