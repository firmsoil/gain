# GAIN Requirements → Jira → SDD

This feature package is the upstream requirements-engineering layer for GAIN. It is intentionally separate from the GitHub analytics package. A Jira-compatible story is an interoperability object, not an engineering specification and not an instruction to implement.

The authoritative workflow is:

```text
Business Context → AI draft → Human review → Approved Story → SDD specification seed
                                                  ↓
                                                Jira
```

The package follows the existing Spec Kit order: `spec.md`, `clarifications.md`, `plan.md`, `data-model.md`, and `tasks.md`. An approved story is only a seed for the ordinary SDD `specify → clarify → plan → tasks → implement → converge` workflow.

