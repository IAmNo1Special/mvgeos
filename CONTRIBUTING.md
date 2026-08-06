# Contributing

## Setup

```bash
git clone <repo-url>
cd mvgeos
uv sync
pre-commit install
```

## Code Style

- Follow the Google Python Style Guide
- Ruff for linting and formatting
- mypy strict mode for type checking
- 88-character line length

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run tests for a specific package
uv run pytest packages/mvgeos-agent/tests/
```

Target: 90%+ test coverage, all tests passing.

## Architecture Decision Records

See `ADR/` directory for all architectural decisions. To propose a new ADR:

1. Create a new file `ADR/NNNN-short-name.md`
2. Follow the ADR template in `ADR/0001-monorepo-with-uv.md`
3. Submit as part of a PR with a description of the decision
