#!/usr/bin/env bash
set -euo pipefail

(command -v uv >/dev/null 2>&1 && uv pip install -e '.[dev]') || true
cp -n .env.example .env || true
./.venv/bin/python -m gain.cli config-check
./.venv/bin/python -m gain.cli backfill
