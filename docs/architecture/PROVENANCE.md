# Architecture Provenance & Interoperability

## Architectural Origins & Independence

MvgeOS is an independent, ground-up agentic operating system architecture built in Python.

While MvgeOS implements its own clean-room design and domain model (Mvges, Spells, Realms, Tomes, Runes, Sigils), its design was informed and inspired by notable open-source architectures and research in the autonomous agent ecosystem:

- **Pi (earendil-works/pi)**: Pioneer of lightweight, streaming JSONL session logs and modular extension hooks.
- **Google ADK (Agent Development Kit)**: Concepts around structural agent-environment scaffolding and declarative tool manifests.
- **Eve**: Event-driven multi-turn execution loops and asynchronous state trees.
- **arXiv Literature & State Machine Research**: Foundational papers on hierarchical multi-turn reasoning loops, memory compaction algorithms, and autonomous test-driven recovery.

---

## Frictionless Migration & Compatibility

MvgeOS was deliberately engineered with immediate, frictionless interoperability for users transitioning from other ecosystems:

### 1. Pi Compatibility (Current)
The persistence layer (mvgeos-tome) implements full schema and wire compatibility with Pi's session format. Users and developers migrating from Pi can:
- Drop existing session JSONL files into MvgeOS without schema translation.
- Resume historical agent trajectories without data loss.
- Transition existing extensions into MvgeOS Runes using lifecycle Sigil hooks.

### 2. Universal Agent Session Reconstruction (Roadmap)
MvgeOS's persistence and session abstractions are designed to expand beyond Pi. The roadmap includes universal session reconstructors capable of parsing and resuming trajectories originated in:
- **Codex CLI / Assistants**
- **Claude Code**
- **PaLM / Gemini Agent Harnesses**
- **DeepSeek Agent Harness**

By treating conversation logs, tool invocations, and execution snapshots as first-class, reconstructible state graphs, MvgeOS aims to serve as a universal substrate where summoners can continue sessions regardless of where they began.
