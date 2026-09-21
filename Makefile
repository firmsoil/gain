.PHONY: install test lint typecheck ci

install:
	uv pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src tests

ci: lint typecheck test
