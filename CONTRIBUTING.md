# Contributing

## Setup

```bash
git clone https://github.com/IAmNo1Special/mvgeos.git
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

Testing standards are defined in [TESTING.md](TESTING.md). Canonical invocations use the module form (`uv run python -m pytest ...`) — on Windows, direct executable spawn is blocked by Application Control policy.

```bash
# Full suite with the 88% combined coverage floor (fail_under)
uv run python -m pytest --cov

# One package, both tiers
uv run python -m pytest mvgeos-agent/tests
```

Requirement: all tests passing, 88% combined coverage floor enforced via pyproject (target 90%+).

## Architecture Decision Records

See `docs/adr/` directory for all architectural decisions. To propose a new ADR:

1. Create a new file `docs/adr/NNNN-short-name.md`
2. Follow the ADR template in `docs/adr/0001-monorepo-with-uv.md`
3. Submit as part of a PR with a description of the decision
