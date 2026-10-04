"""Unified one-shot repository scanner for AI-Native KPIs and SE 3.0 metrics.

Allows GAIN to analyze any local or remote GitHub repository on-demand,
extracting in-tree AI telemetry and generating an executive scorecard.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import structlog
import typer

from gain.adapters.git_local import LocalGitSourceAdapter
from gain.attribution.detector import AIAttributionDetector
from gain.config import get_settings
from gain.logging import configure_logging
from gain.services.ai_impact import AIImpactService
from gain.services.ai_roi import AIROIService
from gain.services.metrics import MetricService
from gain.storage.ai_telemetry import write_ai_telemetry

log = structlog.get_logger(__name__)


def register_scan_commands(app: typer.Typer) -> None:
    @app.command("scan")
    def cli_scan(
        target: str = typer.Argument(
            ".", help="Target repository: local path (e.g. '.'), GitHub URL, or 'owner/name'."
        ),
        days: int = typer.Option(90, "--days", "-d", help="Analysis time window in days."),
        output_format: str = typer.Option(
            "table", "--format", "-f", help="Output format: table, markdown, or json."
        ),
        out: Path | None = typer.Option(None, "--out", "-o", help="Optional output file path."),
    ) -> None:
        """Scan any repository to produce the complete AI-Native KPI & SE 3.0 Scorecard."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()
        run_id = str(uuid.uuid4())

        adapter = LocalGitSourceAdapter(settings)
        metric_svc = MetricService(settings)
        impact_svc = AIImpactService(settings)
        roi_svc = AIROIService(settings)
        detector = AIAttributionDetector()

        target_path = Path(target)
        is_local = target_path.exists() and adapter.is_git_repository(target_path)

        # 1. Ingestion / Data Acquisition
        if is_local:
            typer.echo(f"[*] Ingesting local git repository at: {target_path.resolve()}", err=True)
            ingest_result = adapter.ingest_local_repository(target_path, days=days, run_id=run_id)
            repo_name = ingest_result["repository"]
            total_prs = ingest_result["total_prs"]
            total_commits = ingest_result["total_commits"]
            ai_prs = ingest_result["ai_assisted_prs"]
            ai_penetration = ingest_result["ai_penetration_rate"]
            detected_tools = ingest_result["detected_tools"]
        else:
            # Parse remote repository format: owner/name or https://github.com/owner/name
            clean_target = target.strip()
            match = re.search(
                r"github\.com[/:]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?$", clean_target
            )
            if match:
                repo_name = f"{match.group(1)}/{match.group(2)}"
            elif "/" in clean_target:
                repo_name = clean_target
            else:
                repo_name = f"firmsoil/{clean_target}"

            typer.echo(
                f"[*] Ingesting remote GitHub repository: {repo_name} (window: {days} days)",
                err=True,
            )
            from gain.cli.common import _build_client
            from gain.schema import normalize_records
            from gain.storage.analytics import write_canonical
            from gain.storage.raw import RawStore
            from gain.sync import PullRequestBackfill

            backfill = PullRequestBackfill(settings, _build_client(settings))
            backfill.run(ingestion_run_id=run_id, repositories=[repo_name])

            raw_records = RawStore(settings.raw_dir).read_run(run_id)
            prs, _ = normalize_records(raw_records)
            safe_repo = repo_name.replace("/", "__")
            canonical_path = (
                settings.canonical_dir / f"pull_requests__{safe_repo}__{run_id}.parquet"
            )
            write_canonical(prs, canonical_path)

            # In-tree AI attribution detection
            telemetry = detector.synthesize_developer_telemetry(repository=repo_name, prs=prs)
            write_ai_telemetry(
                telemetry, settings.canonical_dir / f"ai_telemetry__{safe_repo}.parquet"
            )
            report = detector.analyze_repository(repository=repo_name, prs=prs)

            total_prs = len(prs)
            total_commits = 0
            ai_prs = report.ai_assisted_prs
            ai_penetration = report.ai_penetration_rate
            detected_tools = [str(t.value) for t in report.detected_tools]

        # 2. Compute Deterministic SE 3.0 KPIs
        ct_res = metric_svc.query_pr_cycle_time(repository=repo_name)
        refactor_res = metric_svc.query_refactoring_ratio(repository=repo_name)
        bloat_res = metric_svc.query_code_bloat(repository=repo_name)
        tax_res = metric_svc.query_verification_tax(repository=repo_name)
        rework_res = metric_svc.query_defect_rework(repository=repo_name)
        impact_res = impact_svc.analyze_impact(repository=repo_name)

        # 3. Two-Ledger Economic ROI Estimation
        dev_count = max(2, int(impact_res.cohort_definition.get("ai_active_developers") or 5))
        roi_res = roi_svc.calculate_roi_scenario(
            population="repository_scan",
            staff_size=dev_count,
            developer_count=dev_count,
            use_dora_model=True,
        )

        # 4. Construct Unified Payload
        scorecard: dict[str, Any] = {
            "repository": repo_name,
            "scan_run_id": run_id,
            "evaluation_window_days": days,
            "telemetry_overview": {
                "total_prs_evaluated": total_prs,
                "total_commits_evaluated": total_commits,
                "ai_assisted_prs": ai_prs,
                "ai_penetration_rate": f"{ai_penetration:.1%}",
                "detected_tools": detected_tools,
            },
            "flow_metrics": {
                "metric_id": ct_res.metric_id,
                "merged_prs": ct_res.merged_count,
                "p50_cycle_time_seconds": ct_res.summary_stats.get("p50_seconds"),
                "p90_cycle_time_seconds": ct_res.summary_stats.get("p90_seconds"),
            },
            "code_quality_and_bloat": {
                "refactoring_ratio_metric": refactor_res.metric_id,
                "aggregate_refactoring_ratio": refactor_res.summary_stats.get(
                    "aggregate_refactoring_ratio"
                ),
                "pure_additions_percentage": refactor_res.summary_stats.get(
                    "pure_addition_percentage"
                ),
                "code_bloat_metric": bloat_res.metric_id,
                "mean_net_additions_per_file": bloat_res.summary_stats.get(
                    "mean_net_additions_per_file"
                ),
                "bloat_flagged_percentage": bloat_res.summary_stats.get("bloat_flag_percentage"),
            },
            "verification_and_stability": {
                "verification_tax_metric": tax_res.metric_id,
                "mean_review_latency_hours": tax_res.summary_stats.get("mean_latency_hours"),
                "high_friction_review_pct": tax_res.summary_stats.get("high_friction_percentage"),
                "defect_rework_metric": rework_res.metric_id,
                "hotfix_pr_percentage": rework_res.summary_stats.get("hotfix_percentage"),
            },
            "cohort_ai_impact": {
                "status": impact_res.status,
                "epistemic_classification": impact_res.classification.value,
                "findings": impact_res.findings,
            },
            "economic_two_ledger_estimate": {
                "estimated_annual_investment": roi_res.investment_cost,
                "estimated_reclaimed_value": roi_res.headcount_reinvestment_value,
                "estimated_net_benefit": roi_res.net_benefit,
                "payback_period_years": roi_res.payback_period_years,
            },
        }

        # 5. Output Formatting
        if output_format == "json":
            rendered = json.dumps(scorecard, indent=2)
        elif output_format == "markdown":
            rendered = _render_markdown(scorecard)
        else:
            rendered = _render_table(scorecard)

        if out is not None:
            out.write_text(rendered, encoding="utf-8")
            typer.echo(f"[+] Output successfully saved to: {out}")
        else:
            typer.echo(rendered)


