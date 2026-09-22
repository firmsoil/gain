from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings, set_settings_override
from gain.errors import GitHubApiError, RateLimitError
from gain.registry import (
    REPO_REGISTRY_SCHEMA,
    VALID_TIERS,
    RepoEntry,
    RepositoryDiscovery,
    RepositoryRegistry,
)

runner = CliRunner()


# ============================================================================
# 1. RepoEntry Tests: Validation and Immutability
# ============================================================================


def test_repo_entry_defaults() -> None:
    entry = RepoEntry(name_with_owner="firmsoil/gain", org_id="firmsoil")
    assert entry.name_with_owner == "firmsoil/gain"
    assert entry.org_id == "firmsoil"
    assert entry.team_id is None
    assert entry.tier == "standard"
    assert entry.last_synced_at is None
    assert entry.is_archived is False
    assert entry.default_branch == "main"


def test_repo_registry_schema_fields() -> None:
    assert "name_with_owner" in REPO_REGISTRY_SCHEMA
    assert "tier" in REPO_REGISTRY_SCHEMA
    assert "last_synced_at" in REPO_REGISTRY_SCHEMA


def test_repo_entry_immutability() -> None:
    entry = RepoEntry(name_with_owner="firmsoil/gain", org_id="firmsoil")
    with pytest.raises(ValidationError):
        entry.tier = "critical"


def test_repo_entry_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        RepoEntry(
            name_with_owner="firmsoil/gain",
            org_id="firmsoil",
            extra_field="disallowed",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    "invalid_name",
    ["", "   ", "no-slash", "/leading-slash", "trailing-slash/", "a/b/c"],
)
def test_repo_entry_invalid_name_with_owner(invalid_name: str) -> None:
    with pytest.raises(ValidationError):
        RepoEntry(name_with_owner=invalid_name, org_id="firmsoil")


def test_repo_entry_empty_org_id() -> None:
    with pytest.raises(ValidationError):
        RepoEntry(name_with_owner="firmsoil/gain", org_id="   ")


@pytest.mark.parametrize("tier", list(VALID_TIERS))
def test_repo_entry_valid_tiers(tier: str) -> None:
    entry = RepoEntry(name_with_owner="firmsoil/gain", org_id="firmsoil", tier=tier)
    assert entry.tier == tier


def test_repo_entry_invalid_tier() -> None:
    with pytest.raises(ValidationError):
        RepoEntry(name_with_owner="firmsoil/gain", org_id="firmsoil", tier="super-priority")


def test_repo_entry_datetime_normalization() -> None:
    naive_dt = datetime(2026, 9, 21, 10, 0, 0)
    entry = RepoEntry(
        name_with_owner="firmsoil/gain",
        org_id="firmsoil",
        last_synced_at=naive_dt,
    )
    assert entry.last_synced_at is not None
    assert entry.last_synced_at.tzinfo == UTC
    assert entry.last_synced_at.hour == 10


# ============================================================================
# 2. RepositoryRegistry Tests: CRUD, Filtering, Stale Detection, Persistence
# ============================================================================


def test_registry_crud(tmp_path: Path) -> None:
    reg_path = tmp_path / "registry.parquet"
    registry = RepositoryRegistry(reg_path)
    assert registry.count() == 0
    assert registry.list_all() == []

    entry1 = RepoEntry(
        name_with_owner="org1/repo1",
        org_id="org1",
        tier="critical",
        default_branch="master",
    )
    registry.add_or_update(entry1)
    assert registry.count() == 1
    assert registry.get("org1/repo1") == entry1
    # Case-insensitive lookup
    assert registry.get("ORG1/REPO1") == entry1
    assert registry.get("nonexistent/repo") is None

    # Update existing entry
    entry1_updated = RepoEntry(
        name_with_owner="org1/repo1",
        org_id="org1",
        tier="standard",
        default_branch="main",
    )
    registry.add_or_update(entry1_updated)
    assert registry.count() == 1
    retrieved = registry.get("org1/repo1")
    assert retrieved is not None
    assert retrieved.tier == "standard"
    assert retrieved.default_branch == "main"

    # Remove
    assert registry.remove("org1/repo1") is True
    assert registry.count() == 0
    assert registry.remove("org1/repo1") is False


