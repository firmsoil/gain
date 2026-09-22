from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from gain.model.pr import PullRequest

log = structlog.get_logger(__name__)

DEFAULT_ANON_PREFIX = "anon_"
_EPHEMERAL_SALT: bytes | None = None


def _get_ephemeral_salt() -> bytes:
    global _EPHEMERAL_SALT
    if _EPHEMERAL_SALT is None:
        log.warning(
            "privacy_ephemeral_salt_generated",
            warning="No salt provided; generated random 256-bit ephemeral salt.",
        )
        _EPHEMERAL_SALT = secrets.token_bytes(32)
    return _EPHEMERAL_SALT


def pseudonymize_author(login: str | None, salt: str = "") -> str | None:
    """Generate a deterministic, salted HMAC-SHA256 pseudonym for a GitHub author login.

    If login is None or empty, returns None.
    If login is a known bot suffix (e.g. '[bot]'), preserves the bot identity
    tag while hashing the prefix.
    """
    if not login:
        return None

    cleaned = login.strip()
    if not cleaned:
        return None

    is_bot = cleaned.endswith("[bot]")
    base_login = cleaned[:-5] if is_bot else cleaned

    # HMAC-SHA256 with UTF-8 encoding
    key = salt.encode("utf-8") if salt else _get_ephemeral_salt()
    msg = base_login.lower().encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]

    pseudonym = f"{DEFAULT_ANON_PREFIX}{digest}"
    if is_bot:
        pseudonym = f"{pseudonym}[bot]"

    return pseudonym


def anonymize_pull_request(pr: PullRequest, salt: str = "") -> PullRequest:
    """Return a deep copy of the PullRequest domain model with author login pseudonymized."""
    if not pr.author_login:
        return pr

    anon_login = pseudonymize_author(pr.author_login, salt=salt)
    return pr.model_copy(update={"author_login": anon_login})


def anonymize_dataset(prs: list[PullRequest], salt: str = "") -> list[PullRequest]:
    """Anonymize author logins across a collection of canonical PullRequest entities."""
    return [anonymize_pull_request(pr, salt=salt) for pr in prs]
