.PHONY: install test lint typecheck ci

install:
	uv pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy src

ci: lint typecheck test
