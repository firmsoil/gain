"""Domain service for generating and retrieving structured evidence packages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gain.config import Settings, get_settings


@dataclass(frozen=True)
class EvidencePackage:
    evidence_id: str
    claim: str
    claim_classification: str  # Observed, Derived, Associated, Attributed, Modeled, Assumed
    metric_id: str
    metric_version: int
    population_count: int
    time_window: str
    data_freshness_utc: str | None
    statistical_method: str
    assumptions: list[str]
    limitations: list[str]
    confidence_level: str  # High, Medium, Low
    source_references: list[str]
    supporting_artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        base_dir = getattr(self.settings, "output_dir", Path("./data"))
        self.evidence_dir: Path = base_dir / "evidence"

    def _ensure_dir(self) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def store_evidence(self, pkg: EvidencePackage) -> None:
        self._ensure_dir()
        path = self.evidence_dir / f"{pkg.evidence_id}.json"
        path.write_text(json.dumps(pkg.to_dict(), indent=2), encoding="utf-8")

    def get_evidence(self, evidence_id: str) -> EvidencePackage | None:
        path = self.evidence_dir / f"{evidence_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return EvidencePackage(**data)

    def list_evidence_ids(self) -> list[str]:
        if not self.evidence_dir.exists():
            return []
        return [p.stem for p in sorted(self.evidence_dir.glob("*.json"))]
