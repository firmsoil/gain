# ADR 0020: Engineering Intelligence Agent Architecture & Interpretive Separation

## Status
Accepted

## Context
Following the completion of GAIN MCP Server (Gate 5) and the stabilization of GAIN's analytical foundation, engineering leadership requires an autonomous, conversational interface to interrogate engineering flow metrics, detect bottlenecks, and investigate changes. 

However, LLMs inherently suffer from hallucinations, stochastic reasoning errors, and lack of mathematical determinism. If the reasoning agent is allowed to calculate metrics or serve as the analytical system of record, GAIN's foundational guarantee of deterministic analytical authority will be destroyed.

## Decision
1. We introduce the **Engineering Intelligence Agent** strictly as an **interpretive and orchestrational layer**.
2. An explicit three-tier separation is established:
   - **GitHub**: Operational Truth (raw repository events).
   - **GAIN Platform**: Analytical Truth (deterministic metrics, canonical entities, lineage, statistical distributions).
   - **Engineering Intelligence Agent**: Interpretive Intelligence (investigation planning, hypothesis evaluation, evidence synthesis).
3. The Agent interacts with GAIN exclusively through the **GAIN MCP Server** interface boundary, consuming domain tools rather than database tables or calculation scripts.
4. The Agent executes a structured investigation cycle: Gateway -> Planner -> Policy Guard -> Tool Router -> Evidence Synthesizer -> LLM Gateway.

## Consequences
- **Positive**: Complete preservation of analytical integrity; zero hallucinated metric values; testable investigation flows; decoupled architecture.
- **Negative**: Adds orchestrational components (Gateway, Planner, Policy Guard, Router, Synthesizer) requiring comprehensive unit and contract testing.
