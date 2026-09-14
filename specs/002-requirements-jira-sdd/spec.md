# Requirements Engineering and Jira Interoperability Specification

## Purpose

Provide a governed upstream layer that turns BA-supplied business context into a reviewable, Jira-compatible requirement without replacing GAIN's existing SDD process.

## Scope

- Capture immutable, versioned business-context artifacts.
- Generate a structured draft through a provider-neutral LLM boundary.
- Preserve the original generated draft and all human revisions.
- Require deterministic validation and explicit human approval before promotion or Jira export.
- Map the provider-neutral canonical story to Jira wiki text or Jira Cloud ADF through a dedicated mapper.
- Produce a traceable SDD specification seed from an approved story.

## Non-goals

- A backlog UI, autonomous product decisions, a Jira replacement, or a new SDD framework.
- Making Jira mandatory for requirements or specifications.
- Directly coupling requirements to GitHub collection, canonical PR records, or metrics.

## Functional requirements

1. Business context includes an ID, version, business problem, goal, stakeholders, assumptions, constraints, dependencies, sources, and timestamps.
2. A canonical story supports Jira fields, separate role/capability/business-value fields, structured Gherkin acceptance criteria, governance, provenance, and optional external identity.
3. Model generation uses only supplied context; generated output is always stored as `DRAFT` and can never self-approve.
4. Revisions append a new story version and retain earlier versions.
5. Approval requires a named human reviewer and no hard validation errors.
6. Only an approved story can be exported or promoted.
7. Jira payload generation is configurable, supports wiki and ADF descriptions, and does not invent absent optional values.
8. Jira HTTP concerns are isolated behind an issue-tracker adapter with bounded retry handling and redacted observability.
9. A promotion seed preserves product requirements, acceptance criteria, provenance, assumptions, dependencies, open questions, and approval metadata while leaving engineering decisions empty.
10. Requirements events record identifiers and action metadata without recording business-context content by default.

## Acceptance criteria

- A malformed provider result is rejected by the Pydantic contract.
- Missing semantic fields and malformed Gherkin are surfaced deterministically.
- A generated draft cannot be promoted or serialized for Jira export.
- Human approval creates a new immutable version and leaves the original generated version accessible.
- Jira custom-field identifiers are configuration inputs; they are never hard-coded.
- Jira import results in a non-authoritative draft unless it passes through GAIN review.
- The existing GitHub collection → raw persistence → PR normalization → metric flow continues to pass its regression tests.

