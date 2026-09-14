# Technical Plan: Canonical Requirements Architecture

## Architecture

```text
gain.requirements.models       canonical requirement domain models, external reference abstractions
gain.requirements.generation   prompt artifact, provider protocol, provenance capture
gain.requirements.quality      deterministic domain quality validation (hard errors and warnings)
gain.requirements.service      context, versioning, approval, promotion orchestration
gain.requirements.storage      immutable JSON version/event storage
gain.requirements.sdd          downstream SDD specification seed adapter
gain.requirements.jira         external Jira adapter, ADF/wiki mapper, REST client
gain.cli                       operator commands
```

### Dependency Boundary

The requirements domain (`models`, `service`, `storage`, `quality`, `sdd`, `generation`) has zero dependency on Jira APIs, Jira SDKs, or HTTP clients. Jira integration is contained in `gain.requirements.jira` as an adapter and projection target.

The requirements package never imports `gain.github`, `gain.sync`, `gain.metrics`, `gain.schema`, or PR storage. The GitHub analytics pipeline does not import the requirements package.

## Flow

1. Persist `BusinessContext` v1.
2. Pass business context and canonical prompt to `StoryGenerationProvider`.
3. Schema-validate into a non-authoritative `CanonicalRequirement` draft, record provenance, and persist v1.
4. Reviewer reviews and revises or approves a new version.
5. **Pure Git/SDD Flow**: An approved requirement is promoted to `SDDSpecificationSeed` without touching Jira.
6. **Jira Integration Flow (Optional)**: Jira mapper projects the approved requirement to Jira payload (ADF/wiki), synchronizes via `JiraAdapter`, and records Jira external references in a new immutable requirement version.


## Storage

`data/requirements/contexts/<context-id>/v<version>.json`, `stories/<story-id>/v<version>.json`, and `events.jsonl` are append-only artifacts. `data/specification-seeds/` contains promotion records. These files are deliberately independent of raw GitHub telemetry.

