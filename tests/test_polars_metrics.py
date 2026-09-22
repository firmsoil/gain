from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from gain.config import Settings
from gain.metrics.cycle_time import CycleTimeMetric
from gain.model.commit import CanonicalCommit
from gain.model.deployment import (
    CanonicalDeployment,
    DeploymentEnvironment,
    DeploymentStatus,
)
from gain.model.issue import (
    CanonicalIssue,
    IssueStatus,
    IssueType,
    SourceSystem,
)
from gain.model.pr import PullRequest
from gain.services.dora import DORAService
from gain.services.issue_analytics import IssueAnalyticsService
from gain.services.metrics import MetricService
from gain.services.quality import QualityService
from gain.storage.analytics import scan_canonical, write_canonical
from gain.storage.commits import write_canonical_commits
from gain.storage.deployments import write_canonical_deployments
from gain.storage.issues import write_canonical_issues
from gain.storage.partitioning import (
    CANONICAL_COMMIT_SCHEMA,
    CANONICAL_DEPLOYMENT_SCHEMA,
    CANONICAL_ISSUE_SCHEMA,
    CANONICAL_PR_SCHEMA,
    PartitionedWriter,
)
from gain.storage.relationships import RelationshipStore
from tests.factories import make_pr


def test_query_pr_cycle_time_matches_traditional_aggregation(tmp_path: Path) -> None:
    """Verify Polars query_pr_cycle_time produces identical results to traditional calculation."""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=canonical_dir,
        output_dir=tmp_path / "data",
    )

    t0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    prs: list[PullRequest] = []

    # 10 merged PRs with various durations
    for idx in range(1, 11):
        duration_hours = idx * 2.5
        repo = "firmsoil/gain" if idx <= 6 else "firmsoil/analytics"
        prs.append(
            make_pr(
                github_node_id=f"PR_{idx:03d}",
                number=idx,
                repository_name_with_owner=repo,
                created_at=t0 + timedelta(days=idx),
                merged_at=t0 + timedelta(days=idx, hours=duration_hours),
                closed_at=t0 + timedelta(days=idx, hours=duration_hours),
                collected_at=t0 + timedelta(days=idx, hours=duration_hours + 1),
                state="MERGED",
            )
        )

    # 4 unmerged PRs (OPEN)
    for idx in range(11, 15):
        prs.append(
            make_pr(
                github_node_id=f"PR_{idx:03d}",
                number=idx,
                repository_name_with_owner="firmsoil/gain",
                created_at=t0 + timedelta(days=idx),
                merged_at=None,
                closed_at=None,
                collected_at=t0 + timedelta(days=idx, hours=1),
                state="OPEN",
            )
        )

    # 2 closed without merge
    for idx in range(15, 17):
        prs.append(
            make_pr(
                github_node_id=f"PR_{idx:03d}",
                number=idx,
                repository_name_with_owner="firmsoil/gain",
                created_at=t0 + timedelta(days=idx),
                merged_at=None,
                closed_at=t0 + timedelta(days=idx, hours=5),
                collected_at=t0 + timedelta(days=idx, hours=6),
                state="CLOSED",
            )
        )

    write_canonical(prs[:8], canonical_dir / "pull_requests__01.parquet")
    write_canonical(prs[8:], canonical_dir / "pull_requests__02.parquet")

    service = MetricService(settings=settings)

    # A. Full population evaluation
    polars_res = service.query_pr_cycle_time()

    # Traditional observation calculation
    trad_prs = service._load_canonical_prs()
    trad_obs = CycleTimeMetric.observations(trad_prs)
    trad_summary = CycleTimeMetric.summary(trad_obs, total_prs=len(trad_prs))

    assert polars_res.total_evaluated == len(trad_prs)
    assert polars_res.merged_count == len(trad_obs)
    assert polars_res.summary_stats["count"] == trad_summary["count"]
    assert polars_res.summary_stats["merged_count"] == trad_summary["merged_count"]
    assert polars_res.summary_stats["total_evaluated"] == trad_summary["total_evaluated"]
    assert polars_res.summary_stats["p50_seconds"] == pytest.approx(trad_summary["p50_seconds"])
    assert polars_res.summary_stats["p75_seconds"] == pytest.approx(trad_summary["p75_seconds"])
    assert polars_res.summary_stats["p90_seconds"] == pytest.approx(trad_summary["p90_seconds"])
    assert polars_res.summary_stats["p95_seconds"] == pytest.approx(trad_summary["p95_seconds"])
    assert polars_res.summary_stats["mean_seconds"] == pytest.approx(trad_summary["mean_seconds"])

    # Sample comparison
    assert len(polars_res.observations_sample) == min(10, len(trad_obs))
    for p_sample, t_obs in zip(polars_res.observations_sample, trad_obs[:10], strict=True):
        assert p_sample["pr_number"] == t_obs.pr_number
        assert p_sample["node_id"] == t_obs.github_node_id
        assert p_sample["repository"] == t_obs.repository_name_with_owner
        assert p_sample["cycle_time_seconds"] == pytest.approx(t_obs.cycle_time_seconds)

    # B. Predicate pushdown by repository
    repo_res = service.query_pr_cycle_time(repository="firmsoil/gain")
    trad_repo_prs = [p for p in trad_prs if p.repository_name_with_owner == "firmsoil/gain"]
    trad_repo_obs = CycleTimeMetric.observations(trad_repo_prs)
    trad_repo_summary = CycleTimeMetric.summary(trad_repo_obs, total_prs=len(trad_repo_prs))

    assert repo_res.total_evaluated == len(trad_repo_prs)
    assert repo_res.merged_count == len(trad_repo_obs)
    assert repo_res.summary_stats["p50_seconds"] == pytest.approx(trad_repo_summary["p50_seconds"])
    assert repo_res.summary_stats["mean_seconds"] == pytest.approx(
        trad_repo_summary["mean_seconds"]
    )

    # C. Predicate pushdown by date range
    start_filter = t0 + timedelta(days=3)
    end_filter = t0 + timedelta(days=7)
    date_res = service.query_pr_cycle_time(start_date=start_filter, end_date=end_filter)
    trad_date_prs = [p for p in trad_prs if start_filter <= p.created_at <= end_filter]
    trad_date_obs = CycleTimeMetric.observations(trad_date_prs)
    trad_date_summary = CycleTimeMetric.summary(trad_date_obs, total_prs=len(trad_date_prs))

    assert date_res.total_evaluated == len(trad_date_prs)
    assert date_res.merged_count == len(trad_date_obs)
    assert date_res.summary_stats["p50_seconds"] == pytest.approx(trad_date_summary["p50_seconds"])


