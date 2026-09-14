# Clarifications and Recommended Defaults

| Topic | Why it matters | Recommended default |
|---|---|---|
| API auth | Controls enterprise security and permissions | GitHub App for enterprise/org-scale collection; PAT only for local bootstrap |
| Scope | Determines volume and access model | Explicit configured organizations/repositories; no implicit enterprise-wide crawl |
| Historical period | Affects API cost and completeness | 365 days configurable |
| Re-query window | PRs can change after creation | Re-scan recent window (e.g., 30 days) on each incremental sync |
| Bot handling | Prevents distorted human-flow metrics | Classify HUMAN/BOT/UNKNOWN; exclude BOT from human-oriented KPIs by default |
| Raw retention | Needed for reproducibility | Retain raw payloads or equivalent source snapshot under documented retention policy |
| Storage | Determines scale and query ergonomics | Evaluate Parquet + DuckDB first; relational DB only if operational needs justify it |
| Team mapping | Not inherently guaranteed from PR fields | Make team attribution configurable; never invent team identity |
| Individual reporting | Privacy and gaming risk | Default to aggregated views; make individual detail opt-in and governed |
| Metric history | Metric definitions evolve | Persist metric_version with each observation |
