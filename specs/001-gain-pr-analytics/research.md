# Research / Technology Decisions

## GitHub GraphQL vs REST
GraphQL is preferred because it allows precise field selection and nested retrieval. GitHub documents cursor-based pagination for GraphQL connections with `first`/`last` values between 1 and 100. Query complexity, node limits, and rate limits require bounded page sizes and query decomposition. citeturn269712search6turn269712search0turn319563search0

REST remains an adapter for endpoints where it is more appropriate or where the required data is not exposed efficiently through the chosen GraphQL query. GitHub exposes REST endpoints for pull requests, files, commits, and reviews. citeturn319563search4turn319563search1

## Authentication
GitHub documents personal access tokens, GitHub Apps, and OAuth for GraphQL authentication. For organization-scale enterprise collection, a GitHub App is the preferred production direction because access can be explicitly scoped to an installation. citeturn269712search4

## Rate limits and resilience
GraphQL uses a points-based primary limit and has secondary limits on concurrency, endpoint pressure, and compute. GitHub states that responses can time out after about 10 seconds under its GraphQL processing limit and recommends reducing query complexity and splitting large queries. Therefore collection must use backoff, bounded concurrency, checkpoints, and smaller query shapes. citeturn319563search0

## Analytics engine
Evaluate Polars + Parquet + DuckDB as the default analytical path for an MVP because it provides columnar storage and efficient local analytical SQL without requiring a database service. Pandas remains an acceptable fallback for small in-memory transformations.

## Metric framework alignment
DORA currently describes five software delivery performance metrics, including change lead time, deployment frequency, failed deployment recovery time, change fail rate, and deployment rework rate. GAIN's GitHub PR data can inform adjacent leading indicators such as PR lifecycle elapsed time and throughput, but does not provide the production-deployment semantics required to claim those DORA metrics. citeturn319563search2

## Decision
MVP: Python + Polars + Parquet + DuckDB + Pydantic + Typer + pytest + Ruff + mypy, with a GraphQL-first collector and REST adapters.
