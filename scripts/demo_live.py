#!/usr/bin/env python3
"""GAIN Live Demo — Real-time GitHub PR ingestion & analytics against Spinnaker.

This script executes the complete GAIN pipeline against live GitHub GraphQL telemetry:
  1. Validates GitHub API connectivity and authentication
  2. Queries live pull request pages with cursor-based pagination
  3. Archives raw JSONL payloads with ingestion provenance
  4. Normalizes raw payloads into canonical PullRequest domain entities
  5. Runs data-quality validation rules
  6. Computes GAIN-PR-001 observable cycle-time metrics (mean, p50, p75, p90, p95)
  7. Computes GAIN-PR-010 monthly tabular flow statistics (created, merged, closed, merge rate)
  8. Emits Parquet datasets and summary JSON reports

Usage:
    python scripts/demo_live.py
    python scripts/demo_live.py --repo firmsoil/spinnaker
    python scripts/demo_live.py --repo spinnaker/spinnaker --months 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ── Ensure src/ is on Python module search path ─────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gain.github.client import GitHubGraphQLClient
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyStatsMetric
from gain.quality import validate_pull_requests
from gain.schema import normalize_records
from gain.storage.analytics import (
    write_canonical,
    write_cycle_time_observations,
    write_monthly_stats,
)
from gain.storage.raw import RawStore


def banner(title: str) -> None:
    width = 78
    print(f"\n{'━' * width}")
    print(f"  {title}")
    print(f"{'━' * width}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GAIN Live Demo — Pull Request Analytics against Spinnaker",
    )
    parser.add_argument(
        "--repo",
        default="spinnaker/spinnaker",
        help="Target GitHub repository (e.g. firmsoil/spinnaker or spinnaker/spinnaker)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=2,
        help="Number of trailing months to backfill (default: 2)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=25,
        help="GraphQL connection page size (1-100, default: 25)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_slug: str = args.repo
    if "/" not in repo_slug:
        print(f"Error: Invalid repository '{repo_slug}'. Expected 'owner/repo'.", file=sys.stderr)
        sys.exit(1)
    owner, name = repo_slug.split("/", 1)

    # ── Resolve Token ────────────────────────────────────────────────────────
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GAIN_GITHUB_TOKEN")
    if not token:
        # Check gh CLI if available
        import shutil
        import subprocess

        if shutil.which("gh"):
            try:
                proc = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, check=True
                )
                token = proc.stdout.strip()
            except subprocess.SubprocessError:
                pass

    if not token:
        print(
            "Error: GITHUB_TOKEN environment variable not found. "
            "Please set GITHUB_TOKEN or authenticate via 'gh auth login'.",
            file=sys.stderr,
        )
        sys.exit(1)

    now = datetime.now(UTC)
    start_at = now - timedelta(days=args.months * 30)
    run_id = f"live-spinnaker-{now.strftime('%Y%m%d-%H%M%S')}"

    output_dir = Path("data")
    raw_dir = output_dir / "raw" / run_id
    canonical_dir = output_dir / "canonical"
    metrics_dir = output_dir / "metrics"
    catalog_path = Path("docs/metrics/metric-catalog.yaml")

    for d in (raw_dir, canonical_dir, metrics_dir):
        d.mkdir(parents=True, exist_ok=True)

    banner(f"GAIN Live Demo — Target Repository: {repo_slug}")
    print(f"  Run ID            : {run_id}")
    print(f"  Collection Window : {start_at.strftime('%Y-%m-%d')} → {now.strftime('%Y-%m-%d')}")
    print(f"  Page Size         : {args.page_size}")
    print(f"  Target Repository : {repo_slug}\n")

    # ── Step 1: GraphQL Collection & Raw Persistence ─────────────────────────
    banner("Step 1 ▸ Live GitHub GraphQL Pull Request Collection")
    client = GitHubGraphQLClient(token=token, page_size=args.page_size)
    raw_store = RawStore(output_dir / "raw")

    page_count = 0
    total_nodes = 0

    try:
        for page in client.iter_pull_request_pages(owner, name, since=start_at, until=now):
            page_count += 1
            node_count = len(page.nodes)
            total_nodes += node_count
            raw_store.append_page(
                ingestion_run_id=run_id,
                owner=owner,
                name=name,
                page_number=page_count,
                cursor=page.end_cursor,
                repository_id=page.repository_id,
                repository_name_with_owner=page.repository_name_with_owner,
                nodes=page.nodes,
            )
            print(
                f"  [GraphQL Page {page_count:>2}] Retrieved {node_count:>2} PRs | "
                f"hasNext={page.has_next_page}"
            )
    except Exception as exc:
        print(f"  Error querying GitHub GraphQL API: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n  ✓ Collected {total_nodes} live PRs across {page_count} pages.")
    print(f"  ✓ Raw JSONL archive saved to: {raw_dir}/")

    if total_nodes == 0:
        print(f"\n  Note: Repository '{repo_slug}' returned 0 pull requests in this window.")
        print("  Testing zero-record boundary conditions for normalization and reporting.")

    # ── Step 2: Canonical Normalization & Quality Checks ─────────────────────
    banner("Step 2 ▸ Canonical Domain Normalization & Invariant Validation")
    raw_records = raw_store.read_run(run_id)
    canonical_prs, errors = normalize_records(raw_records)
    quality_issues = validate_pull_requests(canonical_prs)

    canonical_path = canonical_dir / f"pull_requests__{run_id}.parquet"
    write_canonical(canonical_prs, canonical_path)

    print(f"  Raw Records Ingested   : {len(raw_records)}")
    print(f"  Canonical Pull Requests: {len(canonical_prs)}")
    print(f"  Normalization Errors   : {len(errors)}")
    print(f"  Quality Invariant Violations: {len(quality_issues)}")
    print(
        f"  ✓ Persisted canonical dataset: {canonical_path} "
        f"({canonical_path.stat().st_size:,} bytes)"
    )

    # ── Step 3: Compute GAIN-PR-001 Observable Cycle Time ───────────────────
    banner("Step 3 ▸ GAIN-PR-001 Cycle Time Computation (Merged PRs)")
    catalog = MetricCatalog(catalog_path)
    cycle_defn = catalog.get(CycleTimeMetric.metric_id)
    print(f"  Metric ID   : {cycle_defn['metric_id']} v{cycle_defn['metric_version']}")
    print(f"  Name        : {cycle_defn['name']}")
    print(f"  Formula     : {cycle_defn['formula']}\n")

    observations = CycleTimeMetric.observations(canonical_prs)
    obs_path = metrics_dir / f"gain-pr-001-cycle-time__{run_id}.parquet"
    write_cycle_time_observations(observations, obs_path)

    summary_raw = CycleTimeMetric.summary(observations)
    summary: dict[str, Any] = dict(summary_raw)
    summary["metric_id"] = CycleTimeMetric.metric_id
    summary["metric_version"] = CycleTimeMetric.metric_version
    summary["generated_at"] = now.isoformat()
    summary["repository"] = repo_slug

    summary_path = metrics_dir / f"gain-pr-001-cycle-time-summary__{run_id}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    raw_count = summary_raw["count"]
    count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
    p50 = summary_raw["p50_seconds"]
    p75 = summary_raw["p75_seconds"]
    p90 = summary_raw["p90_seconds"]
    mean = summary_raw["mean_seconds"]

    print(f"  Sample Size (Merged PRs): {count}")
    if (
        count > 0
        and p50 is not None
        and p75 is not None
        and p90 is not None
        and mean is not None
    ):
        p50_h = p50 / 3600
        p75_h = p75 / 3600
        p90_h = p90 / 3600
        mean_h = mean / 3600
        print(f"  p50 (Median Cycle Time) : {p50:>10,.0f} s ({p50_h:>5.1f} h)")
        print(f"  p75                     : {p75:>10,.0f} s ({p75_h:>5.1f} h)")
        print(f"  p90                     : {p90:>10,.0f} s ({p90_h:>5.1f} h)")
        print(f"  Mean Cycle Time         : {mean:>10,.0f} s ({mean_h:>5.1f} h)")
    else:
        print("  No merged PRs available in this window to calculate cycle duration.")

    # ── Step 4: Compute GAIN-PR-010 Monthly Flow Statistics ─────────────────
    banner("Step 4 ▸ GAIN-PR-010 Monthly Flow Statistics (Created, Merged, Closed)")
    monthly_stats = MonthlyStatsMetric.calculate(canonical_prs, months=args.months)
    print(textwrap.indent(MonthlyStatsMetric.format_table(monthly_stats), "  "))

    monthly_parquet = metrics_dir / f"gain-pr-010-monthly-stats__{run_id}.parquet"
    write_monthly_stats(monthly_stats, monthly_parquet)

    # ── Complete Artifact Summary ───────────────────────────────────────────
    banner("Live Demo Run Complete")
    print(f"  Target Repository    : {repo_slug}")
    print(f"  Raw Directory        : {raw_dir}/")
    print(f"  Canonical Parquet    : {canonical_path}")
    print(f"  Cycle Time Parquet   : {obs_path}")
    print(f"  Cycle Time Summary   : {summary_path}")
    print(f"  Monthly Stats Parquet: {monthly_parquet}")
    print()


if __name__ == "__main__":
    main()
