# Handoff: post-audit issue set

State as of 2026-10-04. 9 commits on `main`, tree clean, CI green.

## What was audited and why

An earlier draft of #162 claimed engine code still resolved `AGENTS.md` paths. It
did not — `steering-bridge` owns `AGENTS.md` via `BEFORE_MVGE_START`, and no
first-party engine module reads it. That error was **methodological**: read engine
code, see a gap, assume nothing owned it. Three other issues were exposed to the
same failure and have now been audited against the marketplace.

## Audit results

| Issue | Was at risk | Verdict |
| --- | --- | --- |
| #162 | yes | **Corrected.** `environment.py` removed; scope narrowed to Rune search paths. ADR-0014 decision 3 now carries an explicit carve-out for persona resolution. |
| #163 | yes | **Confirmed, strengthened.** `steering-bridge/rune.py:98-105` branches on payload shape — a shipped Rune working around this exact fragility. |
| #164 | yes | **Confirmed, clarified.** `steering-bridge` does *prompt-level* steering per session; ADR-0012's `steer()` is turn-level and mid-run. Not obsoleted, but must not be conflated. |
| #165 | no | Engine-only, directly verified line counts. Unchanged. |
| #166 | no | GUI-only, directly verified. Unchanged. |
| marketplace #2 | yes | **Under-scoped.** Four runes bypass `global_agents_dir()`, not one. Broadened, plus an acceptance criterion to automate the check. |
| marketplace #3 | — | **New.** `heal-my-goap` reads a credential from the dead `.agents/.mvgeos/` path, bypassing engine auth resolution. |

## Standing lesson

Before claiming something is unimplemented, grep `mvgeos-marketplace/runes/` for a
Rune that owns it. `steering-bridge` is the reference implementation for both path
resolution and payload discipline, and it is worth reading before designing
anything that touches either.

Two forcing functions now exist, and both came from this:

- `mvgeos-core/scripts/check_adr_contract.py` — an ADR cannot describe code that is gone.
- Proposed in marketplace#2 — a Rune cannot bypass `global_agents_dir()` undetected.

## Order

    #162  layer stack        frontier, independent
    #163  Sigil payloads     frontier, independent
    #164  design-it-twice    frontier, no src changes
      |
    #165  implement seam     blocked by #163, #164
      |
    #166  GUI Turn owner     blocked by #165

    marketplace #2  four runes bypass the resolver     independent
    marketplace #3  heal-my-goap credential path       independent