def test_scan_canonical_empty_and_missing_directory(tmp_path: Path) -> None:
    """Verify scan_canonical handles missing, empty, or unpartitioned directories gracefully."""
    nonexistent = tmp_path / "does_not_exist"

    # 1. Pull requests on nonexistent path
    lf_pr = scan_canonical(nonexistent, entity_type="pull_request")
    assert isinstance(lf_pr, pl.LazyFrame)
    df_pr = lf_pr.collect()
    assert len(df_pr) == 0
    for col in CANONICAL_PR_SCHEMA:
        assert col in df_pr.columns
    # Predicate filtering on empty schema LazyFrame does not fail
    filtered_pr = lf_pr.filter(pl.col("repository_name_with_owner") == "firmsoil/gain").collect()
    assert len(filtered_pr) == 0

    # 2. Deployments on nonexistent path
    lf_dep = scan_canonical(nonexistent, entity_type="deployment")
    df_dep = lf_dep.collect()
    assert len(df_dep) == 0
    for col in CANONICAL_DEPLOYMENT_SCHEMA:
        assert col in df_dep.columns
    filtered_dep = lf_dep.filter(pl.col("environment") == "production").collect()
    assert len(filtered_dep) == 0

    # 3. Commits on nonexistent path
    lf_commit = scan_canonical(nonexistent, entity_type="commit")
    df_commit = lf_commit.collect()
    assert len(df_commit) == 0
    for col in CANONICAL_COMMIT_SCHEMA:
        assert col in df_commit.columns

    # 4. Issues on nonexistent path
    lf_issue = scan_canonical(nonexistent, entity_type="issue")
    df_issue = lf_issue.collect()
    assert len(df_issue) == 0
    for col in CANONICAL_ISSUE_SCHEMA:
        assert col in df_issue.columns

    # 5. Empty directory that exists
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    lf_empty = scan_canonical(empty_dir, entity_type="pull_request")
    assert len(lf_empty.collect()) == 0

    # 6. Directory with unrelated non-parquet files
    unrelated_dir = tmp_path / "unrelated"
    unrelated_dir.mkdir()
    (unrelated_dir / "notes.txt").write_text("not parquet", encoding="utf-8")
    (unrelated_dir / "data.json").write_text("{}", encoding="utf-8")
    lf_unrelated = scan_canonical(unrelated_dir, entity_type="pull_request")
    assert len(lf_unrelated.collect()) == 0


