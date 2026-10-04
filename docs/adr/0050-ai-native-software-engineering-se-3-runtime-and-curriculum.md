# ADR 0050: AI-Native Software Engineering (SE 3.0) Runtime, Metrics, and Curriculum

## Status
Accepted

## Context
Generative AI tools in software engineering (SE 2.0) have predominantly operated as code-generation assistants (copilots, autocomplete). As demonstrated by Hassan et al. (*Towards AI-Native Software Engineering*, ACM TOSEM 2026), this paradigm induces severe systemic challenges:
1. **Additive Bias & Maintainability Drag**: AI assistants bias heavily toward generating new lines of code rather than refactoring or simplifying existing abstractions, causing code bloat and maintenance degradation.
2. **Ephemeral Intent**: Human intent communicated during prompting is discarded once code is generated, eliminating the original specification and rationale needed for future maintenance.
3. **Unbounded Compound Systems**: Complex multi-step LLM workflows lack latency governance, deadline budgets, and cost-effective model tiered routing.
4. **Brute-Force Prompt Engineering**: Prompting remains an empirical, fragile process lacking structured domain engineering and closed-loop feedback.

GAIN requires a formal adoption of SE 3.0 principles while strictly preserving its non-negotiable architectural invariants: GitHub ground truth, deterministic zero-LLM numerical metric computations, transport independence, and epistemic rigor.

## Decision
1. **Pillar 1: Deterministic Metrics & Intent Archiving**
   - Introduce `RefactoringRatioMetric` (`GAIN-QUAL-003`) and `CodeBloatMetric` (`GAIN-QUAL-004`) in `gain.metrics.code_bloat` as pure Python deterministic algorithms.
   - Establish `CanonicalIntent` in `gain.model.intent` as a canonical domain entity with immutable Parquet persistence via `gain.storage.intents`.
   - Expose bloat inspection via `gain bloat` CLI.

2. **Pillar 2: Runtime.next Compound SLA Architecture**
   - Implement `SLABudgetTracker` in `gain.agent.runtime.slack` calculating dynamic DAG slack buffers ($T_{\text{slack}} = T_{\text{deadline}} - T_{\text{crit}}$) and audit histories.
   - Implement `TieredModelRouter` in `gain.agent.runtime.router` directing structured/deterministic classification tasks to local edge SLMs ($\le 8\text{B}$) while reserving frontier models for deep causal attribution.

3. **Pillar 3: Teammate.next Conversational Alignment**
   - Implement `AlignmentSession` in `gain.agent.alignment` with a hard limit of $k \le 3$ dialogue turns to clarify ambiguous user requirements prior to execution.
   - Implement `IntentVerifier` in `gain.agent.verifier` enforcing non-empty claims, proper epistemic bounds (`ClaimType.ASSOCIATED` for non-randomized cohorts), and detecting hallucinations prior to plan execution.

4. **Pillar 4: FM.next Domain Curriculum & Calibration Flywheel**
   - Implement `DomainCurriculum` and `TaxonomyNode` in `gain.curriculum.taxonomy` formalizing software engineering knowledge and foundational skills into structured grounding contexts.
   - Implement `PromptCalibrationService` in `gain.services.calibration` to index analyst thumbs-up feedback into reusable few-shot exemplars.

## Consequences
- **Positive**:
  - Direct quantitative detection of SE 2.0 additive code bloat and technical debt.
  - Full provenance and archival of engineering intent alongside synthesized code.
  - Bounded agent execution time and optimal token economics via tiered model routing.
  - Elimination of manual prompt hacking via systematic curriculum taxonomy and closed-loop calibration.
- **Negative / Constraints**:
  - Added schema maintenance overhead for canonical intent records.
  - Agent investigations require pre-flight verification pass, adding minimal local evaluation overhead.
