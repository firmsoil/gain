"""Policy Guard: Enforces read-only boundaries, tool permissions, and prompt injection defense."""

from __future__ import annotations

import re
from typing import Any

import structlog

from gain.agent.models import InvestigationContext

logger = structlog.get_logger(__name__)

# Mutating or write actions strictly forbidden in GAIN Agent
FORBIDDEN_TOOL_KEYWORDS = (
    "write",
    "delete",
    "create_repo",
    "create_branch",
    "merge",
    "push",
    "update_pull",
    "add_comment",
    "assign",
)

ALLOWED_GAIN_TOOLS = {
    "get_dora_metrics",
    "query_engineering_metrics",
    "compare_cohorts",
    "analyze_ai_impact",
    "calculate_ai_roi",
    "explain_metric",
    "get_metric_lineage",
    "get_evidence",
    "start_investigation",
    "get_investigation",
    "get_data_quality",
    "get_canonical_entity",
}

ALLOWED_GITHUB_TOOLS = {
    "get_pull_request_details",
    "get_commit_details",
    "list_recent_comments",
    "get_repo_info",
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"bypass\s+all\s+(security|policy)\s+rules", re.IGNORECASE),
    re.compile(r"output\s+(all\s+)?(tokens|secrets|credentials)", re.IGNORECASE),
]


UNTRUSTED_TEXT_FIELDS = {
    "title",
    "body",
    "message",
    "comment",
    "description",
    "content",
    "text",
    "commit_message",
    "pr_body",
}


class SecurityPolicyViolationError(Exception):
    """Raised when an action or tool violates the GAIN security policy."""


class PolicyGuard:
    """Enforces authorization, read-only safety, and prompt-injection sanitization."""

    def validate_tool_execution(
        self,
        tool_name: str,
        target_system: str,
        context: InvestigationContext,
    ) -> None:
        """Validate tool permissions, read-only safety, and context scopes."""
        # 1. Enforce strict read-only boundary
        tool_lower = tool_name.lower()
        if any(bad in tool_lower for bad in FORBIDDEN_TOOL_KEYWORDS):
            logger.error("security_policy_write_attempt_blocked", tool=tool_name)
            raise SecurityPolicyViolationError(
                f"Tool '{tool_name}' implies a write or mutating operation, "
                "which is strictly prohibited."
            )

        # 2. Check tool system whitelist
        if target_system == "gain_mcp":
            if tool_name not in ALLOWED_GAIN_TOOLS:
                logger.error("security_policy_disallowed_gain_tool", tool=tool_name)
                raise SecurityPolicyViolationError(
                    f"Tool '{tool_name}' is not in the allowed GAIN MCP tool whitelist."
                )
        elif target_system == "github_mcp":
            if tool_name not in ALLOWED_GITHUB_TOOLS:
                logger.error("security_policy_disallowed_github_tool", tool=tool_name)
                raise SecurityPolicyViolationError(
                    f"Tool '{tool_name}' is not in the allowed GitHub MCP tool whitelist."
                )
        else:
            raise SecurityPolicyViolationError(f"Unknown target system '{target_system}'.")

        # 3. Verify read scopes in context
        required_scope = "gain:metrics:read"
        if required_scope not in context.scopes and "gain:admin" not in context.scopes:
            logger.error("security_policy_scope_missing", required_scope=required_scope)
            raise SecurityPolicyViolationError(
                f"Context for principal '{context.principal_id}' lacks required "
                f"scope '{required_scope}'."
            )

    def sanitize_repository_text(self, text: str, is_untrusted_field: bool = True) -> str:
        """Sanitize external repository text and neutralize prompt-injection sequences."""
        if not text:
            return ""

        sanitized = text
        for pattern in PROMPT_INJECTION_PATTERNS:
            sanitized = pattern.sub("[REDACTED_INJECTION_PATTERN]", sanitized)

        if is_untrusted_field:
            return f"<untrusted_repo_content>\n{sanitized.strip()}\n</untrusted_repo_content>"
        return sanitized

    def sanitize_tool_output(self, output: dict[str, Any]) -> dict[str, Any]:
        """Recursively scan and sanitize textual fields in tool results."""
        clean_output: dict[str, Any] = {}
        for k, v in output.items():
            is_untrusted = k.lower() in UNTRUSTED_TEXT_FIELDS
            if isinstance(v, str):
                clean_output[k] = self.sanitize_repository_text(v, is_untrusted_field=is_untrusted)
            elif isinstance(v, dict):
                clean_output[k] = self.sanitize_tool_output(v)
            elif isinstance(v, list):
                clean_output[k] = [
                    self.sanitize_repository_text(item, is_untrusted_field=is_untrusted)
                    if isinstance(item, str)
                    else self.sanitize_tool_output(item)
                    if isinstance(item, dict)
                    else item
                    for item in v
                ]
            else:
                clean_output[k] = v
        return clean_output
