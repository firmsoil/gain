# Clarifications

| Topic | Decision |
| --- | --- |
| Authority | Human approval establishes an approved product requirement. The subsequent formal SDD specification remains the downstream engineering authority. |
| Jira source of truth | Jira may be the record for an approved work item; GAIN retains a normalized snapshot and immutable lineage. GAIN does not silently overwrite an externally changed Jira issue. |
| Conflict handling | The initial slice only updates an issue when GAIN holds its stable external ID. A future bidirectional synchronizer must detect source-version conflicts and request resolution. |
| Storage | The existing file-backed persistence approach is extended with append-only JSON version files; no second database is introduced. |
| Unknown fields | Optional Jira fields remain `null`/absent. The generation service does not infer project keys, sprint, estimates, assignees, or versions. |
| Imported stories | Jira imports are `DRAFT`, not approved requirements, so imported data still receives human review. |
| Open questions | Material unresolved questions are hard validation errors for approval; non-material advisory ambiguity remains a warning. |

