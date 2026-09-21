"""Jira enterprise source adapter normalizing Jira REST API issues into CanonicalIssue."""

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


class JiraSourceAdapter(BaseSourceAdapter[CanonicalIssue]):
    """Adapter for Jira issue tracking systems."""

    @property
    def source_system(self) -> SourceSystem:
        return SourceSystem.JIRA

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
        """Normalize a Jira issue API JSON dictionary into a CanonicalIssue."""
        key = str(raw_record["key"])
        fields = raw_record.get("fields") or {}

        # Project key
        project = fields.get("project") or {}
        project_key = project.get("key") or key.split("-")[0]

        # Summary / Title
        title = str(fields.get("summary") or key)
        description = fields.get("description")
        desc_text = str(description) if description is not None else None

        # Issue Type mapping
        raw_type = (fields.get("issuetype") or {}).get("name", "Task").lower()
        issue_type = self._map_issue_type(raw_type)

        # Status mapping
        raw_status = (fields.get("status") or {}).get("name", "Open").lower()
        status_category = (
            (fields.get("status") or {}).get("statusCategory", {}).get("key", "").lower()
        )
        status = self._map_issue_status(raw_status, status_category)

        # Priority
        priority_obj = fields.get("priority")
        priority = priority_obj.get("name") if isinstance(priority_obj, dict) else None

        # Author and Assignee
        reporter_obj = fields.get("reporter")
        author = None
        if reporter_obj:
            author = reporter_obj.get("displayName") or reporter_obj.get("accountId")
        assignee_obj = fields.get("assignee")
        assignee = None
        if assignee_obj:
            assignee = assignee_obj.get("displayName") or assignee_obj.get("accountId")

        # Labels
        labels = [str(lbl) for lbl in fields.get("labels") or []]

        # Story points (common custom fields)
        story_points = None
        for sp_key in ("customfield_10016", "customfield_10004", "story_points"):
            if sp_key in fields and fields[sp_key] is not None:
                try:
                    story_points = float(fields[sp_key])
                    break
                except (ValueError, TypeError):
                    continue

        # Timestamps
        created_at = self._parse_iso(str(fields["created"]))
        updated_at = self._parse_iso(str(fields.get("updated") or fields["created"]))
        resolved_at = (
            self._parse_iso(str(fields["resolutiondate"])) if fields.get("resolutiondate") else None
        )
        due_date = self._parse_iso(str(fields["duedate"])) if fields.get("duedate") else None

        # Linked pull requests (e.g. from dev status or custom fields)
        linked_prs: list[str] = []
        if "linked_prs" in raw_record:
            linked_prs.extend(str(pr) for pr in raw_record["linked_prs"])

        return CanonicalIssue(
            id=f"jira:{key}",
            key=key,
            source_system=SourceSystem.JIRA,
            project_key=project_key,
            title=title,
            description=desc_text,
            issue_type=issue_type,
            status=status,
            priority=priority,
            author=author,
            assignee=assignee,
            labels=labels,
            story_points=story_points,
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
            due_date=due_date,
            linked_pr_keys=linked_prs,
            collected_at=collected_at,
            ingestion_run_id=run_id,
        )

    @staticmethod
    def _map_issue_type(name: str) -> IssueType:
        if "story" in name:
            return IssueType.STORY
        if "bug" in name or "defect" in name:
            return IssueType.BUG
        if "epic" in name:
            return IssueType.EPIC
        if "sub" in name:
            return IssueType.SUBTASK
        if "task" in name:
            return IssueType.TASK
        return IssueType.OTHER

    @staticmethod
    def _map_issue_status(name: str, category_key: str) -> IssueStatus:
        if category_key == "done" or name in {"done", "closed", "resolved"}:
            return IssueStatus.DONE
        if category_key == "indeterminate" or name in {"in progress", "in review", "review"}:
            return IssueStatus.IN_REVIEW if "review" in name else IssueStatus.IN_PROGRESS
        if name in {"cancelled", "rejected", "won't do", "wont do"}:
            return IssueStatus.CANCELLED
        return IssueStatus.OPEN

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
