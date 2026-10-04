# ADR 0051: Universal Local Git Adapter, In-Tree AI Attribution, and Scan CLI

## Status
Accepted

## Context
Prior to this enhancement, GAIN required external GitHub API credentials (PAT or GitHub App tokens) and/or external vendor APIs (such as the GitHub Copilot API) to evaluate engineering delivery flow, AI adoption rates, and economic ROI.

This created several operational barriers:
1. **Air-Gapped & Offline Constraints**: Developers and auditors evaluating on-premise, air-gapped, or ad-hoc local clones could not run GAIN without generating API tokens and configuring network access.
2. **Missing Vendor Telemetry**: Many organizations do not have administrative access to central vendor seat APIs (e.g. Copilot Enterprise API), yet their repositories contain rich observable in-tree evidence (e.g. commit trailers such as `Co-authored-by: GitHub Copilot`, `Generated with Cursor`, `Claude Code`, `Codeium`, or AI bot identities).
3. **Friction in Ad-Hoc Evaluation**: Leadership and practitioners lacked a unified "single command" to point GAIN at any repository path or URL to obtain an executive scorecard across flow velocity, code bloat, verification tax, and two-ledger economics.

## Decision
1. **Local Git Source Adapter (`LocalGitSourceAdapter`)**:
   - Implemented in `gain.adapters.git_local.LocalGitSourceAdapter`.
   - Ingests commits, file-level churn (`additions`, `deletions`, `files_changed`), and branch-merge topologies directly via local `git log --numstat` without network calls.
   - Reconstructs canonical `CanonicalCommit` and `PullRequest` domain models offline.

2. **In-Tree AI Attribution Detector (`AIAttributionDetector`)**:
   - Implemented in `gain.attribution.detector.AIAttributionDetector` with domain models in `gain.attribution.models`.
   - Parses Git commit trailers (`Co-authored-by: GitHub Copilot`, `Claude Code`, `Generated with Cursor Composer`, `Codeium`) and recognized bot usernames.
   - Automatically synthesizes `AiDeveloperTelemetry` records from observable Git history.
   - Wired as an automatic fallback into `AIImpactService` so that cohort velocity comparisons and two-ledger economic evaluations function seamlessly on any repository with observable in-tree evidence.

3. **Expanded SE 3.0 Quality & Flow KPI Suite**:
   - **Verification Tax Index (`GAIN-QUAL-005`)**: Pure Python deterministic calculation of review latency distribution ($t_{\text{merged}} - t_{\text{created}}$) in `gain.metrics.verification_tax`, flagging review queues pending $>48$ hours.
   - **Defect Rework & Fragility Rate (`GAIN-QUAL-006`)**: Pure Python deterministic calculation of follow-up rework and hotfix churn within a 14-day operational window in `gain.metrics.defect_churn`.
   - Registered both metrics with strict schemas in `docs/metrics/metric-catalog.yaml`.

4. **Unified One-Shot CLI Scanner (`gain scan`)**:
   - Implemented in `gain.cli.scan` and exposed via the root CLI application.
   - Accepts local filesystem paths (`gain scan .`) or remote repository targets (`gain scan owner/repo` or GitHub URLs).
   - Generates scorecards across four dimensions (AI Adoption, Code Health, Verification Tax, Two-Ledger Economics) in `table`, `markdown`, or `json` formats.

5. **Defensive Parquet Partition Reader**:
   - Hardened `PartitionedReader.scan` in `gain.storage.partitioning` to defensively inspect file schemas and filter out zero-column or corrupted parquet files.

## Consequences
- **Positive**:
  - GAIN can now run against **any** codebase on-demand with zero API tokens or external configuration.
  - Eliminates external vendor API dependencies for AI adoption analysis by capitalizing on observable Git telemetry.
  - Zero-LLM numerical metric invariant is fully preserved (pure Python deterministic computations).
  - Validated vertical slice and backward compatibility remain 100% intact.
- **Negative / Constraints**:
  - Local Git analysis approximates PR boundaries via merge commits when running purely offline against Git clones without GitHub API access.
  - Commit trailer detection relies on developers or AI tooling maintaining standard git trailers or identifiable author logins.
