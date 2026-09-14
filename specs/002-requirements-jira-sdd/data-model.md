# Data Model: Canonical GAIN Requirements & Adapter Architecture

## Architectural Principle

> **GAIN Requirement is the canonical internal requirements representation. Jira is an external projection/integration target, not the system-of-record domain model.**

## Canonical entities

| Entity | Key fields | Invariants |
| --- | --- | --- |
| `BusinessContext` | `context_id`, `version`, problem, goal, stakeholders, constraints | Upstream BA input; immutable, versioned, never rewritten. |
| `CanonicalRequirement` (alias `CanonicalStory`) | `requirement_id`, `version`, story semantics (role, capability, business_value), acceptance criteria, preconditions, assumptions, dependencies, risks, open questions, ambiguity flags, lifecycle, provenance, governance, SDD link, `external_references`, `custom_fields` | Authoritative internal representation independent of Jira; draft by default; rich provenance and approval metadata. |
| `AcceptanceCriterion` | `criterion_id`, summary, given, when, then, validation status, and_given, and_when, and_then, examples, notes | First-class structured domain objects stored provider-neutrally and rendered only at projection boundaries. |
| `ExternalReference` | `external_system`, `external_project`, `external_type`, `external_id`, `external_key`, `external_url`, `external_version`, `last_synced_at`, `metadata` | Generalized external system link (e.g., Jira issue, GitHub issue); secondary reference, never the primary identity. |
| `SDDSpecificationSeed` | `promotion_id`, `requirement_id`, `requirement_version`, `source_context_id`, `source_context_version`, `external_references`, product requirements, acceptance criteria, assumptions, approval, AI provenance | Originates strictly from approved canonical requirements; engineering decisions default empty; pure Git/SDD flows require zero Jira references. |

## Jira Projection Mapping (Adapter Layer)

The Jira mapping layer is isolated in `gain.requirements.jira` and translates deterministically between canonical requirements and Jira payloads without polluting the core domain.

| Canonical GAIN Requirement | Jira Field | Notes |
| --- | --- | --- |
| `summary` | `summary` | Required |
| `story.requirement_type` | `issuetype.name` | Configurable allowed issue types |
| Structured story semantics + criteria | `description` | Formatted as Jira Cloud ADF or Jira Wiki markup |
| `priority` | `priority.name` | Configurable allowed priorities |
| `labels` / `components` | `labels` / `components` | Validated against optional allowed sets |
| `custom_fields["project_key"]` or adapter config | `project.key` | Derived from config if absent |
| `custom_fields["story_points"]` | Configured custom field ID | (e.g., `customfield_10016`) |
| `custom_fields["sprint"]` | Configured custom field ID | (e.g., `customfield_10020`) |
| `custom_fields["parent_key"]` / `epic_key` | `parent.key` | Validated for consistency |
| `custom_fields["reporter"]` / `assignee` | Configured user identifier | (e.g., `accountId`) |


