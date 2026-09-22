from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
import jwt
import structlog

from gain.errors import ConfigurationError, GitHubApiError
from gain.util import parse_utc_datetime

log = structlog.get_logger(__name__)


@runtime_checkable
class GitHubAuthProtocol(Protocol):
    """Protocol defining the interface for GitHub authentication providers."""

    def get_token(self) -> str:
        """Return an active GitHub access token."""
        ...


class GitHubAuth(ABC):
    """Abstract base class and credential provider for GitHub authentication."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls is GitHubAuth:
            token = kwargs.get("token") or (args[0] if args else None)
            if token is not None and isinstance(token, str):
                name = kwargs.get("name", "default_pat")
                org = kwargs.get("org")
                return PATAuth(token=token, name=name, org=org)
        return super().__new__(cls)

    def __init__(
        self,
        token: str = "",
        name: str | None = None,
        org: str | None = None,
        remaining_points: int | None = None,
        reset_time: float | None = None,
        points_used: int = 0,
        acquisitions: int = 0,
    ) -> None:
        self.token = token
        self.name = name or self.__class__.__name__
        self.org = org
        self.remaining_points = remaining_points
        self.reset_time = reset_time
        self.points_used = points_used
        self.acquisitions = acquisitions

    @abstractmethod
    def get_token(self) -> str:
        """Retrieve a valid token for authentication."""
        ...

    def get_auth_header(self) -> str:
        """Return the formatted HTTP Authorization header value."""
        return f"Bearer {self.get_token()}"

    def report_rate_limit(self, remaining: int, reset_epoch: float, used: int = 1) -> None:
        """Update rate-limit metadata from GitHub response headers."""
        self.remaining_points = remaining
        self.reset_time = reset_epoch
        self.points_used += max(0, used)
        log.debug(
            "github_rate_limit_reported",
            provider=self.name,
            remaining=remaining,
            reset_epoch=reset_epoch,
            points_used=self.points_used,
        )

    def is_exhausted(self, now: float | None = None) -> bool:
        """Check whether this provider is currently exhausted (zero quota remaining)."""
        if self.remaining_points is None:
            return False
        current_time = time.time() if now is None else now
        if self.remaining_points <= 0:
            return self.reset_time is None or current_time < self.reset_time
        return False

    def effective_remaining_points(
        self,
        now: float | None = None,
        default_points: int = 5000,
    ) -> int:
        """Calculate effective remaining quota considering reset expiration."""
        current_time = time.time() if now is None else now
        if self.reset_time is not None and current_time >= self.reset_time:
            return default_points
        if self.remaining_points is None:
            return default_points
        return max(0, self.remaining_points)

    def __repr__(self) -> str:
        name = getattr(self, "name", self.__class__.__name__)
        org = getattr(self, "org", None)
        return f"{self.__class__.__name__}(name='{name}', org={org!r}, token='***')"

    def __str__(self) -> str:
        return self.__repr__()


class PATAuth(GitHubAuth):
    """Personal Access Token (PAT) authentication provider."""

    def __init__(
        self,
        token: str,
        name: str | None = None,
        org: str | None = None,
    ) -> None:
        if not token or not token.strip():
            raise ValueError("GitHub PAT token must not be empty.")
        stripped = token.strip()
        display_name = name or (
            f"pat-{stripped[:4]}...{stripped[-4:]}" if len(stripped) >= 8 else "pat-***"
        )
        super().__init__(token=stripped, name=display_name, org=org)

    def get_token(self) -> str:
        return self.token


class GitHubAppAuth(GitHubAuth):
    """GitHub App installation authentication provider using RS256 JWT."""

    def __init__(
        self,
        app_id: str | int,
        private_key_pem: str | Path,
        installation_id: int,
        name: str | None = None,
        org: str | None = None,
        api_url: str = "https://api.github.com",
        jwt_expiration_seconds: int = 540,
        token_expiration_buffer_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = str(app_id).strip()
        if not self.app_id:
            raise ConfigurationError("GitHub App ID cannot be empty")
        self.installation_id = int(installation_id)
        self.api_url = api_url.rstrip("/")
        self.jwt_expiration_seconds = jwt_expiration_seconds
        self.token_expiration_buffer_seconds = token_expiration_buffer_seconds
        self.transport = transport

        display_name = name or f"app-{self.app_id}-inst-{self.installation_id}"
        super().__init__(token="", name=display_name, org=org)

        self._private_key_pem = self._load_private_key(private_key_pem)
        self._cached_token: str | None = None
        self._cached_token_expires_at: float | None = None

    def _load_private_key(self, key_source: str | Path) -> str:
        path: Path | None = None
        if isinstance(key_source, Path):
            path = key_source
        elif isinstance(key_source, str) and "\n" not in key_source:
            candidate = Path(key_source)
            if candidate.is_file():
                path = candidate

        if path is not None:
            if not path.is_file():
                raise ConfigurationError(f"Private key file does not exist: {path}")
            # Security audit: check permissions on POSIX systems
            try:
                mode = path.stat().st_mode & 0o777
                if mode & 0o077 != 0:
                    log.warning(
                        "insecure_private_key_permissions",
                        path=str(path),
                        mode=oct(mode),
                        recommendation="Set file permissions to 0600 (read/write by owner only)",
                    )
            except Exception:
                pass
            return path.read_text(encoding="utf-8")

        if isinstance(key_source, str):
            return key_source
        raise ConfigurationError("Private key must be a PEM string or a Path object")

    def generate_jwt(self, now: float | None = None) -> str:
        """Generate a signed RS256 JWT for GitHub App authentication."""
        current_time = int(time.time() if now is None else now)
        payload: dict[str, Any] = {
            "iat": current_time - 60,
            "exp": current_time + self.jwt_expiration_seconds,
            "iss": self.app_id,
        }
        try:
            encoded = jwt.encode(payload, self._private_key_pem, algorithm="RS256")
            return str(encoded)
        except Exception as exc:
            raise ConfigurationError(f"Failed to generate GitHub App JWT: {exc}") from exc

    def set_installation_token(self, token: str, expires_in_seconds: float = 3600.0) -> None:
        """Manually set or update the cached GitHub App installation access token."""
        self._cached_token = token
        self._cached_token_expires_at = time.time() + expires_in_seconds

    def get_token(self, now: float | None = None) -> str:
        """Return a valid installation access token, refreshing if necessary."""
        current_time = time.time() if now is None else now
        expires_at = self._cached_token_expires_at
        buffer_sec = self.token_expiration_buffer_seconds
        if (
            self._cached_token is not None
            and expires_at is not None
            and current_time < (expires_at - buffer_sec)
        ):
            return self._cached_token
        return self._fetch_installation_token(now=current_time)

    def _fetch_installation_token(self, now: float | None = None) -> str:
        current_time = time.time() if now is None else now
        jwt_token = self.generate_jwt(now=current_time)
        url = f"{self.api_url}/app/installations/{self.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(transport=self.transport, timeout=30.0) as client:
                response = client.post(url, headers=headers)
        except Exception as exc:
            raise GitHubApiError(
                f"Network failure requesting GitHub App installation token: {exc}"
            ) from exc

        if response.status_code not in {200, 201}:
            raise GitHubApiError(
                f"Failed to create GitHub App installation token "
                f"({response.status_code}): {response.text[:500]}"
            )

        data = response.json()
        raw_token = data.get("token")
        if not isinstance(raw_token, str) or not raw_token:
            raise GitHubApiError("GitHub App token response missing valid 'token' field")
        token: str = raw_token

        expires_at_str = data.get("expires_at")
        if expires_at_str and isinstance(expires_at_str, str):
            dt = parse_utc_datetime(expires_at_str)
            self._cached_token_expires_at = dt.timestamp()
        else:
            self._cached_token_expires_at = current_time + 3600.0

        self._cached_token = token
        log.info(
            "github_app_installation_token_acquired",
            app_id=self.app_id,
            installation_id=self.installation_id,
            expires_at=self._cached_token_expires_at,
        )
        return token


__all__ = [
    "GitHubAppAuth",
    "GitHubAuth",
    "GitHubAuthProtocol",
    "PATAuth",
]
