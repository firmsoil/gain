# GAIN Security Baseline

- GitHub credentials come from `GITHUB_TOKEN` and are never hard-coded.
- Tokens must never be logged.
- Use a GitHub App or appropriately scoped credential for enterprise deployment; grant only repository/org permissions required by the configured GraphQL fields.
- Raw payloads should be stored in an access-controlled location because actor identifiers can be indirectly identifying.
- Production deployments should add retention policies and encryption at rest for raw data.
- The MVP does not expose an HTTP service and has no public network listener.
