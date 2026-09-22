# GAIN Service Level Objectives (SLOs) & Operational Reliability

## 1. Executive Summary & Reliability Principles

The GAIN (GitHub AI Intelligence Network) platform serves enterprise engineering leadership, autonomous AI agents, and platform engineering teams at Fortune 100 scale (40,000+ repositories). Because downstream executive decisions and agentic automation depend on deterministic telemetry accuracy, GAIN operates under strict Service Level Objectives (SLOs) and error budgets.

### Core Reliability Principles
1. **GitHub Remains Ground Truth**: Zero telemetry synthesization or statistical extrapolation when upstream data is missing; outages must be recorded explicitly.
2. **Deterministic Computations**: Metric calculations have zero variance across re-runs.
3. **Graceful Degradation**: Temporary rate-limiting on individual GitHub tokens must not halt enterprise-wide ingestion.

---

## 2. Service Level Objectives (SLOs) & Indicators (SLIs)

| Objective Name | Service Level Indicator (SLI) | SLO Target | Measurement Window | Error Budget |
| :--- | :--- | :--- | :--- | :--- |
| **MCP Server Availability** | `sum(rate(gain_mcp_requests_total{status=~"2.."}[5m])) / sum(rate(gain_mcp_requests_total[5m]))` | **99.9%** | 30-day rolling | 43.8 minutes downtime / month |
| **Query Latency (p95)** | `histogram_quantile(0.95, sum(rate(gain_mcp_request_duration_seconds_bucket[5m])) by (le))` | **< 2.000s** | 7-day rolling | 5% exceeding 2.0s |
| **Query Latency (p99)** | `histogram_quantile(0.99, sum(rate(gain_mcp_request_duration_seconds_bucket[5m])) by (le))` | **< 5.000s** | 7-day rolling | 1% exceeding 5.0s |
| **Ingestion Freshness (Critical Tier)** | Elapsed time from upstream GitHub PR merge to canonical Parquet partition write | **< 2 hours** | Per sync cycle | 1% sync cycles delayed |
| **Ingestion Freshness (Standard Tier)** | Elapsed time from upstream GitHub PR merge to canonical Parquet partition write | **< 6 hours** | Per sync cycle | 5% sync cycles delayed |
| **Data Integrity & Lineage** | Ratio of valid canonical PR entities to raw JSONL captured nodes (`canonical_records / raw_records`) | **100.0%** (zero loss) | Per ingestion run | 0 tolerance for silent drop |
| **Quota Continuity** | Percentage of sync cycles completing without unrecoverable `RateLimitError` (via token pool rotation) | **>= 99.5%** | 30-day rolling | <= 0.5% rate-limit aborts |

---

## 3. Error Budget & Burn Rate Alerting

We implement multi-window multi-burn-rate alerts based on Google Cloud SRE best practices:

- **Critical Alert (Page on-call, 14.4x burn rate)**: 2% of 30-day error budget consumed in 1 hour.
- **High Alert (Ticket / Slack notification, 6x burn rate)**: 5% of 30-day error budget consumed in 6 hours.
- **Low Alert (Daily triage, 1x burn rate)**: 10% of 30-day error budget consumed in 3 days.

When error budget consumption exceeds **50% in any rolling 7-day period**:
- Feature deployments and schema migrations are temporarily halted.
- Engineering priority shifts 100% to rate-limit resilience, query optimization, and storage compaction.

---

## 4. Incident Response Runbooks

### Runbook 1: GitHub API Rate-Limit Exhaustion (`GainRateLimitExhaustion`)
1. Check token pool status: `curl http://localhost:8000/readyz | jq .checks.github_tokens`.
2. Review remaining quotas across tokens: check `gain_github_rate_limit_remaining` in Prometheus/Grafana.
3. If using GitHub App authentication:
   - Ensure App installation permissions and token generation secrets are active.
   - Add additional installation tokens to Kubernetes Secret `gain-secret`.
4. If burst backfill is active:
   - Scale down worker concurrency: `kubectl scale cronjob/gain-sync --replicas=0` or reduce `--workers`.
   - The coordinator and workers will automatically resume from the last saved cursor once tokens reset.

### Runbook 2: MCP Server Latency Degradation (`GainMcpHighLatency`)
1. Check Polars predicate pushdown: verify queries filter by `organization` and partition date window (`start_at`..`end_at`).
2. Verify Parquet partition file sizes:
   - Run `gain maintenance stats`.
   - If files are fragmented (< 10MB each), run `gain maintenance compact --execute`.
3. Check HPA pod scaling: verify horizontal autoscaling added pods (`kubectl get hpa gain-mcp`).

### Runbook 3: Ingestion Lag Exceeded (`GainSyncLagExceeded`)
1. Inspect checkpoint store: check `gain_ingestion_pages_total` for stalled repositories.
2. Verify GitHub GraphQL connectivity: `gain config-check`.
3. Inspect worker pod logs: check for malformed JSONL or unparseable upstream schemas.
