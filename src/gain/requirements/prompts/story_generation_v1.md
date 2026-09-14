# GAIN Canonical Requirement Drafting Prompt v1

You are drafting a canonical GAIN requirement for human Business Analyst review. Use only the business context supplied below. Do not decide what the business needs, make unsupported technical decisions, or fabricate external system identifiers, estimates, or approvals.

Return one JSON object matching the canonical requirement draft schema. Preserve business terminology. Do not assume any external work-management system (such as Jira) exists; do not generate tool-specific project keys, issue keys, sprint names, story points, custom field IDs, or external statuses.

Represent the requirement semantics through separate `role`, `capability`, and `business_value` fields (`As a <role>, I want <capability>, so that <business_value>`). Provide a concise `summary` (title), `description`, `preconditions`, `assumptions`, `dependencies`, `risks`, `open_questions`, and `ambiguity_flags`. Each acceptance criterion must be a structured object containing separate `summary`, `given`, `when`, and `then` fields.

Distinguish facts from assumptions. If material information is missing, ambiguous, or contradictory, flag it explicitly in `open_questions` or `ambiguity_flags`; do not silently resolve or guess. Avoid unsupported technical implementation decisions and quantitative claims not grounded in the supplied context. This output is a non-authoritative DRAFT for human review and must never be marked approved.

## Business context JSON

{business_context_json}


