from __future__ import annotations

from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gain.config import Settings
from gain.errors import ConfigurationError, GitHubApiError, RateLimitError
from gain.github.auth import GitHubAppAuth, GitHubAuth, PATAuth
from gain.github.token_pool import GitHubTokenPool


@pytest.fixture
def rsa_private_key_pem() -> str:
    """Generate a 2048-bit RSA private key in PEM format for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@pytest.fixture
def private_key_file(tmp_path: Path, rsa_private_key_pem: str) -> Path:
    """Write private key PEM to a temporary file."""
    key_path = tmp_path / "github_app_private_key.pem"
    key_path.write_text(rsa_private_key_pem, encoding="utf-8")
    return key_path


class TestPATAuth:
    def test_github_auth_base_instantiation(self) -> None:
        auth = GitHubAuth(token="ghp_test_base_token")  # type: ignore[abstract]
        assert isinstance(auth, PATAuth)
        assert auth.get_token() == "ghp_test_base_token"

    def test_token_retrieval(self) -> None:
        auth = PATAuth(token="ghp_testtoken1234567890", org="my-org")
        assert auth.get_token() == "ghp_testtoken1234567890"
        assert auth.org == "my-org"
        assert auth.get_auth_header() == "Bearer ghp_testtoken1234567890"
        assert "ghp_testtoken1234567890" not in str(auth)
        assert "ghp_testtoken1234567890" not in repr(auth)

    def test_empty_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            PATAuth(token="")
        with pytest.raises(ValueError, match="must not be empty"):
            PATAuth(token="   ")

    def test_rate_limit_tracking(self) -> None:
        auth = PATAuth(token="ghp_testtoken12345")
        assert auth.remaining_points is None
        assert auth.reset_time is None
        assert auth.points_used == 0

        auth.report_rate_limit(remaining=4900, reset_epoch=1700000000.0, used=5)
        assert auth.remaining_points == 4900
        assert auth.reset_time == 1700000000.0
        assert auth.points_used == 5

        auth.report_rate_limit(remaining=4890, reset_epoch=1700000000.0, used=10)
        assert auth.remaining_points == 4890
        assert auth.points_used == 15

    def test_exhaustion_detection(self) -> None:
        auth = PATAuth(token="ghp_testtoken12345")
        assert not auth.is_exhausted(now=1000.0)

        auth.report_rate_limit(remaining=0, reset_epoch=2000.0, used=5000)
        # Before reset time -> exhausted
        assert auth.is_exhausted(now=1500.0)
        # At or after reset time -> not exhausted
        assert not auth.is_exhausted(now=2000.0)
        assert not auth.is_exhausted(now=2500.0)


class TestGitHubAppAuth:
    def test_initialization_with_pem_string(self, rsa_private_key_pem: str) -> None:
        auth = GitHubAppAuth(
            app_id="12345",
            private_key_pem=rsa_private_key_pem,
            installation_id=98765,
            org="enterprise-org",
        )
        assert auth.app_id == "12345"
        assert auth.installation_id == 98765
        assert auth.org == "enterprise-org"

    def test_initialization_with_key_path(self, private_key_file: Path) -> None:
        auth = GitHubAppAuth(
            app_id=12345,
            private_key_pem=private_key_file,
            installation_id=98765,
        )
        assert auth.app_id == "12345"

    def test_empty_app_id_raises(self, rsa_private_key_pem: str) -> None:
        with pytest.raises(ConfigurationError, match="GitHub App ID cannot be empty"):
            GitHubAppAuth(
                app_id="",
                private_key_pem=rsa_private_key_pem,
                installation_id=1,
            )

    def test_missing_private_key_file_raises(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "nonexistent.pem"
        with pytest.raises(ConfigurationError, match="Private key file does not exist"):
            GitHubAppAuth(
                app_id="123",
                private_key_pem=missing_file,
                installation_id=1,
            )

    def test_jwt_generation(self, rsa_private_key_pem: str) -> None:
        auth = GitHubAppAuth(
            app_id="4242",
            private_key_pem=rsa_private_key_pem,
            installation_id=12345,
            jwt_expiration_seconds=600,
        )
        fixed_now = 1700000000.0
        signed_jwt = auth.generate_jwt(now=fixed_now)

        # Decode using the corresponding public key
        key = serialization.load_pem_private_key(rsa_private_key_pem.encode("utf-8"), password=None)
        assert isinstance(key, rsa.RSAPrivateKey)
        public_key = key.public_key()
        decoded = jwt.decode(
            signed_jwt, public_key, algorithms=["RS256"], options={"verify_exp": False}
        )

        assert decoded["iss"] == "4242"
        assert decoded["iat"] == 1700000000 - 60
        assert decoded["exp"] == 1700000000 + 600

    def test_mock_token_acquisition_and_caching(self, rsa_private_key_pem: str) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            assert request.method == "POST"
            assert "/app/installations/12345/access_tokens" in str(request.url)
            assert request.headers["authorization"].startswith("Bearer ")
            return httpx.Response(
                201,
                json={
                    "token": "ghs_test_access_token_abc123",
                    "expires_at": "2026-09-21T07:00:00Z",
                },
            )

        transport = httpx.MockTransport(handler)
        auth = GitHubAppAuth(
            app_id="12345",
            private_key_pem=rsa_private_key_pem,
            installation_id=12345,
            transport=transport,
            token_expiration_buffer_seconds=60,
        )

        # First retrieval makes HTTP request
        token = auth.get_token(now=1700000000.0)
        assert token == "ghs_test_access_token_abc123"
        assert request_count == 1

        # Second retrieval within valid expiration uses cached token
        cached_token = auth.get_token(now=1700000010.0)
        assert cached_token == "ghs_test_access_token_abc123"
        assert request_count == 1

    def test_token_refresh_when_expired(self, rsa_private_key_pem: str) -> None:
        tokens = ["ghs_token_first", "ghs_token_second"]
        call_idx = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            token_to_return = tokens[call_idx]
            call_idx += 1
            return httpx.Response(
                201,
                json={
                    "token": token_to_return,
                    "expires_at": "2026-09-21T06:00:00Z",  # Epoch approx 1789970400
                },
            )

        transport = httpx.MockTransport(handler)
        auth = GitHubAppAuth(
            app_id="12345",
            private_key_pem=rsa_private_key_pem,
            installation_id=12345,
            transport=transport,
        )

        # Initial call at t=1000
        first_token = auth.get_token(now=1000.0)
        assert first_token == "ghs_token_first"

        # Advance time past expiration (e.g. year 2027)
        second_token = auth.get_token(now=1800000000.0)
        assert second_token == "ghs_token_second"
        assert call_idx == 2

    def test_token_acquisition_failure_raises_github_api_error(
        self, rsa_private_key_pem: str
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "Resource not accessible by integration"})

        transport = httpx.MockTransport(handler)
        auth = GitHubAppAuth(
            app_id="12345",
            private_key_pem=rsa_private_key_pem,
            installation_id=12345,
            transport=transport,
        )

        with pytest.raises(GitHubApiError, match="Failed to create GitHub App installation token"):
            auth.get_token(now=1000.0)


class TestGitHubTokenPool:
    def test_empty_pool_raises(self) -> None:
        pool = GitHubTokenPool()
        with pytest.raises(
            ConfigurationError, match="No GitHub authentication providers configured"
        ):
            pool.acquire_token()

    def test_token_rotation_least_used_first(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", name="auth-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", name="auth-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        # Both unconsumed: stable tie-break picks A, increments A's acquisitions
        first = pool.acquire_token()
        assert first.name == "auth-a"

        # Second acquisition picks B (B has 0 acquisitions vs A's 1)
        second = pool.acquire_token()
        assert second.name == "auth-b"

        # When points_used are reported: least points_used takes priority
        auth_a.report_rate_limit(remaining=4000, reset_epoch=2000.0, used=20)
        auth_b.report_rate_limit(remaining=4000, reset_epoch=2000.0, used=5)

        # B has fewer points used (5 < 20) with equal remaining points
        third = pool.acquire_token()
        assert third.name == "auth-b"

    def test_healthiest_remaining_quota_priority(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", name="auth-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", name="auth-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        # A has more points remaining even though it used more total points
        auth_a.report_rate_limit(remaining=4500, reset_epoch=2000.0, used=30)
        auth_b.report_rate_limit(remaining=2000, reset_epoch=2000.0, used=5)

        selected = pool.acquire_token(now=1000.0)
        assert selected.name == "auth-a"

    def test_avoidance_of_exhausted_tokens(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", name="auth-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", name="auth-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        # A is completely exhausted before reset epoch
        auth_a.report_rate_limit(remaining=0, reset_epoch=2000.0, used=5000)
        auth_b.report_rate_limit(remaining=300, reset_epoch=2000.0, used=4700)

        # At t=1500, A is exhausted, B is chosen
        selected = pool.acquire_token(now=1500.0)
        assert selected.name == "auth-b"

    def test_reset_time_handling(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", name="auth-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", name="auth-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        # A was exhausted with reset at t=1500
        auth_a.report_rate_limit(remaining=0, reset_epoch=1500.0, used=5000)
        # B has 200 points remaining with reset at t=2500
        auth_b.report_rate_limit(remaining=200, reset_epoch=2500.0, used=4800)

        # At t=1600 (>1500), A's rate limit window has passed!
        # A is no longer exhausted, and its effective quota is refreshed (5000 > 200)
        selected = pool.acquire_token(now=1600.0)
        assert selected.name == "auth-a"

    def test_all_exhausted_raises_rate_limit_error(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", name="auth-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", name="auth-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        auth_a.report_rate_limit(remaining=0, reset_epoch=2000.0, used=5000)
        auth_b.report_rate_limit(remaining=0, reset_epoch=2100.0, used=5000)

        with pytest.raises(RateLimitError, match="All GitHub tokens in pool are rate-limited"):
            pool.acquire_token(now=1500.0)

    def test_org_routing_and_fallback(self) -> None:
        auth_org_x = PATAuth(token="ghp_token_xxxxxxxxxxxx", org="org-x", name="pat-org-x")
        auth_org_y = PATAuth(token="ghp_token_yyyyyyyyyyyy", org="org-y", name="pat-org-y")
        auth_global = PATAuth(token="ghp_token_globalglobal", org=None, name="pat-global")
        pool = GitHubTokenPool([auth_org_x, auth_org_y, auth_global])

        # Specific org match
        assert pool.acquire_token(org="org-x").name == "pat-org-x"
        assert pool.acquire_token(org="org-y").name == "pat-org-y"

        # Org without dedicated token falls back to global token
        assert pool.acquire_token(org="org-z").name == "pat-global"

    def test_org_routing_unmatched_without_global_raises(self) -> None:
        auth_org_x = PATAuth(token="ghp_token_xxxxxxxxxxxx", org="org-x", name="pat-org-x")
        pool = GitHubTokenPool([auth_org_x])

        with pytest.raises(
            ConfigurationError,
            match="No GitHub authentication providers found for organization 'org-z'",
        ):
            pool.acquire_token(org="org-z")

    def test_pool_status_reporting(self) -> None:
        auth_a = PATAuth(token="ghp_token_aaaaaaaaaaaa", org="test-org", name="provider-a")
        auth_b = PATAuth(token="ghp_token_bbbbbbbbbbbb", org=None, name="provider-b")
        pool = GitHubTokenPool([auth_a, auth_b])

        auth_a.report_rate_limit(remaining=3500, reset_epoch=1700000000.0, used=15)

        status = pool.get_pool_status(now=1699999900.0)
        assert len(status) == 2

        status_a = next(item for item in status if item["name"] == "provider-a")
        assert status_a["auth_type"] == "PATAuth"
        assert status_a["org"] == "test-org"
        assert status_a["remaining_points"] == 3500
        assert status_a["reset_time"] == 1700000000.0
        assert status_a["points_used"] == 15
        assert not status_a["is_exhausted"]

        status_b = next(item for item in status if item["name"] == "provider-b")
        assert status_b["remaining_points"] is None
        assert status_b["points_used"] == 0

    def test_pool_report_rate_limit(self) -> None:
        auth = PATAuth(token="ghp_testtoken12345")
        pool = GitHubTokenPool([auth])

        pool.report_rate_limit(auth, remaining=4200, reset_epoch=1700000000.0, used=8)
        assert auth.remaining_points == 4200
        assert auth.reset_time == 1700000000.0
        assert auth.points_used == 8

    def test_from_settings_pat_mode(self) -> None:
        settings = Settings(github_auth_mode="pat", github_token="ghp_fromsettings123")
        pool = GitHubTokenPool.from_settings(settings)
        assert len(pool) == 1
        provider = pool.acquire_token()
        assert isinstance(provider, PATAuth)
        assert provider.get_token() == "ghp_fromsettings123"

    def test_from_settings_app_mode(self, private_key_file: Path) -> None:
        settings = Settings(
            github_auth_mode="app",
            github_app_id="999",
            github_app_private_key_path=private_key_file,
            github_installation_ids=[101, 102],
        )
        pool = GitHubTokenPool.from_settings(settings)
        assert len(pool) == 2
        for provider in pool.providers:
            assert isinstance(provider, GitHubAppAuth)
            assert provider.app_id == "999"


class TestSettingsAppAuthValidation:
    def test_valid_app_mode_settings(self, private_key_file: Path) -> None:
        settings = Settings(
            github_auth_mode="app",
            github_app_id="12345",
            github_app_private_key_path=private_key_file,
            github_installation_ids=[101, 102],
            github_repos=["owner/repo"],
        )
        settings.validate_runtime()
        assert settings.github_auth_mode == "app"
        assert settings.github_installation_ids == [101, 102]

    def test_app_mode_missing_fields_raises_runtime_error(self) -> None:
        settings = Settings(
            github_auth_mode="app",
            github_app_id=None,
            github_repos=["owner/repo"],
        )
        with pytest.raises(ConfigurationError, match="GAIN_GITHUB_APP_ID is required"):
            settings.validate_runtime()

    def test_invalid_auth_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="github_auth_mode must be 'pat' or 'app'"):
            Settings(github_auth_mode="oauth2")

    def test_parse_installation_ids_from_comma_string(self) -> None:
        settings = Settings(github_installation_ids="101, 102, 103")  # type: ignore[arg-type]
        assert settings.github_installation_ids == [101, 102, 103]
