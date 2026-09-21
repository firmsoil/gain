# GAIN Multi-Agent Software Engineering Charter & Operating Model

## 1. Operating Model & Team Topology

The GAIN development system employs a disciplined, role-specialized multi-agent software engineering team inside Google Antigravity to evolve the GAIN platform while preserving established architectural invariants.

```
                         LEAD ARCHITECT (Root)
                                   |
         +-------------------------+-------------------------+
         |                         |                         |
         v                         v                         v
   DATA ENGINEER           ANALYTICS ENGINEER        PLATFORM ENGINEER
 (Canonical Entities       (Deterministic Metrics      (Runtime, Config
   & Raw Storage)             & Flow Calculations)      & Client Resilience)
         |                         |                         |
         +-------------------------+-------------------------+
                                   |
                                   v
                           SECURITY ENGINEER
                      (Secrets, Content Safety
                        & Security Gatekeeper)
                                   |
                                   v
                         VERIFICATION ENGINEER
                      (Independent Test Suite,
                        Static Analysis & Proof)
                                   |
                                   v
                        LEAD AGENT INTEGRATION
                        (Synthesis & Invariants)
                                   |
                                   v
                              MAIN BRANCH
```

---

## 2. Specialist Agent Roster & Authority Boundaries

| Agent Name | Role | Primary Scope | Permitted Tools | Mutates Code? |
|:---|:---|:---|:---|:---:|
| **gain-architect** | Principal Architecture Specialist | Architecture boundaries, ADRs, interface governance | `view_file`, `list_dir`, `grep_search`, `find_by_name`, `write_to_file` (docs only) | **NO** (Read-Heavy) |
| **gain-data-engineer** | Data Platform & Modeling Specialist | Domain entities, normalization, raw store, provenance | `view_file`, `list_dir`, `grep_search`, `write_to_file`, `replace_file_content` | **YES** (Data/Schema scope) |
| **gain-analytics-engineer** | Analytics & Metric Specialist | Metric catalog, deterministic calculations, flow stats | `view_file`, `list_dir`, `grep_search`, `write_to_file`, `replace_file_content` | **YES** (Metrics scope) |
| **gain-platform-engineer** | Production Python & Platform Specialist | Runtime, config, logging, HTTP client resilience, CLI | Read tools, `write_to_file`, `replace_file_content`, `run_command` | **YES** (Platform scope) |
| **gain-security-engineer** | Security & Agent Safety Specialist | Credential isolation, untrusted data, security gate | Read tools, `write_to_file` (security gate reports only) | **NO** (Audit & Gate only) |
| **gain-verification-engineer** | Independent Verification Specialist | Automated test authoring, static analysis, test proof | Full read/write/command tools in test scope | **YES** (Test scope) |

---

## 3. Work Assignment & Parallelization Protocol

1. **Parallel Analysis, Serialized Implementation**:
   - Multiple agents may concurrently inspect and audit the codebase without conflict.
   - Implementation work that touches disjoint files (e.g. data models vs platform client vs test suite) runs in decoupled execution tracks.
   - Core files (e.g. `pyproject.toml`, `gain.cli`) are strictly modified through serial lead-agent coordination to prevent merge conflicts.
2. **Branch & Workspace Strategy**:
   - Major feature initiatives run on designated isolated Git branches or worktrees (`feat/<name>`).
   - Small foundational improvements are verified locally against the virtualenv before staged integration into `main`.
3. **Escalation Path**:
   - Any architectural disagreement between specialist agents (e.g. data modeling vs client payload shape) escalates to the **Lead Architect**. The Lead Architect's determination is final and recorded in an Architecture Decision Record (ADR).

---

## 4. Quality, Security & Verification Gates

### Security Gate (`gain-security-engineer`)
Every release or foundational extension must obtain an explicit **PASS** from the Security Engineer documented in `docs/reviews/SECURITY_GATE.md`:
- Zero hardcoded credentials or logged secrets.
- External repository data (PR titles, descriptions) treated as untrusted.
- Read-only GitHub scopes maintained.
- Strict separation between model inference and deterministic calculation.

### Independent Verification Gate (`gain-verification-engineer`)
Before any code is accepted:
- Complete test suite passes with 100% success rate (`pytest -v`).
- Zero linting errors under `ruff check`.
- Zero type errors under `mypy --strict`.
- Explicit verification that the validated first vertical slice has not regressed.

---

## 5. Definition of Done (DoD)

A development stage is complete only when:
1. All assigned specialist reviews are published in `docs/reviews/`.
2. Lead agent synthesis documents findings and classifications in `docs/reviews/MULTI_AGENT_FINDINGS.md`.
3. Foundational code improvements are integrated with zero regressions on existing capabilities.
4. Independent verification produces `docs/reviews/FINAL_VERIFICATION.md` with concrete execution evidence.
5. Security gate produces `docs/reviews/SECURITY_GATE.md` with explicit sign-off.
6. A comprehensive final implementation report is generated in `docs/MULTI_AGENT_IMPLEMENTATION_REPORT.md`.
