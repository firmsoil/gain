# Security Policy & Vulnerability Reporting

## 1. Supported Versions

Security updates and patches are actively maintained for the following versions:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| **0.1.x** | :white_check_mark: | Active production release branch |
| < 0.1.0 | :x: | Deprecated pre-release prototypes |

---

## 2. Reporting a Vulnerability

The GAIN engineering team takes security vulnerabilities seriously. If you discover a security issue or potential flaw, **please do not open a public GitHub issue**.

### Reporting Channels
- **Email**: Report vulnerabilities directly to `security@gain.enterprise` or open a private GitHub Security Advisory.
- **Content**: Please include:
  - Description of the vulnerability and attack vector.
  - Step-by-step proof of concept (PoC) or reproducible test case.
  - Affected components (`gain.mcp`, `gain.github`, `gain.storage`).
  - Proposed remediation, if known.

---

## 3. Response SLAs

- **Initial Triage & Acknowledgment**: Within 24 hours.
- **Assessment & Reproducibility Confirmation**: Within 48 hours.
- **Remediation & Patch Release**:
  - **Critical (CVSS 9.0-10.0)**: Within 72 hours.
  - **High (CVSS 7.0-8.9)**: Within 7 days.
  - **Medium/Low (CVSS < 7.0)**: In the next scheduled sprint release.

---

## 4. Security Principles Enforced in Codebase

1. **Credential Isolation**: Tokens and private keys must only be supplied via environment variables or secure files (`GAIN_GITHUB_APP_PRIVATE_KEY_PATH`).
2. **Zero Credential Logging**: All log events pass through automated secret regex filtering (`mask_secrets`).
3. **No Unsafe Code Execution**: Repository contents (PR titles, issue bodies, author names) are strictly treated as untrusted strings and never passed to `eval()`, `exec()`, or raw shell commands.
4. **Non-Root Container Runtime**: Production containers execute under UID 10001 (`gain`) with `allowPrivilegeEscalation: false` and dropped Linux capabilities.
