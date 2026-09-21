"""Domain service for durable, application-owned GAIN investigations."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gain.config import Settings, get_settings


@dataclass(frozen=True)
class InvestigationRecord:
    investigation_id: str
    plan_id: str
    tenant_id: str
    principal_id: str
    title: str
    status: str  # "INITIATED", "IN_PROGRESS", "COMPLETED", "FAILED"
    analysis_version: str
    query_specification: dict[str, Any]
    created_at_utc: str
    updated_at_utc: str
    evidence_references: list[str]
    result_references: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvestigationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        base_dir = getattr(self.settings, "output_dir", Path("./data"))
        self.investigation_dir: Path = base_dir / "investigations"

    def _ensure_dir(self) -> None:
        self.investigation_dir.mkdir(parents=True, exist_ok=True)

    def start_investigation(
        self,
        title: str,
        query_specification: dict[str, Any],
        tenant_id: str,
        principal_id: str,
    ) -> InvestigationRecord:
        self._ensure_dir()
        inv_id = f"inv-{uuid.uuid4().hex[:12]}"
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()

        record = InvestigationRecord(
            investigation_id=inv_id,
            plan_id=plan_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            title=title,
            status="INITIATED",
            analysis_version="gain-investigation-v1",
            query_specification=query_specification,
            created_at_utc=now,
            updated_at_utc=now,
            evidence_references=[],
            result_references=[],
        )

        path = self.investigation_dir / f"{inv_id}.json"
        path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
        return record

    def get_investigation(
        self,
        investigation_id: str,
        tenant_id: str,
    ) -> InvestigationRecord | None:
        path = self.investigation_dir / f"{investigation_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        record = InvestigationRecord(**data)

        # Enforce strict tenant isolation: never return record of another tenant
        if record.tenant_id != tenant_id:
            return None

        return record
