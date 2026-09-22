from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import structlog

from gain.errors import ConfigurationError, RateLimitError
from gain.github.auth import GitHubAppAuth, GitHubAuth, PATAuth

if TYPE_CHECKING:
    from gain.config import Settings

log = structlog.get_logger(__name__)


class GitHubTokenPool:
    """Manages a pool of GitHub authentication providers with health-aware routing."""

    def __init__(self, providers: list[GitHubAuth] | None = None) -> None:
        self._providers: list[GitHubAuth] = list(providers) if providers else []
        self._lock = threading.Lock()

    def add_provider(self, provider: GitHubAuth) -> None:
        """Add an authentication provider to the pool."""
        with self._lock:
            self._providers.append(provider)

    @property
    def providers(self) -> tuple[GitHubAuth, ...]:
        """Return the managed authentication providers."""
        with self._lock:
            return tuple(self._providers)

    def __len__(self) -> int:
        with self._lock:
            return len(self._providers)

    def report_rate_limit(
        self,
        auth: GitHubAuth,
        remaining: int,
        reset_epoch: float,
        used: int = 1,
    ) -> None:
        """Update rate-limit information for a managed provider."""
        with self._lock:
            auth.report_rate_limit(remaining=remaining, reset_epoch=reset_epoch, used=used)

    def acquire_token(
        self,
        org: str | None = None,
        now: float | None = None,
    ) -> GitHubAuth:
        """Route to the provider with the healthiest remaining quota.

        Filter priority:
        1. Exact organization match (or global providers if none match).
        2. Non-exhausted quota (accounting for passed reset times).
        3. Highest remaining quota.
        4. Least points used (tie-break).
        5. Least acquisitions (round-robin tie-break).
        """
        current_time = time.time() if now is None else now

        with self._lock:
            if not self._providers:
                raise ConfigurationError(
                    "No GitHub authentication providers configured in token pool"
                )

            # Org filtering: prefer matching org; fallback to global (org is None)
            if org is not None:
                candidates = [p for p in self._providers if p.org == org]
                if not candidates:
                    candidates = [p for p in self._providers if p.org is None]
                if not candidates:
                    raise ConfigurationError(
                        f"No GitHub authentication providers found for organization '{org}'"
                    )
            else:
                candidates = list(self._providers)

            non_exhausted = [p for p in candidates if not p.is_exhausted(current_time)]
            if not non_exhausted:
                reset_times = [p.reset_time for p in candidates if p.reset_time is not None]
                earliest_reset = min(reset_times) if reset_times else None
                msg = "All GitHub tokens in pool are rate-limited"
                if earliest_reset:
                    wait_sec = max(0.0, earliest_reset - current_time)
                    msg += f"; earliest reset in {wait_sec:.0f}s (epoch {earliest_reset})"
                raise RateLimitError(msg)

            def _priority_key(provider: GitHubAuth) -> tuple[int, int, int]:
                # Negate remaining so higher remaining quota comes first in min()
                eff_remaining = provider.effective_remaining_points(current_time)
                return (-eff_remaining, provider.points_used, provider.acquisitions)

            selected = min(non_exhausted, key=_priority_key)
            selected.acquisitions += 1
            log.debug(
                "github_token_acquired",
                token_name=selected.name,
                points_used=selected.points_used,
                remaining_points=selected.remaining_points,
                acquisitions=selected.acquisitions,
            )
            return selected

    def get_pool_status(self, now: float | None = None) -> list[dict[str, Any]]:
        """Return status overview of all managed tokens in pool."""
        current_time = time.time() if now is None else now
        status: list[dict[str, Any]] = []
        for p in self._providers:
            status.append(
                {
                    "name": p.name,
                    "auth_type": p.__class__.__name__,
                    "org": p.org,
                    "remaining_points": p.remaining_points,
                    "reset_time": p.reset_time,
                    "points_used": p.points_used,
                    "is_exhausted": p.is_exhausted(current_time),
                    "acquisitions": p.acquisitions,
                }
            )
        return status

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubTokenPool:
        """Create and populate a token pool from runtime configuration."""
        pool = cls()
        if settings.github_auth_mode == "app":
            if not settings.github_app_id or not settings.github_app_private_key_path:
                raise ConfigurationError(
                    "github_app_id and github_app_private_key_path are required "
                    "when github_auth_mode='app'"
                )
            if not settings.github_installation_ids:
                raise ConfigurationError(
                    "github_installation_ids cannot be empty when github_auth_mode='app'"
                )
            for inst_id in settings.github_installation_ids:
                pool.add_provider(
                    GitHubAppAuth(
                        app_id=settings.github_app_id,
                        private_key_pem=settings.github_app_private_key_path,
                        installation_id=inst_id,
                    )
                )
        else:
            if not settings.github_token:
                raise ConfigurationError("github_token is required when github_auth_mode='pat'")
            pool.add_provider(PATAuth(token=settings.github_token))
        return pool