def _render_table(s: dict[str, Any]) -> str:
    t = s["telemetry_overview"]
    f = s["flow_metrics"]
    q = s["code_quality_and_bloat"]
    v = s["verification_and_stability"]
    e = s["economic_two_ledger_estimate"]

    eval_days = s["evaluation_window_days"]
    run_id_short = s["scan_run_id"][:8]
    refact_ratio = float(q.get("aggregate_refactoring_ratio") or 0.0)
    pure_adds = q.get("pure_additions_percentage") or 0.0
    net_adds = q.get("mean_net_additions_per_file") or 0.0
    bloat_pct = q.get("bloat_flagged_percentage") or 0.0
    lat_mean = v.get("mean_review_latency_hours") or 0.0
    lat_fric = v.get("high_friction_review_pct") or 0.0

    eval_prs_msg = f"{t['total_prs_evaluated']} (AI-Assisted: {t['ai_assisted_prs']})"
    tools_msg = ", ".join(t["detected_tools"]) or "None explicit"

    lines = [
        "",
        "=== GAIN AI-NATIVE SOFTWARE ENGINEERING (SE 3.0) SCORECARD ===",
        f"Repository:               {s['repository']}",
        f"Evaluation Window:        {eval_days} days (Run ID: {run_id_short})",
        "----------------------------------------------------------------------",
        "1. AI ADOPTION & ATTRIBUTION TELEMETRY:",
        f"   - Evaluated PRs:       {eval_prs_msg}",
        f"   - AI Penetration Rate: {t['ai_penetration_rate']}",
        f"   - Detected Tools:      {tools_msg}",
        "",
        "2. SE 2.0 BLOAT & CODE HEALTH (Hassan et al. 2026):",
        f"   - Refactoring Ratio:   {refact_ratio:.1%} (Pure Adds: {pure_adds}%)",
        f"   - Code Bloat Index:    {net_adds} lines/file ({bloat_pct}% flagged)",
        "",
        "3. FLOW & VERIFICATION TAX (DORA 2026):",
        f"   - PR Cycle Time (p50): {f.get('p50_cycle_time_seconds') or 0.0}s",
        f"   - Review Latency Mean: {lat_mean} hrs ({lat_fric}% >48h)",
        f"   - Hotfix / Defect Rate:{v.get('hotfix_pr_percentage') or 0.0}% of merged PRs",
        "",
        "4. ECONOMIC VALUE LEDGER (Two-Ledger Model):",
        f"   - Net Economic Value:  ${e.get('estimated_net_benefit') or 0.0:,.2f}",
        f"   - Reclaimed Capacity:  ${e.get('estimated_reclaimed_value') or 0.0:,.2f}",
        "----------------------------------------------------------------------",
    ]
    return "\n".join(lines)


