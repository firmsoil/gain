# Requirements → Jira → SDD Architecture

## Purpose and boundary

GAIN's existing GitHub analytics flow remains independent:

```text
GitHub GraphQL → raw JSONL → canonical PullRequest → quality → metrics → outputs
```

The requirements capability is an upstream, human-governed path. It never imports the GitHub client, raw PR payloads, canonical PR model, or metrics:

```text
Business Context → structured AI draft → human review → approved canonical story
                                                           ├→ Jira work item
                                                           └→ SDD specification seed
                                                                → specify → clarify → plan → tasks
                                                                → implement → test → converge
```

The seed is not a formal SDD specification. It preserves product intent and traceability so the established SDD workflow can produce the engineering contract. Engineering decisions must be made in that downstream process, not invented during requirements drafting.

## Domain and governance

`BusinessContext` holds BA-supplied problem framing, goal, stakeholders, assumptions, constraints, dependencies, sources, timestamps, and a version. It can be revised append-only before story regeneration. `CanonicalStory` is the provider-neutral requirements exchange model. It has explicit Jira fields (including the Jira workflow status, distinct from GAIN lifecycle status), role/capability/business-value semantics, preconditions, risks, questions, ambiguity flags, and structured `AcceptanceCriterion` entities with separate Given/When/Then fields.

An LLM provider receives a versioned prompt and only the supplied context. The generation service records provider/model/prompt identifiers, input and output hashes, generation parameters, timestamp, and generation ID. It always writes `DRAFT`, even if a provider attempts to make an authoritative claim. The original generated version and every later human change are immutable JSON artifacts.

The state gate is strict:

| State | Meaning | Jira export / SDD promotion |
| --- | --- | --- |
| `DRAFT` | Generated, imported, regenerated, or revised; non-authoritative | Blocked |
| `IN_REVIEW` | Assigned to a named human reviewer | Blocked |
| `APPROVED` | A named human approved a quality-valid version | Allowed |
| `REJECTED` | Reviewer rejected a version | Blocked |

Approval validates required semantics, structured Gherkin, duplicates, unresolved material questions, and quality concerns. Human changes reset approval, requiring a fresh review. Warnings are shown separately from hard errors.

## Jira interoperability

The canonical model is not an Atlassian Document Format (ADF) object. `JiraStoryMapper` is the only Jira presentation boundary:

```text
CanonicalStory → JiraStoryMapper → Jira issue payload → JiraAdapter → Jira Cloud REST
```

It can render Jira wiki-style text or Cloud ADF, maps standard fields (project, issue type, summary, priority, users, labels, components, parent, versions), and puts sprint/story-points in configuration-supplied custom field IDs. Missing optional values stay absent; no project, sprint, estimate, user, or version is fabricated. The `JiraAdapter` isolates HTTP authentication, retryable availability failures, malformed responses, and credential-bearing headers from the requirements domain.

The initial sync contract prevents repeat creates when GAIN already stores an external issue ID/key. The tracker protocol also exposes external-reference lookup for deployments that configure a stable Jira property or custom field. A future bidirectional synchronizer must compare source versions and ask for human resolution on conflicts; this slice does not silently overwrite independently edited Jira content.

## Source of truth and traceability

- Jira can be the product work-management record for an approved issue.
- GAIN stores a normalized, immutable requirements snapshot and its Jira identity for processing and audit.
- The approved SDD specification remains the authoritative engineering contract.

Every saved story includes its source context ID/version, review and approval metadata, generation provenance, Jira identity, and optional formal-specification ID. Promotion writes a seed that retains approved criteria, assumptions, dependencies, questions, human approval, and AI provenance. The CLI's `show-traceability` command reports the persisted chain available in this slice:

```text
Business Context ↔ Story versions ↔ Jira identity ↔ SDD specification seeds
```

The formal specification subsequently connects that seed to the normal SDD plan, tasks, implementation, and tests.

## Storage and observability

Requirements reuse GAIN's file-backed approach rather than introduce another database:

```text
data/requirements/contexts/<context-id>/v<version>.json
data/requirements/stories/<story-id>/v<version>.json
data/requirements/events.jsonl
data/specification-seeds/<promotion-id>.json
```

Version files are append-only. Events contain action metadata and identifiers, not business-context text. The service records context creation, generation and regeneration success/failure, validation, revision, review, approval, rejection, Jira synchronization, and promotion. Jira tokens are configuration values; they are never persisted or written to logs.

## Operator workflow

The CLI intentionally accepts JSON structured output from an approved provider integration, which makes the LLM transport replaceable while retaining a deterministic, testable domain contract.

```bash
gain requirements create-context --input-file context.json --actor ba@example.com
gain requirements revise-context --context-id <context-id> --changes context-edits.json --actor ba@example.com
gain requirements generate-story --context-id <context-id> --structured-output draft.json
gain requirements validate-story --story-id <story-id>
gain requirements review-story --story-id <story-id> --reviewer ba@example.com
gain requirements revise-story --story-id <story-id> --changes edits.json --reviewer ba@example.com
gain requirements approve-story --story-id <story-id> --reviewer ba@example.com
gain requirements jira-payload --story-id <story-id>
gain requirements sync-jira --story-id <story-id>           # optional Jira mode
gain requirements promote-story --story-id <story-id>
gain requirements link-specification --story-id <story-id> --specification-id specs/003-feature --actor architect@example.com
gain requirements show-traceability --story-id <story-id>
```

`generate-story` and `regenerate-story` never infer business intent. A production integration implements the `StoryGenerationProvider` protocol (for example with an OpenAI, Anthropic, or compatible structured-output client) and invokes the same service.