def test_scan_canonical_partitioned_directory(tmp_path: Path) -> None:
    """Verify scan_canonical reads Hive-partitioned directory layouts with partition pushdown."""
    canonical_dir = tmp_path / "canonical"
    writer = PartitionedWriter(canonical_dir)

    t1 = datetime(2026, 5, 10, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)

    pr1 = make_pr(
        github_node_id="PR_P1",
        number=1,
        repository_name_with_owner="firmsoil/gain",
        created_at=t1,
        merged_at=t1 + timedelta(hours=4),
    )
    pr2 = make_pr(
        github_node_id="PR_P2",
        number=2,
        repository_name_with_owner="firmsoil/gain",
        created_at=t2,
        merged_at=t2 + timedelta(hours=8),
    )
    pr3 = make_pr(
        github_node_id="PR_P3",
        number=3,
        repository_name_with_owner="external/repo",
        created_at=t2,
        merged_at=t2 + timedelta(hours=2),
    )

    writer.write_canonical_prs([pr1, pr2, pr3])

    # Scan partitioned dataset
    lf = scan_canonical(canonical_dir, entity_type="pull_request")
    df = lf.collect()
    assert len(df) == 3

    # Predicate pushdown on repository
    filtered_lf = lf.filter(pl.col("repository_name_with_owner") == "firmsoil/gain")
    assert len(filtered_lf.collect()) == 2

    # MetricService should seamlessly execute cycle time query on partitioned layout
    settings = Settings(canonical_dir=canonical_dir, output_dir=tmp_path / "data")
    service = MetricService(settings=settings)
    summary = service.query_pr_cycle_time(repository="firmsoil/gain")
    assert summary.total_evaluated == 2
    assert summary.merged_count == 2
    # p50 of 4h (14400s) and 8h (28800s) -> 21600.0s
    assert summary.summary_stats["p50_seconds"] == 21600.0


def test_performance_and_memory_efficiency(tmp_path: Path) -> None:
    """Verify performance and memory efficiency when scanning canonical PR datasets."""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    settings = Settings(canonical_dir=canonical_dir, output_dir=tmp_path / "data")

    # Generate 3,000 PRs partitioned across 3 parquet files
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    for chunk in range(3):
        chunk_prs: list[PullRequest] = []
        for i in range(1000):
            idx = chunk * 1000 + i + 1
            repo = "firmsoil/gain" if idx % 2 == 0 else "other/repo"
            chunk_prs.append(
                make_pr(
                    github_node_id=f"PR_PERF_{idx}",
                    number=idx,
                    repository_name_with_owner=repo,
                    created_at=t0 + timedelta(hours=idx),
                    merged_at=t0 + timedelta(hours=idx + 3),
                    closed_at=t0 + timedelta(hours=idx + 3),
                    state="MERGED",
                )
            )
        write_canonical(chunk_prs, canonical_dir / f"pull_requests__chunk_{chunk}.parquet")

    service = MetricService(settings=settings)

    # Benchmark query execution
    start_time = time.perf_counter()
    result = service.query_pr_cycle_time(
        repository="firmsoil/gain",
        start_date=t0 + timedelta(hours=500),
        end_date=t0 + timedelta(hours=2500),
    )
    elapsed = time.perf_counter() - start_time

    assert result.total_evaluated > 0
    assert result.merged_count == result.total_evaluated
    assert result.summary_stats["p50_seconds"] == pytest.approx(10800.0)  # 3 hours = 10800.0s
    # Should execute in well under 1 second thanks to Polars columnar scanning
    assert elapsed < 1.0


