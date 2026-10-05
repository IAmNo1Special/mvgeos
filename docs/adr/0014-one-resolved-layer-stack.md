# ADR 0014: One Resolved Layer Stack for the `.agents` Protocol

## Status

Accepted

## Date

2026-10-04

## Supersedes

The directory scheme in [ADR 0002](0002-dotagents-protocol.md) and
[ADR 0006](0006-extension-interoperability.md).

## Context

`AGENTS.md` states the **Protocol Boundary Pattern**: standard protocol
directory names at the filesystem seam (`~/.agents/sessions/`,
`~/.agents/extensions/`), MvgeOS terminology only inside Python. ADR-0002 chose
the opposite — a proprietary `.mvgeos/` subdirectory:

```
.agents/.mvgeos/runes/manifest.json
.agents/.mvgeos/tomes/
.agents/.mvgeos/auth/
.agents/.mvgeos/models.json
```

No `.mvgeos/` directory exists in any `src/` today. The only two surviving
`.mvgeos` matches in first-party code are legacy compatibility string tests
(`mvgeos-agent/src/mvgeos_agent/rune_lifecycle.py:121,128`), which the repo's own
**Zero Backward Compatibility Burden** rule says to delete.

`mvgeos_core.constants` became the resolver of record — `global_agents_dir()` and
`GLOBAL_DIR_ENV` (`mvgeos-core/src/mvgeos_core/constants.py:87-98`) — and its own
docstring names the failure this decision exists to prevent:

> *"the install path and the discovery path resolving differently is what allows
> a rune to install successfully and then load nowhere."*

That failure has not been prevented, because resolution is still duplicated in
five places that disagree:

| Site | Divergence |
| --- | --- |
| `RuneLifecycle.resolve_paths` (`rune_lifecycle.py:95-134`) | Infers `Scope` by substring-matching the path string; still recognises the dead `.mvgeos/{agent}/runes` and `.mvgeos/runes` forms. |
| `Mvge.__init__` (`mvge.py:356-393`) | Appends colocated `runes/`, config `runes/`+`extensions/`, and package `runes/` — a second precedence pass with its own rules. |
| `dynamic_commands.get_extension_dirs` (`dynamic_commands.py:20-50`) | Uses the ambient `Path.cwd()` and probes the non-standard `<cwd>/extensions`. |
| `environment.resolve_system_prompt` (`environment.py:303,619,671`) | Falls back to `Path.cwd()` when no project directory is given. |
| `approval-rune/gate.py:71` | `DEFAULT_DATA_DIR = Path.home() / ".agents" / "approval"` — ignores `MVGEOS_GLOBAL_DIR` entirely. |

Seven of the thirty commits before this ADR were fixes to some variant of this.
`Scope` exists as an enum but is metadata only: precedence is list order, and a
user-supplied `rune_paths` config silently replaces the whole layering as a side
effect (`environment.py:444-453`).

## Decision

One module owns the layer stack and is the only place a path is derived.

1. **Single resolver.** Every global-layer path is produced by one call. The
   resolution is read at call time, never frozen at import — the original
   `DEFAULT_SESSION_DIR` constant was resolved once during import and could not be
   redirected afterwards.

2. **Layer order, most general to most specific.** global → user → agent →
   project. `$MVGEOS_GLOBAL_DIR` overrides the global layer for every read and
   every write, which is what makes an isolated run possible.

3. **Project is anchored, never ambient.** The project layer is derived from an
   explicit project directory and is *omitted entirely* when none is given, so
   the ambient working directory can never leak into a search path.

4. **Standard names only.** `sessions/`, `agents/`, `agents/<name>/extensions/`,
   `agents/<name>/skills/`, `skills/`, `extensions/`, `auth/`, `approval/`,
   `models.json`, `history`. No proprietary subdirectory.

5. **`Scope` becomes a ranking rule, not a label.** Precedence derives from the
   layer a path belongs to, not from the order a caller happened to concatenate
   strings in. Installation and discovery ask the same question and get the same
   answer, because they are the same call.

6. **`rune_paths` narrows or extends the stack explicitly.** It never replaces
   the layering as a side effect of being set.

7. **`GLOBAL_DIR_ENV` is honoured everywhere, including by Runes.** A Rune that
   hardcodes `~/.agents` is a bug, and the test suite asserts it.

## Consequences

**Positive**

- One place to change when the layout moves. Install path and discovery path
  cannot diverge, because they are one call rather than two.
- `MVGEOS_GLOBAL_DIR` isolates a whole run — global Rune layer, Tomes, auth,
  approval state and model cache together. That is what lets the root
  `conftest.py` make the suite hermetic regardless of what the developer has
  installed.
- The legacy `.mvgeos/{agent}/runes` matching becomes deletable, removing the
  last first-party reference to a scheme this decision retired.
- `approval-rune` stops writing grants outside the relocated global layer.

**Negative**

- A caller that genuinely wants a bespoke path list must now say so. There is no
  longer an implicit "my list *is* the precedence", which was quietly how
  `rune_paths` worked.
- Moving the five resolvers onto one module is a cross-package change touching
  core, agent, runes, and cli. It cannot be done package-locally.
- Any Rune already published against the old resolvers needs re-checking. The
  `mvgeos-marketplace` contract check gates engine removals but not path
  resolution.
