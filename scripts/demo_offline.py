#!/usr/bin/env python3
"""GAIN Demo — Offline vertical-slice walkthrough with synthetic PR data.

This script demonstrates the full GAIN pipeline **without** a live GitHub token:
  1. Seeds synthetic raw JSONL data for the last year (Sep 2025 – Aug 2026)
  2. Normalises raw records into canonical PullRequest Parquet
  3. Validates data quality
  4. Computes the GAIN-PR-001 cycle-time metric
  5. Computes GAIN-PR-010 monthly tabular statistics on PRs created, merged, and closed
  6. Prints all tabular reports and summaries to stdout

Usage:
    python scripts/demo_offline.py
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

# ── ensure src/ is on the path when running as a script ──────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyStatsMetric
from gain.quality import validate_pull_requests
from gain.schema import normalize_records
from gain.storage.analytics import (
    read_canonical,
    write_canonical,
    write_cycle_time_observations,
    write_monthly_stats,
)

# ─── Configuration ────────────────────────────────────────────────────────
DEMO_RUN_ID = "demo-run-001"
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
CANONICAL_DIR = DATA_DIR / "canonical"
METRICS_DIR = DATA_DIR / "metrics"
METRIC_CATALOG_PATH = Path("docs/metrics/metric-catalog.yaml")


# ─── Synthetic PR Data Generator (Last 12 Months: 2025-09 to 2026-08) ─────
def build_synthetic_pr_dataset() -> list[dict]:
    records: list[dict] = []

    # 12 monthly templates: (year, month, pr_definitions)
    # PR tuple: (repo, pr_num, author, author_type, day, delay, unmerged, draft, add, del, files)
    monthly_plan = [
        ("2025-09", [
            ("backend", 101, "alice", "User", 2, 0.2, False, False, 45, 10, 2),
            ("backend", 102, "bob", "User", 15, 3.5, False, False, 210, 40, 6),
            ("frontend", 201, "grace", "User", 20, 1.0, False, False, 90, 15, 3),
        ]),
        ("2025-10", [
            ("backend", 103, "carol", "User", 5, 0.5, False, False, 30, 5, 1),
            ("backend", 104, "dependabot[bot]", "Bot", 12, 0.1, False, False, 5, 5, 1),
            # Closed unmerged
            ("frontend", 202, "henry", "User", 18, None, True, False, 120, 80, 5),
        ]),
        ("2025-11", [
            ("backend", 105, "alice", "User", 8, 2.0, False, False, 180, 30, 4),
            ("frontend", 203, "grace", "User", 14, 0.4, False, False, 55, 12, 2),
            ("frontend", 204, "henry", "User", 22, 4.0, False, False, 310, 95, 9),
        ]),
        ("2025-12", [
            ("backend", 106, "dave", "User", 3, 1.5, False, False, 95, 20, 3),
            ("backend", 107, "bob", "User", 10, 5.0, False, False, 420, 110, 11),
            ("frontend", 205, "grace", "User", 19, 0.3, False, False, 25, 4, 1),
        ]),
        ("2026-01", [
            ("backend", 108, "alice", "User", 7, 0.8, False, False, 60, 15, 2),
            ("backend", 109, "eve", "User", 16, None, True, False, 75, 25, 4),  # Closed unmerged
            ("frontend", 206, "henry", "User", 21, 2.2, False, False, 140, 35, 5),
        ]),
        ("2026-02", [
            ("backend", 110, "carol", "User", 4, 1.1, False, False, 85, 18, 3),
            ("backend", 111, "dependabot[bot]", "Bot", 11, 0.05, False, False, 2, 2, 1),
            ("frontend", 207, "grace", "User", 24, 0.9, False, False, 70, 10, 2),
        ]),
        ("2026-03", [
            ("backend", 112, "bob", "User", 6, 3.0, False, False, 260, 50, 7),
            ("backend", 113, "alice", "User", 15, 0.4, False, False, 40, 8, 1),
            ("frontend", 208, "henry", "User", 22, 1.8, False, False, 185, 45, 6),
        ]),
        ("2026-04", [
            ("backend", 114, "dave", "User", 9, 2.5, False, False, 230, 60, 5),
            ("frontend", 209, "grace", "User", 14, 0.5, False, False, 50, 12, 2),
            ("frontend", 210, "henry", "User", 28, None, True, False, 90, 30, 3),  # Closed unmerged
        ]),
        ("2026-05", [
            ("backend", 115, "alice", "User", 3, 0.6, False, False, 70, 15, 2),
            ("backend", 116, "bob", "User", 12, 4.2, False, False, 350, 80, 10),
            ("frontend", 211, "grace", "User", 20, 1.2, False, False, 110, 20, 4),
        ]),
        ("2026-06", [
            ("backend", 117, "carol", "User", 5, 0.3, False, False, 25, 5, 1),
            ("backend", 118, "eve", "User", 17, 2.0, False, False, 160, 40, 5),
            ("frontend", 212, "henry", "User", 25, 3.1, False, False, 240, 70, 8),
        ]),
        ("2026-07", [
            ("backend", 119, "dave", "User", 8, 1.8, False, False, 190, 45, 5),
            ("backend", 120, "alice", "User", 19, 0.7, False, False, 65, 14, 2),
            ("frontend", 213, "grace", "User", 23, 0.4, False, False, 35, 8, 1),
        ]),
        ("2026-08", [
            ("backend", 121, "alice", "User", 1, 0.19, False, False, 82, 11, 4),
            ("backend", 122, "bob", "User", 3, 3.27, False, False, 320, 95, 12),
            ("backend", 123, "carol", "User", 5, 0.05, False, False, 12, 3, 1),
            ("backend", 124, "dependabot[bot]", "Bot", 7, 0.02, False, False, 4, 4, 1),
            # Outlier
            ("backend", 125, "dave", "User", 10, 14.1, False, False, 1450, 280, 42),
            # Closed unmerged
            ("backend", 126, "eve", "User", 15, None, True, False, 60, 20, 3),
            ("backend", 127, "frank", "User", 20, None, False, True, 30, 0, 2),       # Draft
            ("backend", 128, "alice", "User", 25, 0.27, False, False, 145, 32, 7),
            ("frontend", 214, "grace", "User", 2, 0.5, False, False, 200, 45, 8),
            ("frontend", 215, "henry", "User", 8, 3.85, False, False, 510, 120, 15),
            ("frontend", 216, "grace", "User", 18, 0.16, False, False, 25, 8, 2),
            ("frontend", 217, "henry", "User", 28, None, False, False, 88, 22, 5),    # Open PR
        ]),
    ]

    for ym, pr_list in monthly_plan:
        year, month = map(int, ym.split("-"))
        for (
            repo_short, pr_num, author, a_type, c_day, merge_delay,
            closed_unmerged, is_draft, adds, dels, files
        ) in pr_list:
            owner = "acme"
            name = repo_short
            repo_full = f"{owner}/{name}"
            repo_id = f"R_kgDOAcme{name.capitalize()}"

            created_iso = f"{year:04d}-{month:02d}-{c_day:02d}T10:00:00Z"
            closed_iso = None
            merged_iso = None
            state = "OPEN"
            review_dec = None

            if merge_delay is not None:
                # Merged PR
                state = "CLOSED"
                review_dec = "APPROVED"
                # Calculate merge date
                delay_hours = int(merge_delay * 24)
                merge_day = c_day + (delay_hours // 24)
                merge_hour = 10 + (delay_hours % 24)
                if merge_hour >= 24:
                    merge_day += merge_hour // 24
                    merge_hour = merge_hour % 24
                # Stay within month bounds for simplicity
                safe_day = min(merge_day, 28)
                merged_iso = f"{year:04d}-{month:02d}-{safe_day:02d}T{merge_hour:02d}:00:00Z"
                closed_iso = merged_iso
            elif closed_unmerged:
                # Closed without merging
                state = "CLOSED"
                review_dec = "CHANGES_REQUESTED"
                close_day = min(c_day + 2, 28)
                closed_iso = f"{year:04d}-{month:02d}-{close_day:02d}T16:00:00Z"

            records.append({
                "metadata": {
                    "collected_at": "2026-09-01T00:00:00+00:00",
                    "cursor": None,
                    "ingestion_run_id": DEMO_RUN_ID,
                    "name": name,
                    "owner": owner,
                    "page_number": 1,
                    "repository_id": repo_id,
                    "repository_name_with_owner": repo_full,
                },
                "node": {
                    "id": f"PR_{repo_short.upper()}_{pr_num}",
                    "number": pr_num,
                    "author": {"__typename": a_type, "login": author},
                    "createdAt": created_iso,
                    "closedAt": closed_iso,
                    "mergedAt": merged_iso,
                    "state": state,
                    "isDraft": is_draft,
                    "additions": adds,
                    "deletions": dels,
                    "changedFiles": files,
                    "reviewDecision": review_dec,
                },
            })

    return records


# ── Helpers ───────────────────────────────────────────────────────────────
def banner(text: str) -> None:
    width = 76
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def pretty(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


# ── Main Pipeline ─────────────────────────────────────────────────────────
def main() -> None:
    for d in (RAW_DIR, CANONICAL_DIR, METRICS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    synthetic_records = build_synthetic_pr_dataset()

    # ── Step 1: Seed raw JSONL ────────────────────────────────────────────
    banner("Step 1 ▸ Seeding synthetic raw JSONL (trailing 12 months: 2025-09 to 2026-08)")
    run_dir = RAW_DIR / DEMO_RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)

    from collections import defaultdict
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for record in synthetic_records:
        key = f"{record['metadata']['owner']}__{record['metadata']['name']}"
        by_repo[key].append(record)

    for repo_key, records in by_repo.items():
        path = run_dir / f"{repo_key}__page-00001.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        print(f"  ✓ Wrote {len(records):>2} records → {path}")

    total_raw = sum(len(r) for r in by_repo.values())
    print(f"\n  Raw store total: {total_raw} records across {len(by_repo)} repo pages")

    # ── Step 2: Normalize ─────────────────────────────────────────────────
    banner("Step 2 ▸ Normalising raw records → canonical PullRequest models")
    from gain.storage.raw import RawStore
    raw_records = RawStore(RAW_DIR).read_run(DEMO_RUN_ID)
    prs, errors = normalize_records(raw_records)

    print(f"  Raw records read   : {len(raw_records)}")
    print(f"  Canonical PRs      : {len(prs)}")
    print(f"  Normalization errors: {len(errors)}")

    # ── Step 3: Data-quality validation ───────────────────────────────────
    banner("Step 3 ▸ Data-quality validation")
    quality_issues = validate_pull_requests(prs)
    if quality_issues:
        for issue in quality_issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}")
    else:
        print("  ✓ All quality checks passed — 0 issues")

    # ── Step 4: Write canonical Parquet ───────────────────────────────────
    banner("Step 4 ▸ Writing canonical Parquet dataset")
    canonical_path = CANONICAL_DIR / f"pull_requests__{DEMO_RUN_ID}.parquet"
    write_canonical(prs, canonical_path)
    print(f"  ✓ {canonical_path}  ({canonical_path.stat().st_size:,} bytes)")

    report = {
        "run_id": DEMO_RUN_ID,
        "raw_records": len(raw_records),
        "canonical_records": len(prs),
        "normalization_errors": errors,
        "quality_issues": [vars(i) for i in quality_issues],
        "canonical_path": str(canonical_path),
    }
    report_path = DATA_DIR / f"normalization_report__{DEMO_RUN_ID}.json"
    report_path.write_text(pretty(report), encoding="utf-8")
    print(f"  ✓ {report_path}")

    # Read back from Parquet (round-trip test)
    canonical_prs = read_canonical(canonical_path)

    # ── Step 5: Compute GAIN-PR-001 cycle-time metric ─────────────────────
    banner("Step 5 ▸ Computing GAIN-PR-001 cycle-time metric")
    catalog = MetricCatalog(METRIC_CATALOG_PATH)
    ct_defn = catalog.get(CycleTimeMetric.metric_id)
    print(f"  Metric catalog entry : {ct_defn['metric_id']} v{ct_defn['metric_version']}")

    observations = CycleTimeMetric.observations(canonical_prs)
    print(f"  Merged PRs with cycle time: {len(observations)}")

    obs_path = METRICS_DIR / "gain-pr-001-cycle-time.parquet"
    write_cycle_time_observations(observations, obs_path)

    summary = CycleTimeMetric.summary(observations)
    summary["metric_id"] = CycleTimeMetric.metric_id
    summary["metric_version"] = CycleTimeMetric.metric_version
    summary["generated_at"] = datetime.now(UTC).isoformat()

    summary_path = METRICS_DIR / "gain-pr-001-cycle-time-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    p50_h = summary['p50_seconds'] / 3600
    p75_h = summary['p75_seconds'] / 3600
    p90_h = summary['p90_seconds'] / 3600
    mean_h = summary['mean_seconds'] / 3600
    print(f"  p50 (median)     : {summary['p50_seconds']:>10,.0f} s  ({p50_h:>6.1f} h)")
    print(f"  p75              : {summary['p75_seconds']:>10,.0f} s  ({p75_h:>6.1f} h)")
    print(f"  p90              : {summary['p90_seconds']:>10,.0f} s  ({p90_h:>6.1f} h)")
    print(f"  mean             : {summary['mean_seconds']:>10,.0f} s  ({mean_h:>6.1f} h)")

    # ── Step 6: Compute GAIN-PR-010 Monthly Tabular Statistics ───────────
    banner("Step 6 ▸ Monthly Tabular Statistics on PRs (Created, Merged, Closed)")
    monthly_defn = catalog.get(MonthlyStatsMetric.metric_id)
    print(f"  Metric ID            : {monthly_defn['metric_id']} v{monthly_defn['metric_version']}")
    print(f"  Name                 : {monthly_defn['name']}")
    print(f"  Formula              : {monthly_defn['formula']}\n")

    # 6.1 Total monthly statistics across all repositories
    monthly_stats = MonthlyStatsMetric.calculate(canonical_prs, months=12)
    print("  ── Overall Monthly PR Activity (Trailing 12 Months) ──\n")
    print(textwrap.indent(MonthlyStatsMetric.format_table(monthly_stats), "  "))

    # Save monthly stats parquet and json
    monthly_parquet = METRICS_DIR / "gain-pr-010-monthly-stats.parquet"
    write_monthly_stats(monthly_stats, monthly_parquet)
    print(f"\n  ✓ {monthly_parquet} ({monthly_parquet.stat().st_size:,} bytes)")

    monthly_summary = {
        "metric_id": MonthlyStatsMetric.metric_id,
        "metric_version": MonthlyStatsMetric.metric_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "months_analyzed": 12,
        "monthly_records": [s.to_dict() for s in monthly_stats],
    }
    monthly_json = METRICS_DIR / "gain-pr-010-monthly-stats.json"
    monthly_json.write_text(json.dumps(monthly_summary, indent=2, default=str), encoding="utf-8")
    print(f"  ✓ {monthly_json}")

    # 6.2 By-Repository Breakdown
    print("\n  ── Segmented Monthly PR Activity by Repository ──\n")
    repo_stats = MonthlyStatsMetric.calculate(canonical_prs, months=12, by_repo=True)
    print(textwrap.indent(MonthlyStatsMetric.format_table(repo_stats), "  "))

    # 6.3 Author-Level Monthly Activity (Opt-in with Responsible Use Advisory)
    print("\n  ── Author-Level PR Activity (Trailing 3 Months, Human Contributors) ──\n")
    author_stats = MonthlyStatsMetric.calculate(
        canonical_prs, months=3, by_author=True, include_bots=False
    )
    print(textwrap.indent(MonthlyStatsMetric.format_table(author_stats), "  "))

    # ── Output Artifacts Summary ──────────────────────────────────────────
    banner("Demo Complete — Output Artifacts")
    print(f"  Raw JSONL Directory  : {run_dir}/")
    print(f"  Canonical Parquet    : {canonical_path}")
    print(f"  Normalization Report : {report_path}")
    print(f"  Cycle Time Parquet   : {obs_path}")
    print(f"  Cycle Time Summary   : {summary_path}")
    print(f"  Monthly Stats Parquet: {monthly_parquet}")
    print(f"  Monthly Stats JSON   : {monthly_json}")
    print()


if __name__ == "__main__":
    main()
