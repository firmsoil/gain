from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

FROZEN_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
FROZEN_CREATED = datetime(2026, 6, 10, 10, 0, 0, tzinfo=UTC)
FROZEN_MERGED = datetime(2026, 6, 12, 14, 30, 0, tzinfo=UTC)


@pytest.fixture
def frozen_now() -> datetime:
    return FROZEN_NOW


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure for tests."""
    for sub in ("raw", "canonical", "metrics", "requirements", "specification-seeds"):
        (tmp_path / sub).mkdir()
    return tmp_path