def test_registry_batch_add(tmp_path: Path) -> None:
    reg_path = tmp_path / "registry.parquet"
    registry = RepositoryRegistry(reg_path)

    batch = [RepoEntry(name_with_owner=f"org/repo-{i}", org_id="org") for i in range(5)]
    registry.add_batch(batch)
    assert registry.count() == 5
    assert len(registry.list_all()) == 5


def test_registry_multi_org_and_tier_filtering(tmp_path: Path) -> None:
    reg_path = tmp_path / "registry.parquet"
    registry = RepositoryRegistry(reg_path)

    e1 = RepoEntry(name_with_owner="alpha/service-a", org_id="alpha", tier="critical")
    e2 = RepoEntry(name_with_owner="alpha/service-b", org_id="alpha", tier="standard")
    e3 = RepoEntry(name_with_owner="beta/service-c", org_id="beta", tier="critical")
    e4 = RepoEntry(name_with_owner="gamma/service-d", org_id="gamma", tier="archive")

    registry.add_batch([e1, e2, e3, e4])
    assert registry.count() == 4

    # Filter by org
    alpha_repos = registry.list_by_org("alpha")
    assert len(alpha_repos) == 2
    assert [r.name_with_owner for r in alpha_repos] == ["alpha/service-a", "alpha/service-b"]

    beta_repos = registry.list_by_org("BETA")  # case-insensitive
    assert len(beta_repos) == 1
    assert beta_repos[0].name_with_owner == "beta/service-c"

    assert registry.list_by_org("unknown") == []

    # Filter by tier
    critical_repos = registry.list_by_tier("critical")
    assert len(critical_repos) == 2
    assert [r.name_with_owner for r in critical_repos] == ["alpha/service-a", "beta/service-c"]

    archive_repos = registry.list_by_tier("ARCHIVE")  # case-insensitive
    assert len(archive_repos) == 1
    assert archive_repos[0].name_with_owner == "gamma/service-d"


def test_registry_stale_detection(tmp_path: Path) -> None:
    reg_path = tmp_path / "registry.parquet"
    registry = RepositoryRegistry(reg_path)

    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
    cutoff = now - timedelta(days=7)

    # 1. Never synced -> stale
    e_never = RepoEntry(name_with_owner="org/never-synced", org_id="org", last_synced_at=None)
    # 2. Synced 10 days ago -> stale
    e_old = RepoEntry(
        name_with_owner="org/old-synced",
        org_id="org",
        last_synced_at=cutoff - timedelta(days=3),
    )
    # 3. Synced 2 days ago -> fresh
    e_fresh = RepoEntry(
        name_with_owner="org/fresh-synced",
        org_id="org",
        last_synced_at=cutoff + timedelta(days=5),
    )

    registry.add_batch([e_never, e_old, e_fresh])

    stale = registry.list_stale(before=cutoff)
    assert len(stale) == 2
    stale_names = [e.name_with_owner for e in stale]
    assert "org/never-synced" in stale_names
    assert "org/old-synced" in stale_names
    assert "org/fresh-synced" not in stale_names

    # Test with naive datetime cutoff
    naive_cutoff = datetime(2026, 9, 14, 12, 0, 0)
    stale_naive = registry.list_stale(before=naive_cutoff)
    assert len(stale_naive) == 2


def test_registry_persistence_across_reloads(tmp_path: Path) -> None:
    reg_path = tmp_path / "subdir" / "registry.parquet"
    reg1 = RepositoryRegistry(reg_path)

    sync_time = datetime(2026, 9, 20, 8, 30, 0, tzinfo=UTC)
    entries = [
        RepoEntry(
            name_with_owner="firmsoil/gain",
            org_id="firmsoil",
            tier="critical",
            last_synced_at=sync_time,
            is_archived=False,
            default_branch="main",
        ),
        RepoEntry(
            name_with_owner="firmsoil/legacy-tool",
            org_id="firmsoil",
            tier="archive",
            last_synced_at=None,
            is_archived=True,
            default_branch="master",
        ),
    ]
    reg1.add_batch(entries)
    reg1.save()
    assert reg_path.exists()

    # Load in new registry instance
    reg2 = RepositoryRegistry(reg_path)
    assert reg2.count() == 2
    assert reg2.get("firmsoil/gain") == entries[0]
    assert reg2.get("firmsoil/legacy-tool") == entries[1]

    # Test load() reloads after clearing
    reg2._entries.clear()
    assert reg2.count() == 0
    reg2.load()
    assert reg2.count() == 2


