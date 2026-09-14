# GAIN Quickstart

## Prerequisites
- Python 3.12+
- `uv`
- GitHub App credentials or a development PAT with minimum required permissions

## Setup
```bash
uv sync
cp .env.example .env
```

## Validate authentication
```bash
gain auth-check
```

## Backfill one year
```bash
gain backfill --since 365d --repo-config config/repos.yaml
```

## Validate data
```bash
gain validate
```

## Compute metrics
```bash
gain compute --metric-set core-pr
```

## Generate report
```bash
gain report --level executive
```

## Run tests
```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