def _render_markdown(s: dict[str, Any]) -> str:
    t = s["telemetry_overview"]
    f = s["flow_metrics"]
    q = s["code_quality_and_bloat"]
    v = s["verification_and_stability"]
    e = s["economic_two_ledger_estimate"]

    tools_str = ", ".join(t["detected_tools"]) or "None"
    refact_ratio = float(q.get("aggregate_refactoring_ratio") or 0.0)
    pure_adds = q.get("pure_additions_percentage") or 0.0
    net_adds = q.get("mean_net_additions_per_file") or 0.0
    bloat_pct = q.get("bloat_flagged_percentage") or 0.0
    p50_ct = f.get("p50_cycle_time_seconds") or 0.0
    lat_mean = v.get("mean_review_latency_hours") or 0.0
    lat_fric = v.get("high_friction_review_pct") or 0.0
    hotfix_pct = v.get("hotfix_pr_percentage") or 0.0

    return f"""# GAIN AI-Native Software Engineering (SE 3.0) Scorecard

**Target Repository:** `{s["repository"]}`  
**Evaluation Window:** {s["evaluation_window_days"]} Days | **Run ID:** `{s["scan_run_id"]}`  
**Theoretical Foundation:** Hassan et al. (ACM TOSEM 2026) & Google Cloud DORA 2026  

---

## 1. AI Presence & Attribution Telemetry
| Metric | Value | Interpretation |
| :--- | :--- | :--- |
| **Total PRs Evaluated** | `{t["total_prs_evaluated"]}` | Total pull requests evaluated in window |
| **AI-Assisted PRs** | `{t["ai_assisted_prs"]}` | PRs with verified in-tree AI evidence |
| **AI Penetration Rate** | `{t["ai_penetration_rate"]}` | Proportion of flow with observed AI |
| **Detected Tools** | `{tools_str}` | Tooling signatures detected in git |

---

## 2. SE 2.0 Additive Churn & Code Bloat Diagnostics
| Metric | Formula / Catalog ID | Value | Status |
| :--- | :--- | :--- | :--- |
| **Refactoring Ratio** | `GAIN-QUAL-003` | `{refact_ratio:.1%}` | Pure adds: `{pure_adds}%` |
| **Code Bloat Index** | `GAIN-QUAL-004` | `{net_adds} lines/f` | Bloat (>100): `{bloat_pct}%` |

---

## 3. Flow Velocity & Verification Tax
| Metric | Catalog ID | Value | Notes |
| :--- | :--- | :--- | :--- |
| **Median Cycle Time (p50)** | `GAIN-PR-001` | `{p50_ct}s` | PR duration (created to merged) |
| **Review Queue Latency** | `GAIN-QUAL-005` | `{lat_mean}h` | Friction (>48h): `{lat_fric}%` |
| **Defect Rework Rate** | `GAIN-QUAL-006` | `{hotfix_pct}%` | Hotfix / rollback frequency |

---

## 4. Google Cloud DORA 2026 Two-Ledger Economics
- **Estimated Net Benefit:** `${e.get("estimated_net_benefit") or 0.0:,.2f}`
- **Reclaimed Headcount Capacity:** `${e.get("estimated_reclaimed_value") or 0.0:,.2f}`
- **Estimated Tool Investment:** `${e.get("estimated_annual_investment") or 0.0:,.2f}`
- **Payback Period:** `{e.get("payback_period_years") or 0.0} years`
"""
