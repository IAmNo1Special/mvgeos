# 03 — Fix TUI status footer truncation order-of-operations and dynamic width calculation

**What to build:** Render the TUI status footer cleanly using active terminal viewport width (`app.output.get_size().columns`), preventing single-line line wrapping or text overflow when appending execution queue mode and model metadata.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Queue mode and working status (`working • mode: steer`) are appended to footer items prior to running width truncation.
- [ ] `_fit_footer()` receives live terminal column count from the active Prompt Toolkit application.
- [ ] Footer text is truncated or split dynamically into left and right sections to fit within terminal width boundaries.
- [ ] Integration tests in `mvgeos-cli/tests/integration/tui.py` verify dynamic footer rendering across terminal width changes.
