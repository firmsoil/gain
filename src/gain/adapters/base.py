"""Base abstractions and error quarantine for enterprise source adapters."""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gain.config import Settings, get_settings
from gain.model.issue import SourceSystem


class AdapterIngestionResult(BaseModel):
    """Execution summary of an enterprise source adapter ingestion run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    source_system: str
    entity_type: str
    raw_records_count: int
    canonical_records_count: int
    errors_count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    raw_file_path: str
    canonical_file_path: str


class BaseSourceAdapter[T: BaseModel](ABC):
    """Abstract base adapter for enterprise engineering-system sources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    @abstractmethod
    def source_system(self) -> SourceSystem:
        """The source system identifier."""
        ...

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """The canonical entity type produced (e.g. 'issues', 'deployments')."""
        ...

    @abstractmethod
    def normalize_record(
        self,
        raw_record: dict[str, Any],
        run_id: str,
        collected_at: datetime,
    ) -> T:
        """Normalize a single raw payload into a canonical domain model."""
        ...

    @abstractmethod
    def persist_canonical(self, records: list[T], path: Path) -> None:
        """Persist canonical domain models to columnar Parquet."""
        ...

    def ingest_payloads(
        self,
        payloads: Sequence[dict[str, Any]],
        partition_key: str = "default",
        run_id: str | None = None,
    ) -> AdapterIngestionResult:
        """Losslessly capture raw payloads, normalize with quarantine, and persist."""
        ingestion_run_id = run_id or str(uuid.uuid4())
        collected_at = datetime.now(UTC)

        # 1. Ensure storage directories exist
        raw_dir = self.settings.raw_dir / self.source_system.value / partition_key
        raw_dir.mkdir(parents=True, exist_ok=True)
        canonical_dir = self.settings.canonical_dir
        canonical_dir.mkdir(parents=True, exist_ok=True)

        raw_file_path = (
            raw_dir / f"{self.entity_type}__{self.source_system.value}__{ingestion_run_id}.jsonl"
        )
        canonical_file_path = (
            canonical_dir
            / f"{self.entity_type}__{self.source_system.value}__{ingestion_run_id}.parquet"
        )

        # 2. Lossless raw capture to JSONL with provenance metadata
        with open(raw_file_path, "w", encoding="utf-8") as f:
            for idx, payload in enumerate(payloads):
                record = {
                    "metadata": {
                        "ingestion_run_id": ingestion_run_id,
                        "source_system": self.source_system.value,
                        "entity_type": self.entity_type,
                        "partition_key": partition_key,
                        "record_index": idx,
                        "collected_at": collected_at.isoformat(),
                    },
                    "payload": payload,
                }
                f.write(json.dumps(record) + "\n")

        # 3. Defensive normalization with error quarantine
        canonical_records: list[T] = []
        errors: list[dict[str, Any]] = []

        for idx, payload in enumerate(payloads):
            try:
                canonical = self.normalize_record(
                    raw_record=payload,
                    run_id=ingestion_run_id,
                    collected_at=collected_at,
                )
                canonical_records.append(canonical)
            except Exception as exc:
                errors.append(
                    {
                        "record_index": idx,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )

        # 4. Columnar persistence of canonical records
        if canonical_records:
            self.persist_canonical(canonical_records, canonical_file_path)

        return AdapterIngestionResult(
            run_id=ingestion_run_id,
            source_system=self.source_system.value,
            entity_type=self.entity_type,
            raw_records_count=len(payloads),
            canonical_records_count=len(canonical_records),
            errors_count=len(errors),
            errors=errors,
            raw_file_path=str(raw_file_path),
            canonical_file_path=str(canonical_file_path),
        )