def test_quality_service_polars_native_evaluation(tmp_path: Path) -> None:
    """Verify QualityService executes streaming Polars validations correctly."""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    settings = Settings(canonical_dir=canonical_dir)
    service = QualityService(settings=settings)

    # 1. Nonexistent directory returns NO_DATA
    missing_service = QualityService(settings=Settings(canonical_dir=tmp_path / "not_there"))
    res_missing = missing_service.get_dataset_quality()
    assert res_missing.source_status == "NO_DATA"
    assert res_missing.population_sufficiency == "INSUFFICIENT"

    # 2. Empty directory returns EMPTY_DATASET
    res_empty = service.get_dataset_quality()
    assert res_empty.source_status == "EMPTY_DATASET"
    assert res_empty.total_records == 0

    # 3. Healthy dataset with valid PRs
    t0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    healthy_prs = [
        make_pr(
            github_node_id=f"PR_{i}",
            number=i,
            created_at=t0,
            merged_at=t0 + timedelta(hours=2),
            closed_at=t0 + timedelta(hours=2),
        )
        for i in range(1, 35)
    ]
    write_canonical(healthy_prs, canonical_dir / "pull_requests__01.parquet")

    res_healthy = service.get_dataset_quality()
    assert res_healthy.total_records == 34
    assert res_healthy.valid_records == 34
    assert res_healthy.source_status == "HEALTHY"
    assert res_healthy.population_sufficiency == "SUFFICIENT"
    assert res_healthy.completeness_score == 1.0
    assert res_healthy.validity_score == 1.0
    assert len(res_healthy.quality_flags) == 0

    # 4. Dataset with data quality issues
    problematic_prs = [
        make_pr(  # Duplicate ID
            github_node_id="PR_1",
            number=99,
            created_at=t0,
            merged_at=t0 + timedelta(hours=1),
            closed_at=t0 + timedelta(hours=1),
        ),
        make_pr(  # Invalid closed_at preceding created_at
            github_node_id="PR_INV_CLOSE",
            number=100,
            created_at=t0,
            merged_at=t0 - timedelta(hours=2),
            closed_at=t0 - timedelta(hours=2),
        ),
        make_pr(  # Merged without closed_at
            github_node_id="PR_WARN",
            number=101,
            created_at=t0,
            merged_at=t0 + timedelta(hours=1),
            closed_at=None,
        ),
    ]
    write_canonical(problematic_prs, canonical_dir / "pull_requests__02.parquet")

    res_issues = service.get_dataset_quality()
    assert res_issues.source_status == "WARNING"
    assert res_issues.total_records == 37
    assert res_issues.valid_records < res_issues.total_records
    assert len(res_issues.quality_flags) > 0
    flag_codes = {f["code"] for f in res_issues.quality_flags}
    assert "DUPLICATE_NODE_ID" in flag_codes
    assert "INVALID_CLOSED_AT" in flag_codes
    assert "MERGED_WITHOUT_CLOSED_AT" in flag_codes


