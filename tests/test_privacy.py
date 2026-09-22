from __future__ import annotations

from datetime import UTC, datetime

from gain.privacy import anonymize_dataset, anonymize_pull_request, pseudonymize_author
from tests.factories import make_pr


def test_pseudonymize_author_deterministic() -> None:
    # Deterministic output for same login and salt
    p1 = pseudonymize_author("octocat", salt="test-salt")
    p2 = pseudonymize_author("octocat", salt="test-salt")
    assert p1 == p2
    assert p1 is not None
    assert p1.startswith("anon_")

    # Case insensitivity
    p3 = pseudonymize_author("OctoCat", salt="test-salt")
    assert p3 == p1

    # Different salt produces different pseudonym
    p_diff = pseudonymize_author("octocat", salt="other-salt")
    assert p_diff != p1


def test_pseudonymize_author_bot() -> None:
    p_bot = pseudonymize_author("dependabot[bot]", salt="salt-1")
    assert p_bot is not None
    assert p_bot.startswith("anon_")
    assert p_bot.endswith("[bot]")


def test_pseudonymize_author_none_empty() -> None:
    assert pseudonymize_author(None) is None
    assert pseudonymize_author("") is None
    assert pseudonymize_author("   ") is None


def test_anonymize_pull_request() -> None:
    pr = make_pr(
        number=100,
        author_login="alice",
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    anon_pr = anonymize_pull_request(pr, salt="my-salt")
    assert anon_pr.github_node_id == pr.github_node_id
    assert anon_pr.author_login is not None
    assert anon_pr.author_login.startswith("anon_")
    assert anon_pr.author_login != "alice"


def test_anonymize_dataset() -> None:
    prs = [
        make_pr(
            number=1,
            author_login="alice",
            created_at=datetime(2026, 1, 15, tzinfo=UTC),
        ),
        make_pr(
            number=2,
            author_login="bob",
            created_at=datetime(2026, 1, 16, tzinfo=UTC),
        ),
    ]
    anon_prs = anonymize_dataset(prs, salt="dataset-salt")
    assert len(anon_prs) == 2
    assert anon_prs[0].author_login != "alice"
    assert anon_prs[1].author_login != "bob"
    assert anon_prs[0].author_login != anon_prs[1].author_login


def test_pseudonymize_author_without_salt_uses_ephemeral_key() -> None:
    p1 = pseudonymize_author("dev_user")
    p2 = pseudonymize_author("dev_user")
    assert p1 == p2
    assert p1 is not None
    assert p1.startswith("anon_")
    # Verified it produces a valid 17-char pseudonym (anon_ + 12 hex)
    assert len(p1) == 17
