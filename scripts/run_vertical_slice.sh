#!/usr/bin/env bash
set -euo pipefail

uv pip install -e '.[dev]'
cp -n .env.example .env || true
./.venv/bin/python -m gain.cli config-check
./.venv/bin/python -m gain.cli backfill
