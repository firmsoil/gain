"""Linear enterprise source adapter normalizing Linear API issues into CanonicalIssue."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gain.adapters.base import BaseSourceAdapter
from gain.model.issue import (
    CanonicalIssue,
    IssueStatus,
    IssueType,
    SourceSystem,
)
from gain.storage.issues import write_canonical_issues


class LinearSourceAdapter(BaseSourceAdapter[CanonicalIssue]):
    """Adapter for Linear issue tracking systems."""

    @property
    def source_system(self) -> SourceSystem:
        return SourceSystem.LINEAR

    @property
    def entity_type(self) -> str:
        return "issues"

    def persist_canonical(self, records: list[CanonicalIssue], path: Path) -> None:
        write_canonical_issues(records, path)

    def normalize_record(
        self,
        raw_record: dict[str, Any],
        run_id: str,
        collected_at: datetime,
    ) -> CanonicalIssue:
        """Normalize a Linear issue API JSON dictionary into a CanonicalIssue."""
        identifier = str(raw_record.get("identifier") or raw_record["id"])
        team = raw_record.get("team") or {}
        project_key = str(team.get("key") or identifier.split("-")[0])

        title = str(raw_record.get("title") or identifier)
        description = raw_record.get("description")
        desc_text = str(description) if description is not None else None

        # State mapping
        state_obj = raw_record.get("state") or {}
        state_type = str(state_obj.get("type", "")).lower()
        state_name = str(state_obj.get("name", "")).lower()
        status = self._map_linear_state(state_type, state_name)

        # Estimate / Story points
        estimate = raw_record.get("estimate")
        story_points = float(estimate) if estimate is not None else None

        # Assignee and Creator
        assignee_obj = raw_record.get("assignee") or {}
        assignee = assignee_obj.get("name") or assignee_obj.get("displayName")
        creator_obj = raw_record.get("creator") or {}
        author = creator_obj.get("name") or creator_obj.get("displayName")

        # Labels
        labels_obj = raw_record.get("labels") or {}
        labels_list = labels_obj.get("nodes") if isinstance(labels_obj, dict) else labels_obj
        if not isinstance(labels_list, list):
            labels_list = []
        labels: list[str] = []
        for lbl in labels_list:
            if isinstance(lbl, dict) and lbl.get("name"):
                labels.append(str(lbl["name"]))
            elif lbl is not None:
                labels.append(str(lbl))

        # Priority
        priority_val = raw_record.get("priority")
        priority = self._map_linear_priority(priority_val)

        # Timestamps
        created_at = self._parse_iso(str(raw_record["createdAt"]))
        updated_at = self._parse_iso(str(raw_record.get("updatedAt") or raw_record["createdAt"]))
        completed_at = (
            self._parse_iso(str(raw_record["completedAt"]))
            if raw_record.get("completedAt")
            else None
        )
        due_date = (
            self._parse_iso(str(raw_record["dueDate"])) if raw_record.get("dueDate") else None
        )

        return CanonicalIssue(
            id=f"linear:{identifier}",
            key=identifier,
            source_system=SourceSystem.LINEAR,
            project_key=project_key,
            title=title,
            description=desc_text,
            issue_type=IssueType.STORY if story_points else IssueType.TASK,
            status=status,
            priority=priority,
            author=author,
            assignee=assignee,
            labels=labels,
            story_points=story_points,
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=completed_at,
            due_date=due_date,
            linked_pr_keys=[],
            collected_at=collected_at,
            ingestion_run_id=run_id,
        )

    @staticmethod
    def _map_linear_state(state_type: str, state_name: str) -> IssueStatus:
        if state_type in {"completed", "done"}:
            return IssueStatus.DONE
        if state_type in {"canceled", "cancelled"}:
            return IssueStatus.CANCELLED
        if state_type in {"started", "in_progress"}:
            if "review" in state_name:
                return IssueStatus.IN_REVIEW
            return IssueStatus.IN_PROGRESS
        if "review" in state_name:
            return IssueStatus.IN_REVIEW
        return IssueStatus.OPEN

    @staticmethod
    def _map_linear_priority(val: Any) -> str | None:
        # Linear priorities: 0 = None, 1 = Urgent, 2 = High, 3 = Normal, 4 = Low
        priority_map = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}
        if isinstance(val, int) and val in priority_map:
            return priority_map[val]
        return str(val) if val is not None else None

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
