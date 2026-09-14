"""Seeker-hides-all vs baseline benchmark (hermetic, fake realm).

Measures what the engine actually sends, using production code paths
(Mvge._build_spells + _make_stream_fn snapshot), with a scripted policy
standing in for the model. No network, no keys, deterministic.

- Baseline: every spell advertised every turn (today's composition).
- Seeker: 4 meta (+3 heal) on turn 1, widened with the target on turn 2.

Run: uv run python benchmarks/seeker_vs_baseline.py --distractors 50 200
"""

# ruff: noqa: T201
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mvgeos_agent.mvge import Mvge  # noqa: E402
from mvgeos_core.spells import MvgeSpell  # noqa: E402
from mvgeos_runes.rune_runner import RuneRunner  # noqa: E402
from mvgeos_runes.types import SpellDefinition  # noqa: E402

SEEKER_META = ["tool_search", "skill_search", "skill_execute", "mcp_search"]
HEAL_SPELLS = ["goap_plan_and_execute", "goap_sense_world", "goap_synthesize_action"]


class DistractorSpell(MvgeSpell):
    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            description=f"Distractor tool {name} for benchmark payload sizing.",
            parameters={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Task input"},
                    "options": {"type": "object", "description": "Extra options"},
                },
                "required": ["input"],
            },
        )

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return {"result": "ok"}


def _wire_bytes(agent: Mvge) -> tuple[int, list[str]]:
    """Build the real wire payload via _make_stream_fn; capture ChannelConfig."""
    captured: dict[str, Any] = {}

    class FakeRealm:
        def stream(
            self, model: Any, invocations: Any, config: Any, signal: Any = None
        ) -> Any:
            captured["spells"] = config.spells
            captured["tools"] = config.tools
            raise StopIteration

    model = SimpleNamespace(id="bench/fake", api_key="", base_url="")
    state = SimpleNamespace(
        spells=agent._build_spells(),
        contemplation_level="medium",
        contemplation_budget=None,
        exclude_contemplation=False,
        system_prompt="bench",
    )
    fn = agent._make_stream_fn(model, FakeRealm(), state, 0.0, 100)
    with contextlib.suppress(StopIteration):
        fn([], None)
    payload = {"spells": captured["spells"], "tools": captured["tools"]}
    blob = json.dumps(payload)
    names = sorted(
        {s["function"]["name"] for s in (captured["spells"] or []) if "function" in s}
    )
    return len(blob.encode()), names


def _make_agent(n_distractors: int, seeker_mode: bool) -> Mvge:
    distractors = [DistractorSpell(f"distractor_{i:03d}") for i in range(n_distractors)]
    agent = Mvge(api_key="bench-key", spells=distractors)
    runner = RuneRunner()
    meta_params = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to find"}},
        "required": ["query"],
    }
    for name in SEEKER_META:
        runner.register_spell(
            SpellDefinition(
                name=name, description="Seeker meta", parameters=dict(meta_params)
            ),
            rune_name="seeker",
        )
    for name in HEAL_SPELLS:
        runner.register_spell(
            SpellDefinition(
                name=name, description="Heal", parameters=dict(meta_params)
            ),
            rune_name="heal-my-goap",
        )
    agent._runner = runner
    if seeker_mode:
        runner.set_active_spells(list(SEEKER_META), rune_name="seeker")
        runner.set_active_spells(list(HEAL_SPELLS), rune_name="heal-my-goap")
        runner.set_global_spell_allowlist([*SEEKER_META, *HEAL_SPELLS])
    return agent


def run_case(n: int) -> dict[str, Any]:
    target = f"distractor_{n // 2:03d}"

    # Baseline: everything visible, task done in 1 turn.
    base = _make_agent(n, seeker_mode=False)
    t0 = time.perf_counter()
    base_bytes, base_names = _wire_bytes(base)
    base_build_us = (time.perf_counter() - t0) * 1e6

    # Seeker: turn 1 = meta+heal only; discovery widens; turn 2 = +target.
    seeker = _make_agent(n, seeker_mode=True)
    t0 = time.perf_counter()
    t1_bytes, t1_names = _wire_bytes(seeker)
    seeker._runner.widen_global_allowlist([target])  # simulated tool_search hit
    t2_bytes, t2_names = _wire_bytes(seeker)
    seeker_build_us = (time.perf_counter() - t0) * 1e6 / 2

    total_seeker = t1_bytes + t2_bytes
    return {
        "distractors": n,
        "baseline_turns": 1,
        "baseline_bytes": base_bytes,
        "baseline_tools": len(base_names),
        "seeker_turns": 2,
        "seeker_t1_bytes": t1_bytes,
        "seeker_t2_bytes": t2_bytes,
        "seeker_total_bytes": total_seeker,
        "seeker_tools_t1": len(t1_names),
        "seeker_tools_t2": len(t2_names),
        "savings_bytes": base_bytes * 2 - total_seeker,
        "savings_pct_vs_2turn_baseline": 100.0
        * (base_bytes * 2 - total_seeker)
        / (base_bytes * 2),
        "target_visible_t2": target in t2_names,
        "target_hidden_t1": target not in t1_names,
        "base_build_us": round(base_build_us, 1),
        "seeker_build_us": round(seeker_build_us, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distractors", nargs="+", type=int, default=[50, 200])
    args = parser.parse_args()
    rows = [run_case(n) for n in args.distractors]
    print(
        f"{'N':>5} {'base B':>9} {'seek T1':>9} {'seek T2':>9} "
        f"{'seek tot':>9} {'save%':>7} {'turns':>9} {'ok':>3}"
    )
    for r in rows:
        print(
            f"{r['distractors']:>5} {r['baseline_bytes']:>9} "
            f"{r['seeker_t1_bytes']:>9} {r['seeker_t2_bytes']:>9} "
            f"{r['seeker_total_bytes']:>9} "
            f"{r['savings_pct_vs_2turn_baseline']:>6.1f}% "
            f"{r['baseline_turns']:>1}v{r['seeker_turns']:>1} "
            f"{'ok' if r['target_visible_t2'] and r['target_hidden_t1'] else 'FAIL':>3}"
        )
        print(
            f"      tools: base={r['baseline_tools']} seeker_t1={r['seeker_tools_t1']} "
            f"seeker_t2={r['seeker_tools_t2']} build_us: base={r['base_build_us']} "
            f"seeker={r['seeker_build_us']}"
        )
    print("\nBytes ~= wire JSON; ~/4 ~= tokens. Seeker costs +1 discovery turn;")


if __name__ == "__main__":
    main()
