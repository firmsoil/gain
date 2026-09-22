from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import structlog
from pydantic import BaseModel, ConfigDict, field_validator

from gain.config import get_settings
from gain.errors import GitHubApiError, RateLimitError

log = structlog.get_logger(__name__)

VALID_TIERS: frozenset[str] = frozenset({"critical", "standard", "archive"})

REPO_REGISTRY_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "name_with_owner": pl.String,
    "org_id": pl.String,
    "team_id": pl.String,
    "tier": pl.String,
    "last_synced_at": pl.Datetime("us", "UTC"),
    "is_archived": pl.Boolean,
    "default_branch": pl.String,
}


def _normalize_datetime(dt: datetime) -> datetime:
    """Ensure datetime is offset-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class RepoEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name_with_owner: str
    org_id: str
    team_id: str | None = None
    tier: str = "standard"
    last_synced_at: datetime | None = None
    is_archived: bool = False
    default_branch: str = "main"

    @field_validator("name_with_owner")
    @classmethod
    def validate_name_with_owner(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("name_with_owner cannot be empty")
        if trimmed.count("/") != 1 or any(not part for part in trimmed.split("/")):
            raise ValueError(f"Invalid name_with_owner '{v}'; expected 'owner/name' format")
        return trimmed

    @field_validator("org_id")
    @classmethod
    def validate_org_id(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("org_id cannot be empty")
        return trimmed

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        trimmed = v.strip().lower()
        if trimmed not in VALID_TIERS:
            raise ValueError(
                f"Invalid tier '{v}'. Must be one of: {', '.join(sorted(VALID_TIERS))}"
            )
        return trimmed

    @field_validator("last_synced_at")
    @classmethod
    def validate_last_synced_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _normalize_datetime(v)


class RepositoryRegistry:
    """Registry for enterprise repositories tracked by GAIN."""

    def __init__(self, path: Path | str | None = None, *, auto_save: bool = False) -> None:
        if path is not None:
            self.path = Path(path)
        else:
            self.path = get_settings().registry_path
        self.auto_save = auto_save
        self._entries: dict[str, RepoEntry] = {}
        if self.path.exists():
            self.load()

    def add_or_update(self, entry: RepoEntry) -> None:
        """Add or update a repository entry in the registry."""
        key = entry.name_with_owner.strip().lower()
        self._entries[key] = entry
        log.info(
            "repository_registered",
            repo=entry.name_with_owner,
            tier=entry.tier,
            org=entry.org_id,
        )
        if self.auto_save:
            self.save()

    def add_batch(self, entries: list[RepoEntry]) -> None:
        """Batch add or update repository entries."""
        for entry in entries:
            key = entry.name_with_owner.strip().lower()
            self._entries[key] = entry
        log.info("repository_batch_registered", count=len(entries))
        if self.auto_save:
            self.save()

    def get(self, name_with_owner: str) -> RepoEntry | None:
        """Retrieve a repository entry by full owner/name identifier."""
        return self._entries.get(name_with_owner.strip().lower())

    def remove(self, name_with_owner: str) -> bool:
        """Remove a repository from the registry."""
        key = name_with_owner.strip().lower()
        if key in self._entries:
            del self._entries[key]
            log.info("repository_unregistered", repo=name_with_owner)
            if self.auto_save:
                self.save()
            return True
        return False

    def list_all(self) -> list[RepoEntry]:
        """List all registered repositories sorted by name."""
        return sorted(self._entries.values(), key=lambda e: e.name_with_owner.lower())

    def list_by_org(self, org: str) -> list[RepoEntry]:
        """List registered repositories for a given organization."""
        target = org.strip().lower()
        return sorted(
            [e for e in self._entries.values() if e.org_id.strip().lower() == target],
            key=lambda e: e.name_with_owner.lower(),
        )

    def list_by_tier(self, tier: str) -> list[RepoEntry]:
        """List registered repositories with a specified tier."""
        target = tier.strip().lower()
        return sorted(
            [e for e in self._entries.values() if e.tier.strip().lower() == target],
            key=lambda e: e.name_with_owner.lower(),
        )

    def list_stale(self, before: datetime) -> list[RepoEntry]:
        """List repositories not synced since the given timestamp or never synced."""
        cutoff = _normalize_datetime(before)
        stale: list[RepoEntry] = []
        for entry in self._entries.values():
            if entry.last_synced_at is None:
                stale.append(entry)
            else:
                entry_dt = _normalize_datetime(entry.last_synced_at)
                if entry_dt < cutoff:
                    stale.append(entry)
        return sorted(stale, key=lambda e: e.name_with_owner.lower())

    def count(self) -> int:
        """Return total number of registered repositories."""
        return len(self._entries)

    def save(self) -> None:
        """Save the registry contents to Parquet."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [entry.model_dump() for entry in self._entries.values()]
        df = pl.DataFrame(rows, schema=REPO_REGISTRY_SCHEMA)
        df.write_parquet(self.path)
        log.info("repository_registry_saved", path=str(self.path), count=len(self._entries))

    def load(self) -> None:
        """Load registry entries from the Parquet file."""
        if not self.path.exists():
            self._entries.clear()
            return
        df = pl.read_parquet(self.path)
        entries: dict[str, RepoEntry] = {}
        for row in df.to_dicts():
            entry = RepoEntry.model_validate(row)
            entries[entry.name_with_owner.strip().lower()] = entry
        self._entries = entries
        log.info("repository_registry_loaded", path=str(self.path), count=len(self._entries))


