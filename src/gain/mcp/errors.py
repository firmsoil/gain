"""Structured MCP error hierarchy for GAIN."""

from __future__ import annotations

from typing import Any


class MCPError(Exception):
    """Base error for all GAIN MCP operations."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class AuthenticationError(MCPError):
    code = "AUTHENTICATION_FAILURE"
    status_code = 401


class AuthorizationError(MCPError):
    code = "AUTHORIZATION_FAILURE"
    status_code = 403


class InvalidInputError(MCPError):
    code = "INVALID_INPUT"
    status_code = 400


class NotFoundError(MCPError):
    code = "NOT_FOUND"
    status_code = 404


class UnsupportedCapabilityError(MCPError):
    code = "UNSUPPORTED_CAPABILITY"
    status_code = 501


class InsufficientDataError(MCPError):
    code = "INSUFFICIENT_DATA"
    status_code = 422


class StaleDataError(MCPError):
    code = "STALE_DATA"
    status_code = 412


class AnalysisError(MCPError):
    code = "ANALYSIS_FAILURE"
    status_code = 500


class DependencyUnavailableError(MCPError):
    code = "DEPENDENCY_UNAVAILABLE"
    status_code = 503


class TimeoutError(MCPError):
    code = "TIMEOUT"
    status_code = 504