def test_registry_empty_persistence(tmp_path: Path) -> None:
    reg_path = tmp_path / "empty_registry.parquet"
    reg = RepositoryRegistry(reg_path)
    reg.save()
    assert reg_path.exists()

    reloaded = RepositoryRegistry(reg_path)
    assert reloaded.count() == 0
    assert reloaded.list_all() == []


# ============================================================================
# 3. RepositoryDiscovery Tests: Mock HTTP Transport & Pagination
# ============================================================================


def test_repository_discovery_single_page() -> None:
    repos_payload = [
        {
            "id": 101,
            "name": "core-engine",
            "full_name": "acmeco/core-engine",
            "owner": {"login": "acmeco"},
            "archived": False,
            "default_branch": "main",
        },
        {
            "id": 102,
            "name": "docs-site",
            "full_name": "acmeco/docs-site",
            "owner": {"login": "acmeco"},
            "archived": True,
            "default_branch": "trunk",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/orgs/acmeco/repos"
        assert request.headers["authorization"] == "Bearer test-pat"
        assert request.headers["x-github-api-version"] == "2022-11-28"
        return httpx.Response(200, json=repos_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(client=client, token="test-pat")
    results = discovery.discover("acmeco", tier="critical", team_id="platform-team")

    assert len(results) == 2
    assert results[0].name_with_owner == "acmeco/core-engine"
    assert results[0].org_id == "acmeco"
    assert results[0].tier == "critical"
    assert results[0].team_id == "platform-team"
    assert results[0].is_archived is False
    assert results[0].default_branch == "main"
    assert results[0].last_synced_at is None

    assert results[1].name_with_owner == "acmeco/docs-site"
    assert results[1].is_archived is True
    assert results[1].default_branch == "trunk"


def test_repository_discovery_pagination_with_link_headers() -> None:
    page1_payload = [
        {"name": "repo-1", "full_name": "acme/repo-1", "archived": False},
        {"name": "repo-2", "full_name": "acme/repo-2", "archived": False},
    ]
    page2_payload = [
        {"name": "repo-3", "full_name": "acme/repo-3", "archived": False},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            headers = {
                "Link": '<https://api.github.com/orgs/acme/repos?page=2&per_page=2>; rel="next"'
            }
            return httpx.Response(200, json=page1_payload, headers=headers)
        if page == "2":
            headers = {
                "Link": '<https://api.github.com/orgs/acme/repos?page=1&per_page=2>; rel="prev"'
            }
            return httpx.Response(200, json=page2_payload, headers=headers)
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(client=client, page_size=2)
    results = discovery.discover("acme")

    assert len(results) == 3
    assert [r.name_with_owner for r in results] == [
        "acme/repo-1",
        "acme/repo-2",
        "acme/repo-3",
    ]


def test_repository_discovery_pagination_length_based() -> None:
    page1_payload = [
        {"name": "repo-1", "full_name": "acme/repo-1"},
        {"name": "repo-2", "full_name": "acme/repo-2"},
    ]
    page2_payload = [
        {"name": "repo-3", "full_name": "acme/repo-3"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(200, json=page1_payload)
        if page == "2":
            return httpx.Response(200, json=page2_payload)
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(client=client, page_size=2)
    results = discovery.discover("acme")
    assert len(results) == 3


def test_repository_discovery_retry_on_rate_limit() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="Rate limit exceeded")
        return httpx.Response(
            200,
            json=[{"name": "recovered-repo", "full_name": "acme/recovered-repo"}],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(
        client=client,
        max_retries=2,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.01,
    )
    results = discovery.discover("acme")
    assert len(results) == 1
    assert results[0].name_with_owner == "acme/recovered-repo"
    assert calls == 2


def test_repository_discovery_rate_limit_exceeded() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(
        client=client,
        max_retries=1,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.001,
    )
    with pytest.raises(RateLimitError):
        discovery.discover("acme")


def test_repository_discovery_not_found_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovery = RepositoryDiscovery(client=client)
    with pytest.raises(GitHubApiError):
        discovery.discover("nonexistent-org")


def test_repository_discovery_missing_org() -> None:
    discovery = RepositoryDiscovery()
    with pytest.raises(ValueError, match="Organization name must be provided"):
        discovery.discover()


def test_repository_discovery_convenience_interfaces() -> None:
    payload = [{"name": "repo-1", "full_name": "acme/repo-1"}]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    # Test classmethod discover_repositories
    res1 = RepositoryDiscovery.discover_repositories("acme", client=client)
    assert len(res1) == 1

    # Test callable instance
    discovery = RepositoryDiscovery(client=client)
    res2 = discovery("acme")
    assert len(res2) == 1

    # Test discover_org
    res3 = discovery.discover_org("acme")
    assert len(res3) == 1


# ============================================================================
# 4. CLI Subcommand Tests: list, add
# ============================================================================


def test_cli_registry_add_and_list(tmp_path: Path) -> None:
    reg_path = tmp_path / "cli_registry.parquet"
    settings = Settings(registry_path=reg_path)
    set_settings_override(settings)
    try:
        # 1. Initially empty
        list_res = runner.invoke(app, ["registry", "list"])
        assert list_res.exit_code == 0
        assert "No repositories found" in list_res.stdout

        # 2. Add repo with owner/name format
        add_res = runner.invoke(app, ["registry", "add", "firmsoil/gain", "--tier", "critical"])
        assert add_res.exit_code == 0
        assert "Added repository firmsoil/gain" in add_res.stdout
        assert "tier=critical" in add_res.stdout

        # 3. Add repo with explicit --org option
        add_res2 = runner.invoke(
            app, ["registry", "add", "data-pipeline", "--org", "firmsoil", "--tier", "standard"]
        )
        assert add_res2.exit_code == 0
        assert "Added repository firmsoil/data-pipeline" in add_res2.stdout

        # 4. Add repo for another org
        add_res3 = runner.invoke(app, ["registry", "add", "external/adapter", "--tier", "archive"])
        assert add_res3.exit_code == 0

        # 5. List all
        list_all = runner.invoke(app, ["registry", "list"])
        assert list_all.exit_code == 0
        assert "Repositories (3):" in list_all.stdout
        assert "firmsoil/gain" in list_all.stdout
        assert "firmsoil/data-pipeline" in list_all.stdout
        assert "external/adapter" in list_all.stdout

        # 6. Filter by org
        list_org = runner.invoke(app, ["registry", "list", "--org", "firmsoil"])
        assert list_org.exit_code == 0
        assert "Repositories (2):" in list_org.stdout
        assert "external/adapter" not in list_org.stdout

        # 7. Filter by tier
        list_tier = runner.invoke(app, ["registry", "list", "--tier", "critical"])
        assert list_tier.exit_code == 0
        assert "Repositories (1):" in list_tier.stdout
        assert "firmsoil/gain" in list_tier.stdout

        # 8. List JSON output
        list_json = runner.invoke(app, ["registry", "list", "--json"])
        assert list_json.exit_code == 0
        data = json.loads(list_json.stdout)
        assert isinstance(data, list)
        assert len(data) == 3
    finally:
        set_settings_override(None)


def test_cli_registry_add_missing_org(tmp_path: Path) -> None:
    reg_path = tmp_path / "cli_registry.parquet"
    settings = Settings(registry_path=reg_path)
    set_settings_override(settings)
    try:
        # Name without slash and without --org should fail
        res = runner.invoke(app, ["registry", "add", "bare-repo-name"])
        assert res.exit_code != 0
        assert "Organization must be specified" in res.output
    finally:
        set_settings_override(None)
