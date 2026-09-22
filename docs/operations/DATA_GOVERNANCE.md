# GAIN Enterprise Data Governance, Privacy, & Data Classification

## 1. Scope & Governance Charter

This document defines data classification tiers, Personally Identifiable Information (PII) protections, audit retention periods, and right-to-be-forgotten compliance mechanisms for GAIN across 40,000+ GitHub repositories.

---

## 2. Enterprise Data Classification Matrix

| Classification Tier | Data Elements Included | Encryption at Rest | Encryption in Transit | Masking / Anonymization Required | Retention Policy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1 — Public / Unrestricted** | Public repository identifiers, open-source PR numbers, standard license types | Optional | TLS 1.3 | No | Indefinite |
| **Tier 2 — Internal Business Data** | Internal repo names, aggregate flow metrics (Cycle Time p50/p90, DORA throughput, PR volume) | AES-256 (GCM) | TLS 1.3 | No | 2 years |
| **Tier 3 — Confidential Engineering Telemetry** | PR titles, review comments, issue descriptions, commit messages, Jira/Linear story IDs | AES-256 (GCM) | TLS 1.3 | Secret-masking regex filter applied during ingestion logging | 1 year (Canonical) |
| **Tier 4 — Restricted / PII & Credentials** | GitHub author logins, committer email addresses, PATs, App Private Keys, installation IDs | AES-256 + KMS / Vault | TLS 1.3 + mTLS | **Mandatory HMAC-SHA256 pseudonymization**; zero credential logging | Credentials: rotate every 90 days; Raw PII: purge after 90 days |

---

## 3. PII Governance & Cryptographic Pseudonymization

GAIN implements deterministic cryptographic pseudonymization via `gain.privacy`:

### Mathematical Specification
Given an author GitHub login $L$ and an organization-scoped salt $S$:
$$P = \text{anon\_} + \text{Truncate}_{12}(\text{HMAC-SHA256}(S, \text{lowercase}(\text{trim}(L))))$$

For bot identities (e.g. `dependabot[bot]`), the `[bot]` suffix is preserved while the base identity is pseudonymized to allow bot activity segmentation.

### Right-to-be-Forgotten & GDPR / CCPA Compliance
Under GDPR Article 17 (Right to Erasure) and CCPA:
1. **Cryptographic Erasure via Key Shredding**:
   - Each business organization or tenant maintains an independent HMAC salt.
   - When an employee departs or requests erasure, their mapping can be invalidated individually, or when a business unit is de-provisioned, destroying the salt renders all historical pseudonyms cryptographically irreversible.
2. **Raw JSONL Purge**:
   - Raw ingestion JSONL containing raw GitHub logins is purged on a strict 90-day retention schedule (`gain maintenance purge-raw --days 90`).
   - Downstream canonical datasets only contain pseudonymized identifiers when `GAIN_PII_MASK_AUTHORS=true`.

---

## 4. Secret Sanitization & Defense-in-Depth

All structured log events emitted via `structlog` pass through the `mask_secrets` processor in `src/gain/logging.py`.
Patterns matching GitHub PATs (`ghp_`, `gho_`, `ghs_`, `ghu_`, `github_pat_`), JWT tokens, and private keys (`BEGIN PRIVATE KEY`) are replaced with `[REDACTED_SECRET]` before stream emission or disk write.
