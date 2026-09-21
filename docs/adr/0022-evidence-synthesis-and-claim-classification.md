# ADR 0022: Evidence Synthesis and Claim Classification Taxonomy

## Status
Accepted

## Context
A major failure mode of AI-generated analytical summaries is blurring the boundary between verified empirical observations and ungrounded inferences. In engineering leadership discussions, presenting a correlated trend as an established causal attribution (e.g. asserting that an AI assistant caused cycle time reduction without controlling for PR size or author seniority) can lead to disastrous enterprise decisions.

## Decision
1. All material analytical claims synthesized by the Engineering Intelligence Agent must be anchored in an immutable **Evidence Package** (`EvidencePackage`).
2. Every claim statement produced in an investigation response must be tagged with a classification from the strict 7-tier taxonomy:
   - `Observed`: Directly observed, unprocessed raw engineering telemetry.
   - `Derived`: Pure mathematical/statistical output from verified deterministic algorithms.
   - `Associated`: Statistically correlated patterns where confounding variables may exist.
   - `Attributed`: Experimentally or counterfactually verified causal links.
   - `Modeled`: Projections or scenario simulations based on parameterized models.
   - `Assumed`: Foundational premises stated without measurement.
   - `Unknown`: Unverifiable or missing telemetry.
3. Every evidence package must record:
   - Investigation ID & Plan ID
   - Target population and time window
   - Metric definitions and versions utilized
   - Lineage traces back to raw JSONL provenance coordinates
   - Limitations, caveats, and data quality indicators

## Consequences
- **Positive**: Complete auditability of agent findings; elimination of causal fallacies; explicit transparency of caveats and assumptions.
- **Negative**: Adds mandatory schema serialization and validation overhead to the synthesis phase.
