import json
from datetime import UTC, datetime
from pathlib import Path

from gain.schema import normalize_records


def test_normalization() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "graphql_page_1.json").read_text())
    metadata = {
        "repository_name_with_owner": "acme/example",
        "repository_id": "R_1",
        "collected_at": datetime.now(UTC).isoformat(),
        "ingestion_run_id": "run-1",
    }
    raw_nodes = fixture["data"]["repository"]["pullRequests"]["nodes"]
    records = [{"metadata": metadata, "node": node} for node in raw_nodes]
    prs, errors = normalize_records(records)
    assert len(prs) == 2
    assert not errors
    assert prs[0].number == 1
    assert prs[0].merged_at is not None
    assert (prs[0].merged_at - prs[0].created_at).total_seconds() == 21600.0
    assert prs[1].author_type == "Bot"
