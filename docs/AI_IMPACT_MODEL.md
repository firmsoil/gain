# GAIN AI Impact Analytical Model

**Author:** Lead Implementation Architect  
**Status:** Approved & Implemented (Gate 8)  
**Authoritative References:** `docs/MASTER_SPEC.md` Section 12, `docs/REFERENCE_ARCHITECTURE.md`, `docs/adr/0030-deterministic-ai-impact-and-attribution-engine.md`  

---

## 1. Analytical Mission & Purpose

The **GAIN AI Impact Model** provides an empirical, deterministic methodology to evaluate how AI developer tools (e.g. GitHub Copilot, Cursor) affect software delivery flow, cycle times, and review characteristics across engineering teams.

### Core Non-Negotiable Directives
1. **Never Infer AI Assistance from Generic PR Characteristics**: When authoritative developer-level AI adoption telemetry is absent, the system must refuse to speculate or estimate AI usage based solely on commit frequency, line counts, or PR speed.
2. **Never Confuse Association with Causation**: Statistical shifts between cohorts are tagged as `Associated` by default. Causal attribution (`Attributed`) is permitted only when rigorous experimental controls (e.g. randomized rollout, difference-in-differences controlling for seniority and PR size) are verified.
3. **Pure Deterministic Computation**: All cohort distributions, percentiles (p50, p75, p90, mean), and delta metrics are computed via pure Python algorithms without LLM inference.

---

## 2. Seven-Tier Claim Classification Applied to AI Analytics

| Claim Tier | Empirical Definition in AI Analytics | Example |
| :--- | :--- | :--- |
| **`Observed`** | Direct raw telemetry recorded without transformation. | 18 developers have active Copilot licenses with 4,200 code suggestions accepted. |
| **`Derived`** | Pure mathematical calculations derived from observed facts. | Copilot user PR median cycle time is 14,200 seconds ($p50$). |
| **`Associated`** | Statistically correlated trends where confounding variables may exist. | Copilot users merged PRs 18% faster than non-users (uncontrolled for PR size). |
| **`Attributed`** | Causal effects established through experimental controls. | Controlled diff-in-diff shows 12% cycle time reduction attributable to Copilot. |
| **`Modeled`** | Projections or scenarios derived from parameterized models. | Projected developer capacity savings of 2.5 hours/week based on acceptance ratios. |
| **`Assumed`** | Foundational premises stated without measurement. | Assumed blended developer hourly rate of $85.00/hr. |
| **`Unknown`** | Telemetry missing or insufficient to evaluate. | Authoritative Copilot seat logs unavailable for repo `firmsoil/gain`. |

---

## 3. Analytical Progression Pipeline

```
┌────────────────────────┐
│  Authoritative AI      │ (Copilot seat assignments, daily suggestions,
│  Adoption Telemetry    │  acceptances, lines added)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│   Cohort Formation     │ (AI-Active Cohort vs Non-AI Baseline Cohort)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Confounder Isolation   │ (PR Size [additions/deletions], Author Seniority,
│ & Flow Measurement     │  Review Iterations, Bot Filtering)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Statistical Synthesis  │ (p50/p90 Delta Shift, Throughput Ratio,
│ & Claim Tagging        │  Attribution vs Association Classification)
└────────────────────────┘
```

---

## 4. Confounder Isolation Principles

When measuring the difference in PR cycle time between AI-assisted authors and baseline authors, three primary confounders must be controlled:
1. **PR Size (Complexity)**: AI-generated code might increase the number of lines added, which naturally inflates code review latency. Comparing cohorts without normalizing for size bins ($<100$ lines, $100-500$ lines, $>500$ lines) creates distorted metrics.
2. **Author Experience & Tenure**: High-adoption early adopters are often senior engineers who already merge PRs faster.
3. **Reviewer Latency vs Author Latency**: Differentiating between author active work time and reviewer queue time to isolate where AI assistance actually intervened.
