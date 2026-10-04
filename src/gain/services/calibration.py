"""Closed-loop prompt calibration service (SE 3.0 Section 4.5).

Eliminates trial-and-error prompt engineering by capturing positive human feedback
and automatically injecting battle-tested exemplars into model reasoning contexts
(Hassan et al. 2026).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from gain.config import Settings, get_settings
from gain.curriculum.taxonomy import DomainCurriculum

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CalibratedExemplar:
    """A battle-tested investigation briefing validated by senior human analysts."""

    exemplar_id: str
    query: str
    briefing_text: str
    feedback_score: int  # +1 for approved/reinforced, -1 for rejected
    analyst_id: str
    evidence_package_id: str | None
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromptCalibrationService:
    """Manages the closed-loop data flywheel: human feedback capture and prompt calibration."""

    def __init__(
        self,
        settings: Settings | None = None,
        curriculum: DomainCurriculum | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        base_dir = getattr(self.settings, "output_dir", Path("./data"))
        self.calibration_dir: Path = base_dir / "calibration"
        self.curriculum = curriculum or DomainCurriculum.load_default_curriculum()

    def _ensure_dir(self) -> None:
        self.calibration_dir.mkdir(parents=True, exist_ok=True)

    def record_feedback(
        self,
        query: str,
        briefing_text: str,
        feedback_score: int,
        analyst_id: str,
        evidence_package_id: str | None = None,
    ) -> CalibratedExemplar:
        """Capture human analyst feedback for an investigation briefing.

        Approved briefings (+1) are persisted to the calibrated exemplar store.
        """
        self._ensure_dir()
        exemplar_id = f"ex-{uuid4().hex[:8]}"
        now_utc = datetime.now(UTC).isoformat()

        exemplar = CalibratedExemplar(
            exemplar_id=exemplar_id,
            query=query,
            briefing_text=briefing_text,
            feedback_score=feedback_score,
            analyst_id=analyst_id,
            evidence_package_id=evidence_package_id,
            created_at_utc=now_utc,
        )

        file_path = self.calibration_dir / f"{exemplar_id}.json"
        file_path.write_text(json.dumps(exemplar.to_dict(), indent=2), encoding="utf-8")

        log.info(
            "calibration_feedback_recorded",
            exemplar_id=exemplar_id,
            feedback_score=feedback_score,
            analyst_id=analyst_id,
        )
        return exemplar

    def retrieve_positive_exemplars(
        self,
        query: str,
        limit: int = 2,
    ) -> list[CalibratedExemplar]:
        """Retrieve battle-tested exemplars that match keywords in the query."""
        if not self.calibration_dir.exists():
            return []

        q_terms = set(re.findall(r"\w+", query.lower()))
        matched: list[tuple[int, CalibratedExemplar]] = []

        for p in sorted(self.calibration_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                exemplar = CalibratedExemplar(**data)
                # Only reinforce approved positive exemplars
                if exemplar.feedback_score <= 0:
                    continue

                ex_terms = set(re.findall(r"\w+", exemplar.query.lower()))
                overlap = len(q_terms.intersection(ex_terms))
                matched.append((overlap, exemplar))
            except Exception as e:
                log.warning("exemplar_read_failed", file=str(p), error=str(e))
                continue

        # Sort by term overlap descending
        matched.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in matched[:limit]]

    def compile_calibrated_prompt(self, query: str) -> str:
        """Construct a calibrated system prompt by combining curriculum rules and exemplars."""
        # 1. Authoritative curriculum grounding
        curriculum_context = self.curriculum.compile_grounding_prompt(query)

        # 2. Battle-tested positive exemplars from the closed-loop flywheel
        exemplars = self.retrieve_positive_exemplars(query, limit=2)
        exemplar_sections: list[str] = []

        if exemplars:
            exemplar_sections.append("\n### Battle-Tested Exemplar Patterns (Analyst Approved):")
            for idx, ex in enumerate(exemplars, 1):
                exemplar_sections.append(
                    f"\n**Exemplar {idx} [Query: '{ex.query}']**:\n{ex.briefing_text}"
                )

        full_prompt = curriculum_context + "\n" + "\n".join(exemplar_sections)
        return full_prompt
