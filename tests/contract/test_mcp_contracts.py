from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from gain.mcp.schemas.versioning import (
    CURRENT_CONTRACT_VERSION,
    DEFAULT_API_VERSION,
    VersionedResponse,
    wrap_versioned,
)


class SampleMetricPayload(BaseModel):
    repository: str
    cycle_time_p50_hours: float
    cycle_time_p90_hours: float
    sample_size: int


def test_wrap_versioned_envelope() -> None:
    data = SampleMetricPayload(
        repository="acme/gain",
        cycle_time_p50_hours=14.5,
        cycle_time_p90_hours=48.2,
        sample_size=120,
    )
    wrapped = wrap_versioned(data, metadata={"source": "polars_analytics"})

    assert wrapped.api_version == DEFAULT_API_VERSION
    assert wrapped.contract_version == CURRENT_CONTRACT_VERSION
    assert wrapped.data == data
    assert wrapped.metadata["source"] == "polars_analytics"
    assert wrapped.timestamp is not None

    # JSON roundtrip serialization check
    dumped = wrapped.model_dump(mode="json")
    assert dumped["api_version"] == "1.0"
    assert dumped["contract_version"] == "2026-06-01"
    assert dumped["data"]["repository"] == "acme/gain"
    assert dumped["data"]["cycle_time_p50_hours"] == 14.5


def test_wrap_versioned_unsupported_version_raises() -> None:
    data = {"sample": 1}
    with pytest.raises(ValueError, match="Unsupported contract_version"):
        wrap_versioned(data, contract_version="1999-01-01")


def test_versioned_response_schema_compatibility() -> None:
    schema = VersionedResponse[SampleMetricPayload].model_json_schema()
    assert "properties" in schema
    assert "api_version" in schema["properties"]
    assert "contract_version" in schema["properties"]
    assert "data" in schema["properties"]
    assert "metadata" in schema["properties"]


def test_json_rpc_wire_framing_compatibility() -> None:
    """Validate that VersionedResponse envelopes map cleanly to JSON-RPC 2.0 wire frames."""
    data = SampleMetricPayload(
        repository="firmsoil/gain",
        cycle_time_p50_hours=8.0,
        cycle_time_p90_hours=24.0,
        sample_size=50,
    )
    wrapped = wrap_versioned(data)
    dumped = wrapped.model_dump(mode="json")
    json_rpc_frame: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": "req-101",
        "result": dumped,
    }
    assert json_rpc_frame["jsonrpc"] == "2.0"
    assert json_rpc_frame["id"] == "req-101"
    res_payload = json_rpc_frame["result"]
    assert isinstance(res_payload, dict)
    assert res_payload["api_version"] == "1.0"
    assert res_payload["data"]["repository"] == "firmsoil/gain"