class RepositoryDiscovery:
    """Helper to discover repositories from GitHub REST API using pagination."""

    def __init__(
        self,
        token_or_client: str | httpx.Client | None = None,
        org: str | None = None,
        *,
        token: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = "https://api.github.com",
        api_version: str = "2022-11-28",
        page_size: int = 100,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.5,
        retry_max_backoff_seconds: float = 10.0,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_token = token
        resolved_client = client
        if isinstance(token_or_client, str):
            resolved_token = token_or_client
        elif isinstance(token_or_client, httpx.Client):
            resolved_client = token_or_client

        self.token = resolved_token
        self._external_client = resolved_client
        self.org = org
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.page_size = page_size
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.retry_max_backoff_seconds = retry_max_backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.api_version,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request_page(
        self, client: httpx.Client, url: str, params: dict[str, Any]
    ) -> httpx.Response:
        headers = self._build_headers()
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code in {403, 429}:
                    if attempt >= self.max_retries:
                        raise RateLimitError(
                            f"GitHub rate limit reached: status={resp.status_code}"
                        )
                    delay = min(
                        self.base_backoff_seconds * (2**attempt),
                        self.retry_max_backoff_seconds,
                    )
                    log.warning("github_rate_limit_retry", attempt=attempt, delay=delay)
                    time.sleep(delay)
                    continue
                if 500 <= resp.status_code < 600:
                    if attempt >= self.max_retries:
                        raise GitHubApiError(
                            f"GitHub server error {resp.status_code}: {resp.text[:300]}"
                        )
                    delay = min(
                        self.base_backoff_seconds * (2**attempt),
                        self.retry_max_backoff_seconds,
                    )
                    log.warning("github_server_error_retry", attempt=attempt, delay=delay)
                    time.sleep(delay)
                    continue
                if resp.status_code == 404:
                    raise GitHubApiError(f"GitHub organization or endpoint not found: {url}")
                if resp.is_error:
                    raise GitHubApiError(
                        f"GitHub REST API error {resp.status_code}: {resp.text[:300]}"
                    )
                return resp
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise GitHubApiError(f"GitHub network failure after retries: {exc}") from exc
                delay = min(
                    self.base_backoff_seconds * (2**attempt),
                    self.retry_max_backoff_seconds,
                )
                log.warning("github_network_error_retry", attempt=attempt, delay=delay)
                time.sleep(delay)
        raise AssertionError("unreachable")

    def discover(
        self,
        org: str | None = None,
        *,
        tier: str = "standard",
        team_id: str | None = None,
    ) -> list[RepoEntry]:
        """Discover repositories belonging to an organization."""
        target_org = org or self.org
        if not target_org:
            raise ValueError("Organization name must be provided to discover repositories.")

        url = f"{self.base_url}/orgs/{target_org}/repos"
        discovered: list[RepoEntry] = []
        page = 1

        def _fetch_all(client: httpx.Client) -> list[RepoEntry]:
            nonlocal page
            while True:
                params: dict[str, Any] = {"per_page": self.page_size, "page": page}
                resp = self._request_page(client, url, params)
                data = resp.json()
                if not isinstance(data, list):
                    raise GitHubApiError(
                        f"Unexpected response format from GitHub API: "
                        f"expected list, got {type(data)}"
                    )
                if not data:
                    break

                for item in data:
                    full_name = item.get("full_name") or f"{target_org}/{item['name']}"
                    repo_org = (
                        item.get("owner", {}).get("login", target_org)
                        if isinstance(item.get("owner"), dict)
                        else target_org
                    )
                    is_archived = bool(item.get("archived", False))
                    default_branch = str(item.get("default_branch", "main"))
                    discovered.append(
                        RepoEntry(
                            name_with_owner=full_name,
                            org_id=repo_org,
                            team_id=team_id,
                            tier=tier,
                            last_synced_at=None,
                            is_archived=is_archived,
                            default_branch=default_branch,
                        )
                    )

                if "link" in resp.headers:
                    if "next" in resp.links:
                        page += 1
                        continue
                    break
                else:
                    if len(data) < self.page_size:
                        break
                    page += 1

            return discovered

        if self._external_client is not None:
            results = _fetch_all(self._external_client)
        else:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                results = _fetch_all(client)

        log.info(
            "repository_discovery_completed",
            org=target_org,
            count=len(results),
        )
        return results

    def discover_org(
        self,
        org: str,
        *,
        tier: str = "standard",
        team_id: str | None = None,
    ) -> list[RepoEntry]:
        """Alias for discover(org=...)."""
        return self.discover(org=org, tier=tier, team_id=team_id)

    def __call__(
        self,
        org: str | None = None,
        *,
        tier: str = "standard",
        team_id: str | None = None,
    ) -> list[RepoEntry]:
        """Callable interface to discover repositories."""
        return self.discover(org=org, tier=tier, team_id=team_id)

    @classmethod
    def discover_repositories(
        cls,
        org: str,
        token: str | None = None,
        client: httpx.Client | None = None,
        *,
        tier: str = "standard",
        team_id: str | None = None,
        base_url: str = "https://api.github.com",
        transport: httpx.BaseTransport | None = None,
        page_size: int = 100,
    ) -> list[RepoEntry]:
        """Classmethod convenience to discover repositories."""
        instance = cls(
            token=token,
            client=client,
            org=org,
            base_url=base_url,
            transport=transport,
            page_size=page_size,
        )
        return instance.discover(org=org, tier=tier, team_id=team_id)


__all__ = [
    "REPO_REGISTRY_SCHEMA",
    "VALID_TIERS",
    "RepoEntry",
    "RepositoryDiscovery",
    "RepositoryRegistry",
]
