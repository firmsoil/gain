from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from gain.model.pr import PullRequest


def normalize_raw_record(record: dict[str, Any]) -> PullRequest:
    metadata = record["metadata"]
    node = record["node"]
    author = node.get("author") or {}
    return PullRequest(
        github_node_id=str(node["id"]),
        number=int(node["number"]),
        repository_name_with_owner=str(metadata["repository_name_with_owner"]),
        repository_id=str(metadata["repository_id"]),
        author_login=author.get("login"),
        author_type=author.get("__typename"),
        created_at=_parse_datetime(node["createdAt"]),
        closed_at=_parse_nullable_datetime(node.get("closedAt")),
        merged_at=_parse_nullable_datetime(node.get("mergedAt")),
        state=str(node["state"]),
        is_draft=bool(node.get("isDraft", False)),
        additions=_optional_int(node.get("additions")),
        deletions=_optional_int(node.get("deletions")),
        changed_files=_optional_int(node.get("changedFiles")),
        review_decision=node.get("reviewDecision"),
        collected_at=_parse_datetime(metadata["collected_at"]),
        ingestion_run_id=str(metadata["ingestion_run_id"]),
    )


def normalize_records(
    records: list[dict[str, Any]],
) -> tuple[list[PullRequest], list[dict[str, Any]]]:
    valid: list[PullRequest] = []
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        try:
            valid.append(normalize_raw_record(record))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            errors.append({"record_index": index, "error": str(exc)})
    return valid, errors


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_nullable_datetime(value: str | None) -> datetime | None:
    return None if value is None else _parse_datetime(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
