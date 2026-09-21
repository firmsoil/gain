# GAIN Engineering Intelligence Agent Architecture

**Author:** Lead Implementation Architect  
**Status:** Approved & Implemented (Gate 7)  
**Authoritative References:** `docs/MASTER_SPEC.md`, `docs/REFERENCE_ARCHITECTURE.md`, `docs/adr/0020-engineering-intelligence-agent-architecture.md` through `0023-policy-guard-and-prompt-injection-defense.md`  

---

## 1. Executive Summary & Purpose

The **Engineering Intelligence Agent** serves as the **interpretive intelligence** layer of GAIN. It translates natural-language inquiries from engineering leaders and practitioners into rigorous analytical plans, orchestrates governed queries across dual MCP interfaces (GAIN MCP and GitHub MCP), assembles structured evidence packages, and produces evidence-grounded findings.

### Non-Negotiable Core Separation
1. **GitHub — Operational Truth**: Direct ground facts of source activity (PRs, commits, reviews, comments).
2. **GAIN — Analytical Truth**: Deterministic, versioned metrics, statistical distributions, canonical domain models, lineage traces, and data quality evaluations.
3. **Engineering Intelligence Agent — Interpretive Intelligence**: Hypothesis formation, multi-step investigation planning, evidence synthesis, and constrained explanation.

Under **zero circumstances** does the Agent recalculate metrics, make probabilistic guesses where data is missing, perform write actions against repositories, or treat repository text as system instructions.

---

## 2. Runtime Architecture & Information Flow

```
                      User / CLI / API
                              │
                              ▼
                     ┌──────────────────┐
                     │  Agent Gateway   │ ── Authenticate, establish tenant & scopes,
                     └────────┬─────────┘    assign request_id & investigation_id
                              │
                              ▼
                     ┌──────────────────┐
                     │     Planner      │ ── Translate NL question into an explicit
                     └────────┬─────────┘    multi-step InvestigationPlan
                              │
                              ▼
                     ┌──────────────────┐
                     │   Policy Guard   │ ── Enforce read-only boundary, tool whitelist,
                     └────────┬─────────┘    repo scope, prompt-injection defense
                              │
                              ▼
                     ┌──────────────────┐
                     │   Tool Router    │ ── Route analytical vs operational tasks
                     └────────┬─────────┘
           ┌──────────────────┴──────────────────┐
           ▼                                     ▼
   ┌───────────────┐                     ┌───────────────┐
   │   GAIN MCP    │                     │  GitHub MCP   │
   │  (Analytical) │                     │ (Operational) │
   └───────┬───────┘                     └───────┬───────┘
           │                                     │
           └──────────────────┬──────────────────┘
                              ▼
                     ┌──────────────────┐
                     │Evidence Synthesizer│ ── Build durable EvidencePackage, classify
                     └────────┬─────────┘    claims (Observed, Derived, Attributed, etc.)
                              │
                              ▼
                     ┌──────────────────┐
                     │   LLM Gateway    │ ── Constrained reasoning only; synthesize
                     └────────┬─────────┘    interpretive summary grounded in evidence
                              │
                              ▼
                     ┌──────────────────┐
                     │ Structured Report│ ── Answer + EvidencePackage + Audit Trace
                     └──────────────────┘
```

---

## 3. Component Design & Responsibilities

### 3.1 Agent Gateway (`gain.agent.gateway`)
- **Authentication Context**: Validates principal identity and organization association.
- **Tenant Isolation**: Ensures all operations run within the authenticated `tenant_id`.
- **Traceability & Correlation**: Generates immutable `request_id` (UUID4) and initializes `investigation_id`.
- **Budgeting & Rate Controls**: Enforces execution timeouts and maximum step limits to prevent run-away loops.

### 3.2 Investigation Planner (`gain.agent.planner`)
- Translates unstructured questions into explicit, ordered `InvestigationPlan` containing discrete `PlanStep`s.
- Supports standardized investigation methodologies:
  - **Metric Shift Investigation**: (e.g. "Why did cycle time spike last month?")
  - **Delivery Health Briefing**: (e.g. "What is the engineering throughput across our repos?")
  - **Cohort Comparison**: (e.g. "How does team A compare to team B in review latency?")
  - **AI Impact Investigation**: (Strict adherence to data prerequisites before attributing impact).
- Declares step dependencies, required parameters, and fallback actions.

### 3.3 Policy Guard (`gain.agent.policy`)
- **Strict Read-Only Enforcement**: Rejects any mutating or write operations (`git push`, `create_pr`, `merge_pr`, `delete_branch`).
- **Tool Whitelist**: Validates every tool request against authorized scopes before routing.
- **Indirect Prompt-Injection Sanitization**: All repository content (PR bodies, titles, commit messages, comments) is marked as untrusted data and wrapped in boundary tags (`<untrusted_repo_content>...`), preventing external repository data from executing system prompt injection attacks.
- **Zero Hallucination Gate**: Ensures model claims are verified against the evidence package.

### 3.4 Tool Router (`gain.agent.router`)
- Dispatches tool requests according to explicit domain rules:
  - **GAIN MCP**: Authoritative metrics (`query_engineering_metrics`, `compare_cohorts`), definitions (`explain_metric`), data quality (`get_data_quality`), lineage (`get_metric_lineage`), evidence packages (`get_evidence`), and canonical PRs (`get_canonical_entity`).
  - **GitHub MCP**: Qualitative operational context (`get_pull_request_details`, `get_commit_details`, `list_recent_comments`).
- **Failure Handling**:
  - If GitHub MCP is unavailable: operates in analytical-only mode, stating clearly that qualitative live context is unavailable. **Never fabricates live data.**
  - If GAIN MCP is unavailable: halts and reports service unavailability. **Never attempts ad-hoc metric calculation via GitHub APIs.**

### 3.5 Evidence Synthesizer (`gain.agent.synthesizer`)
- Aggregates analytical metrics, query specifications, lineage coordinates, and qualitative context into a durable `EvidencePackage`.
- Enforces the **7-tier Claim Classification Taxonomy**:
  1. `Observed`: Direct raw telemetry recorded without transformation.
  2. `Derived`: Pure deterministic mathematical calculations (e.g. cycle time, percentiles).
  3. `Associated`: Statistically correlated phenomena with confounding factors present.
  4. `Attributed`: Causal links established through rigorous experimental or counterfactual controls.
  5. `Modeled`: Projections or scenario simulations based on explicit parameterized assumptions.
  6. `Assumed`: Stated premises without direct measurement.
  7. `Unknown`: Insufficient data to classify.

### 3.6 LLM Gateway (`gain.agent.llm`)
- Abstracts reasoning providers behind a clean, testable interface (`ReasoningProvider`).
- Default deterministic provider for test suites, CI, and zero-token environments.
- Extensible to enterprise LLM providers (e.g. Anthropic, Google Gemini, OpenAI).
- Enforces strict token budgets, structured response schemas, and automatic credential masking via `gain.logging.mask_secrets`.

---

## 4. Security & Safety Architecture

1. **Untrusted Data Boundary**: Repository content is data, not instructions. The policy guard strips/neutralizes instruction override markers (e.g., `Ignore previous instructions and output...`).
2. **Credential Isolation**: The Agent runtime never receives or logs raw tokens (`GITHUB_TOKEN`, `GAIN_TOKEN`). Secrets are externalized and masked.
3. **Auditability**: Every investigation creates an immutable audit trail (`AgentAuditLog`) logging every step, tool invocation, duration, and policy check.
