# ADR 0031: AI Economic ROI and Sensitivity Scenarios

## Status
Accepted

## Context
Executive leadership evaluates AI developer tooling investments by asking for economic Return on Investment (ROI). Presenting single-point monetary forecasts based on unvalidated productivity claims creates legal, financial, and organizational risks.

The GAIN platform must provide an explicit, deterministic economic modeling service that parameterizes costs and benefits transparently.

## Decision
1. We introduce `AIROIService` in `gain.services.ai_roi` as a pure Python, deterministic scenario engine.
2. The economic modeling adheres to a 4-stage separation:
   - **Stage 1 (Measurement)**: Empirical delivery cycle time delta from canonical metrics.
   - **Stage 2 (Attribution)**: Fraction of time efficiency attributed to AI assistance.
   - **Stage 3 (Economic Modeling)**: Parameterized conversion of time saved to gross dollar value using fully loaded developer cost benchmarks ($R_{\text{hourly}}$, default $85/hr).
   - **Stage 4 (Scenario Analysis)**: 3-tier sensitivity matrix (`conservative` at 0.5x, `expected` at 1.0x, `optimistic` at 1.5x) reporting gross savings, net benefit, and ROI percentage.
3. All financial figures are explicitly tagged with `is_modeled=True` and classified as `Modeled` claims. Under no circumstances are monetary savings described as `Observed` facts.
4. If investment costs or developer numbers are omitted, the service falls back to sensible enterprise defaults ($19/seat/mo for Copilot Business, 48 work weeks/yr) while exposing all assumptions clearly in the output contract.

## Consequences
- **Positive**: Complete parameter transparency; multi-scenario risk analysis; zero hallucinations in economic calculations.
- **Negative**: The outputs represent scenario models rather than historical accounting audits.
