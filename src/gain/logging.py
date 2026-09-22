import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "token",
    "secret",
    "authorization",
    "password",
    "api_key",
    "access_token",
    "key_pem",
    "private_key",
    "certificate",
}

TOKEN_PATTERN = re.compile(
    r"(ghp_[A-Za-z0-9_]{20,}|ghs_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})"
)


def mask_secrets(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in list(event_dict.items()):
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS) and isinstance(value, str):
            event_dict[key] = "***REDACTED***"
        elif isinstance(value, str) and TOKEN_PATTERN.search(value):
            event_dict[key] = TOKEN_PATTERN.sub("***REDACTED***", value)
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, format="%(message)s", level=logging.INFO, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            mask_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
