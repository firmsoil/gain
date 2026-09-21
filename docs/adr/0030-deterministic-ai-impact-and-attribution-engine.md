# ADR 0030: Deterministic AI Impact and Attribution Engine

## Status
Accepted

## Context
Organizations adopting AI coding tools (e.g. GitHub Copilot, Cursor) frequently request quantitative evidence on whether AI accelerates software delivery. However, calculating AI impact by merely comparing all PRs before and after rollout without developer-level adoption telemetry produces severe causal fallacies (confounding team size changes, seasonal variations, PR size differences, and developer tenure).

Furthermore, LLMs must never be permitted to calculate metric deltas or guess whether a PR was AI-authored.

## Decision
1. We introduce `AIImpactService` in `gain.services.ai_impact` as a pure Python, deterministic analytical service.
2. The service operates strictly on authoritative developer telemetry (`AiDeveloperTelemetry`):
   - Telemetry must include direct tool activity (suggestions, acceptances, lines suggested/accepted).
   - If telemetry is absent for a requested repository or cohort, the service deterministically returns `status="insufficient_data"` and tags findings with `ClaimClassification.UNKNOWN`.
3. Cohort formation:
   - When telemetry is present, developers are classified into AI-Active vs Non-Active cohorts.
   - Flow metrics (PR cycle time percentiles p50, p75, p90, mean) are calculated for each cohort using existing canonical datasets.
   - By default, shifts are classified as `Associated` unless experimental controls (randomized assignment or verified diff-in-diff controlling for PR size) are present.
4. No heuristic guessing of AI assistance based on commit frequency or PR line count is permitted.

## Consequences
- **Positive**: Strict analytical rigor; elimination of bogus AI productivity claims; transparency when telemetry is missing.
- **Negative**: Repositories without ingested AI telemetry cannot display direct AI impact numbers.
