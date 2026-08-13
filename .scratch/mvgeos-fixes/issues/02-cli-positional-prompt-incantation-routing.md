# 02 — Disambiguate positional CLI prompt incantations from leaf subcommands

**What to build:** Route positional text prompts that begin with subcommand names (e.g., `mvgeos info about python`, `mvgeos build a web app`) to the prompt runner instead of triggering Click `UsageError: Got unexpected extra arguments`.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `MvgeosGroup.invoke` in `mvgeos_cli/main.py` checks whether target subcommands accept positional arguments.
- [ ] Positional prompts starting with leaf subcommand names (`info`, `build`) that take no positional arguments are handled as prompt incantations when extra arguments are present.
- [ ] Running unquoted positional prompts such as `mvgeos info about python` executes the prompt successfully.
- [ ] Integration tests in `mvgeos-cli/tests/integration/cli.py` verify unquoted subcommand-prefixed prompt routing.
