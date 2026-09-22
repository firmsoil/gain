from __future__ import annotations

from gain.errors import ConfigurationError, GainError, RateLimitError


def test_gain_error_defaults() -> None:
    err = GainError("test")
    assert err.error_code == "GAIN-0000"
    assert err.is_retryable is False
    assert err.severity == "ERROR"
    assert err.team == "platform"
    assert err.details == {}
    assert str(err) == "test"


def test_gain_error_details() -> None:
    err = GainError("test", details={"foo": "bar"})
    assert err.details == {"foo": "bar"}


def test_rate_limit_error() -> None:
    err = RateLimitError("rate limited")
    assert err.error_code == "GAIN-2029"
    assert err.is_retryable is True
    assert err.team == "platform"


def test_configuration_error() -> None:
    err = ConfigurationError("bad config")
    assert err.error_code == "GAIN-1001"
    assert err.is_retryable is False
    assert err.team == "platform"
