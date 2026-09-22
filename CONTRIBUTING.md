# Contributing to GAIN

Thank you for your interest in contributing to GAIN (GitHub AI Intelligence Network).
This project provides deterministic, enterprise-grade engineering intelligence for Fortune 100 technology organizations.

---

## 1. Core Architectural Non-Negotiables

All contributors must strictly adhere to the authoritative reference architecture in [`docs/REFERENCE_ARCHITECTURE.md`](docs/REFERENCE_ARCHITECTURE.md) and [`GEMINI.md`](GEMINI.md):

1. **GitHub Remains Source of Truth**: All metrics and downstream models derive from observable GitHub telemetry. Raw API responses must be captured losslessly.
2. **Deterministic, Zero-LLM Metrics**: Metric calculations (including PR cycle time `GAIN-PR-001`) must be pure Python deterministic computations with explicit versions. No LLM reasoning or heuristic inference is permitted in metric execution.
3. **Transport Independence**: Canonical domain models (`gain.model.*`) must never expose GraphQL-specific artifacts (cursors, pageInfo, edges, connection wrappers).
4. **Preserve Validated Vertical Slice**: Under no circumstance may the existing validated vertical slice (GraphQL -> Raw JSONL -> Canonical PullRequest -> Cycle Time -> Automated Tests) be regressed or broken.
5. **Code Quality Standards**:
   - Python >=3.12
   - Strict typing with `mypy` (`strict = true`)
   - Strict linting and formatting with `ruff`
   - Structured logging via `structlog`
   - Zero hardcoded credentials or logged secrets

---

## 2. Development Setup

We use [`uv`](https://github.com/astral-sh/uv) for fast, reproducible Python environment management.

```bash
# Clone the repository
git clone https://github.com/firmsoil/gain.git
cd gain

# Create virtual environment with Python 3.12 or 3.13
uv venv --python 3.12
source .venv/bin/activate

# Install dependencies in editable mode with development tools
uv pip install -e '.[dev]'
```

---

## 3. Pre-Commit Quality Checks

Before opening a pull request, verify all quality gates locally:

```bash
# Run test suite
pytest

# Run linter
ruff check src tests

# Run formatter check
ruff format --check src tests

# Run strict type checking
mypy src tests --strict
```

---

## 4. Commit Message Guidelines

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature or capability
- `fix:` A bug fix
- `docs:` Documentation updates
- `refactor:` Code refactoring without behavioral change
- `perf:` Performance improvements
- `test:` Adding or updating tests
- `chore:` Tooling, dependency, or build changes
