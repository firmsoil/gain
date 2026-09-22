from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_API_VERSION = "1.0"
CURRENT_CONTRACT_VERSION = "2026-06-01"
SUPPORTED_CONTRACT_VERSIONS = frozenset({"2026-06-01", "2026-01-01"})


class VersionedResponse[T](BaseModel):
    """Standardized versioned envelope wrapping all GAIN MCP tool and resource payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: str = Field(
        default=DEFAULT_API_VERSION,
        description="Semantic version of the GAIN MCP protocol.",
    )
    contract_version: str = Field(
        default=CURRENT_CONTRACT_VERSION,
        description="Date-stamped contract revision of the payload schema.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when response was synthesized.",
    )
    data: T = Field(description="Strongly typed payload body.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Auxiliary envelope metadata, provenance tags, or pagination markers.",
    )


def wrap_versioned[T](
    data: T,
    *,
    contract_version: str = CURRENT_CONTRACT_VERSION,
    metadata: dict[str, Any] | None = None,
) -> VersionedResponse[T]:
    """Wrap any data payload in the standard GAIN MCP VersionedResponse envelope."""
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ValueError(
            f"Unsupported contract_version '{contract_version}'. "
            f"Supported versions: {', '.join(sorted(SUPPORTED_CONTRACT_VERSIONS))}"
        )

    return VersionedResponse[T](
        data=data,
        contract_version=contract_version,
        metadata=metadata or {},
    )