def test_dora_service_polars_lazy_filtering(tmp_path: Path) -> None:
    """Verify DORAService calculates delivery metrics efficiently via Polars pushdown."""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    settings = Settings(canonical_dir=canonical_dir)

    t0_commit = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)
    t0_deploy = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)  # 2h lead time = 7200s

    commits = [
        CanonicalCommit(
            sha="sha_dora_01",
            repository_name_with_owner="firmsoil/gain",
            author_name="Alice",
            committed_at=t0_commit,
            message="Feature",
            collected_at=t0_commit,
            ingestion_run_id="run-1",
        ),
        CanonicalCommit(
            sha="sha_other_repo",
            repository_name_with_owner="other/repo",
            author_name="Bob",
            committed_at=t0_commit,
            message="Other feature",
            collected_at=t0_commit,
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_commits(commits, canonical_dir / "commits__01.parquet")

    deployments = [
        CanonicalDeployment(
            id="dep-1",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.SUCCESS,
            commit_sha="sha_dora_01",
            started_at=t0_deploy - timedelta(minutes=5),
            completed_at=t0_deploy,
            collected_at=t0_deploy,
            ingestion_run_id="run-1",
        ),
        CanonicalDeployment(
            id="dep-staging",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.STAGING,
            status=DeploymentStatus.SUCCESS,
            commit_sha="sha_dora_01",
            started_at=t0_deploy,
            completed_at=t0_deploy + timedelta(minutes=10),
            collected_at=t0_deploy,
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_deployments(deployments, canonical_dir / "deployments__01.parquet")

    dora_service = DORAService(settings=settings)
    dora_res = dora_service.calculate_dora(repository="firmsoil/gain", environment="production")

    assert dora_res.status == "available"
    assert dora_res.change_lead_time.status == "available"
    assert dora_res.change_lead_time.value == 7200.0
    assert dora_res.change_fail_rate.value == 0.0


def test_issue_analytics_traceability_fast_lookup(tmp_path: Path) -> None:
    """Verify IssueAnalyticsService and RelationshipStore fast lookup."""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    settings = Settings(
        canonical_dir=canonical_dir,
        indexes_dir=tmp_path / "indexes",
        output_dir=tmp_path / "data",
    )

    t0 = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
    t_res = datetime(2026, 4, 1, 13, 0, 0, tzinfo=UTC)  # 4h = 14400s

    issues = [
        CanonicalIssue(
            id="jira:ENG-10",
            key="ENG-10",
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="Explicit link issue",
            issue_type=IssueType.STORY,
            status=IssueStatus.DONE,
            created_at=t0,
            updated_at=t_res,
            resolved_at=t_res,
            linked_pr_keys=["201"],
            collected_at=t_res,
            ingestion_run_id="run-1",
        ),
        CanonicalIssue(
            id="jira:ENG-202",
            key="202",  # numeric key matches PR 202
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="Numeric match issue",
            issue_type=IssueType.BUG,
            status=IssueStatus.DONE,
            created_at=t0,
            updated_at=t_res,
            resolved_at=t_res,
            linked_pr_keys=[],
            collected_at=t_res,
            ingestion_run_id="run-1",
        ),
        CanonicalIssue(
            id="jira:ENG-30",
            key="ENG-30",
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="RelStore link issue",
            issue_type=IssueType.TASK,
            status=IssueStatus.DONE,
            created_at=t0,
            updated_at=t_res,
            resolved_at=t_res,
            linked_pr_keys=[],
            collected_at=t_res,
            ingestion_run_id="run-1",
        ),
        CanonicalIssue(
            id="jira:ENG-40",
            key="ENG-40",
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="Unlinked issue",
            issue_type=IssueType.TASK,
            status=IssueStatus.OPEN,
            created_at=t0,
            updated_at=t0,
            resolved_at=None,
            linked_pr_keys=[],
            collected_at=t0,
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_issues(issues, canonical_dir / "issues__jira__01.parquet")

    prs = [
        make_pr(
            github_node_id="PR_201",
            number=201,
            repository_name_with_owner="firmsoil/gain",
        ),
        make_pr(
            github_node_id="PR_202",
            number=202,
            repository_name_with_owner="firmsoil/gain",
        ),
        make_pr(
            github_node_id="PR_203",
            number=203,
            repository_name_with_owner="firmsoil/gain",
        ),
    ]
    write_canonical(prs, canonical_dir / "pull_requests__01.parquet")

    # Set up RelationshipStore with link for ENG-30
    rel_store = RelationshipStore(storage_dir=settings.indexes_dir)
    rel_store.record_pr_issue_link(
        repository="firmsoil/gain",
        pr_number=203,
        issue_key="ENG-30",
    )

    issue_service = IssueAnalyticsService(settings=settings, relationship_store=rel_store)
    analytics_res = issue_service.analyze_issues(project_key="ENG", repository="firmsoil/gain")

    assert analytics_res.status == "available"
    assert analytics_res.total_issues == 4
    assert analytics_res.resolved_issues == 3
    assert analytics_res.open_issues == 1
    # 3 issues linked (ENG-10 via explicit link, 202 via number,
    # ENG-30 via RelationshipStore) out of 4 = 75.0%
    assert analytics_res.linked_prs_count == 3
    assert analytics_res.traceability_rate == 75.0
    assert analytics_res.cycle_time_stats["p50_seconds"] == 14400.0
