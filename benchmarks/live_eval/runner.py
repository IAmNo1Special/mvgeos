# ruff: noqa: T201
"""Live evaluation runner for Seeker vs baseline comparison.

Uses the installed coding_mvge agent with Seeker rune and OpenRouter realm.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mvgeos_agent.harness.compaction import CompactionSettings  # noqa: E402
from mvgeos_agent.mvge import Mvge  # noqa: E402

from .config import EvalConfig, TaskResult, load_tasks  # noqa: E402

SEEKER_META = ["tool_search", "skill_search", "skill_execute", "mcp_search"]

# Runes whose background Sigils are detached during eval runs. They fire
# extra LLM calls per turn (consolidation) and persist traces into the
# agent's real store. Detached in BOTH modes equally, so the comparison
# stays fair while runs stay fast, cheap, and side-effect free.
BACKGROUND_RUNES = ("skill_evolution",)


class DistractorSpell:
    """Placeholder for distractors - we'll use the real agent's spells."""

    pass


def detach_background_runes(runner: Any) -> int:
    """Remove background-rune Sigils from a loaded runner (eval only).

    Uses RuneRunner internals; never ship this in product code. Returns
    the number of handler registrations removed.
    """
    removed = 0
    owned = getattr(runner, "_rune_handlers", {}) or {}
    sigils = getattr(runner, "_sigil_handlers", {}) or {}
    for rune_name in BACKGROUND_RUNES:
        for hook, handlers in owned.get(rune_name, {}).items():
            registered = sigils.get(hook, [])
            for handler in list(handlers):
                while handler in registered:
                    registered.remove(handler)
                    removed += 1
    return removed


async def run_single_task(
    task: dict[str, Any],
    config: EvalConfig,
    mode: str,
    tmp_base: Path,
) -> TaskResult:
    """Run a task in baseline or seeker mode using the installed coding_mvge agent."""
    task_id = task["task_id"]
    start_time = time.perf_counter()

    # Set up test files
    test_dir = tmp_base / task_id
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    for rel_path, content in task.get("setup", {}).get("files", {}).items():
        file_path = test_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    # Use the installed coding_mvge agent with its spells and runes.
    # Agent auto-discovers spells from its spells/ dir and runes
    # from ~/.agents/extensions/.
    compaction_settings = (
        CompactionSettings(enabled=True)
        if config.compaction_enabled
        else CompactionSettings(enabled=False, reserve_mana=0, keep_recent_mana=0)
    )
    agent = Mvge(
        api_key=config.api_key(),
        name="coding_mvge",
        provider_name=config.provider_name,
        compaction=compaction_settings,
    )
    # Mvge takes no model_id constructor arg (model comes from the agent
    # environment); override pre-initialize so MVGEOS_EVAL_MODEL applies.
    # Eval-only; product code must not touch this private.
    agent._model_id = config.model_id

    # For baseline mode, we need to disable the Seeker global allowlist
    # so all spells are visible. The agent loads runes during initialize().
    await agent.initialize()

    # Get the runner to manipulate active spells / allowlist
    runner = agent._runner

    # Detach background Sigils (harvest/consolidate) in both modes:
    # equal treatment, no extra LLM spend, no writes into the real store.
    if runner is not None:
        detached = detach_background_runes(runner)
        print(f"    Detached {detached} background Sigil(s)")

    if mode == "seeker":
        # Seeker mode: only 4 meta-tools visible
        if runner is not None:
            runner.set_active_spells(list(SEEKER_META), rune_name="seeker")
            runner.set_global_spell_allowlist(list(SEEKER_META))
    else:
        # Baseline mode: disable global allowlist so all spells visible
        if runner is not None:
            runner.set_global_spell_allowlist(None)

    # Build the prompt. Task text identical across modes; only the
    # tool-access framing differs (the independent variable).
    success_criteria = task.get("success_criteria", "")
    if mode == "seeker":
        access_framing = (
            "You start with only discovery meta-tools. First cast "
            "tool_search with an operation and target describing what you "
            "need; then cast the discovered spells to do the work."
        )
    else:
        access_framing = (
            "You have direct access to file operation tools. Cast them to do the work."
        )
    prompt = (
        f"Task: {task['description']}\n\n"
        f"Working directory: {test_dir}\n\n"
        f"{success_criteria}\n\n"
        f"{access_framing} Complete the task and "
        "report your result clearly."
    )

    success = False
    error = None
    tools_called: list[str] = []
    tool_call_count = 0
    final_output = ""
    turns = 0
    mana_used = 0

    try:
        # Run the task
        invocation = await agent.run(prompt)

        state = agent._state
        transcript: list[dict[str, Any]] = []
        if state is not None:
            turns = len([i for i in state.invocations if hasattr(i, "role")])
            mana_used = (
                getattr(agent, "mana_used", None) or getattr(state, "mana_used", 0) or 0
            )

            # Extract tools called from invocations + transcript preview
            for inv in state.invocations:
                role = getattr(inv, "role", "?")
                kinds: list[str] = []
                content = getattr(inv, "content", None)
                if content:
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type", "?")
                            kinds.append(str(btype))
                            if btype == "spell_cast":
                                sc = block.get("spell_cast", {})
                                tools_called.append(sc.get("name", "unknown"))
                                tool_call_count += 1
                            elif btype == "text":
                                kinds.append(block.get("text", "")[:120])
                transcript.append({"role": role, "kinds": kinds})
        else:
            turns = 0
            mana_used = 0

        final_output = ""
        if hasattr(invocation, "content") and invocation.content:
            for block in invocation.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    final_output += block.get("text", "")

        # Check success based on ground truth
        success = check_success(task, final_output, test_dir)

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        with contextlib.suppress(Exception):
            await agent.close()

    wall_time = time.perf_counter() - start_time

    return TaskResult(
        task_id=task_id,
        mode=mode,
        success=success,
        error=error,
        turns=turns,
        mana_used=mana_used,
        wall_time_seconds=wall_time,
        tools_called=tools_called,
        tool_call_count=tool_call_count,
        final_output=final_output[:5000],  # Truncate for storage
    )


def check_success(task: dict[str, Any], output: str, test_dir: Path) -> bool:
    """Check if the model's output satisfies the task's ground truth."""
    gt = task.get("ground_truth", {})
    task_id = task["task_id"]

    output_lower = output.lower()

    if task_id == "file_read_basic":
        expected = gt.get("expected_content_start", "").lower()
        return expected in output_lower

    elif task_id == "file_write_readback":
        expected = gt.get("expected_readback", "")
        return expected in output

    elif task_id == "directory_listing":
        expected_count = gt.get("expected_file_count", 0)
        expected_names = gt.get("expected_names", [])
        count_ok = str(expected_count) in output
        names_ok = all(name in output for name in expected_names)
        return count_ok and names_ok

    elif task_id == "code_search_function":
        expected_sig = gt.get("expected_signature", "").lower()
        return expected_sig.lower() in output_lower

    elif task_id == "code_search_class_method":
        expected_body = gt.get("expected_body_contains", "").lower()
        return expected_body in output_lower

    elif task_id == "grep_pattern_search":
        expected_count = gt.get("expected_count", 0)
        return str(expected_count) in output

    elif task_id == "multi_step_synthesis":
        expected_revenue = gt.get("total_revenue", 0)
        expected_expenses = gt.get("total_expenses", 0)
        expected_profit = gt.get("net_profit", 0)
        return (
            str(expected_revenue) in output
            and str(expected_expenses) in output
            and str(expected_profit) in output
        )

    elif task_id == "file_modification":
        expected = gt.get("expected_result", "")
        return expected in output

    elif task_id == "json_manipulation":
        expected = str(gt.get("expected_answer", 0))
        return expected in output

    elif task_id == "recursive_file_search":
        expected_count = gt.get("expected_count", 0)
        expected_names = gt.get("expected_names", [])
        count_ok = str(expected_count) in output
        names_ok = all(name in output for name in expected_names)
        return count_ok and names_ok

    if gt:
        return any(str(v).lower() in output_lower for v in gt.values() if v)

    return False


async def run_evaluation(
    config: EvalConfig,
    tasks: list[str] | None = None,
    modes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run the full evaluation suite."""
    all_tasks = load_tasks()
    if tasks:
        wanted = set(tasks)
        selected = [t for t in all_tasks if t["task_id"] in wanted]
        missing = wanted - {t["task_id"] for t in selected}
        if missing:
            raise ValueError(f"Unknown task IDs: {sorted(missing)}")
        all_tasks = selected
    run_modes = list(modes) if modes else ["baseline", "seeker"]
    results: list[dict[str, Any]] = []

    tmp_base = Path(__file__).parent / "tmp_eval"
    tmp_base.mkdir(exist_ok=True)

    for task in all_tasks:
        task_id = task["task_id"]
        print(f"\n{'=' * 60}")
        print(f"Task: {task_id} ({task['category']})")
        print(f"{'=' * 60}")

        for mode in run_modes:
            print(f"\n  Mode: {mode}...")
            try:
                result = await asyncio.wait_for(
                    run_single_task(task, config, mode, tmp_base),
                    timeout=config.timeout_seconds,
                )
            except TimeoutError:
                print(f"    TIMEOUT after {config.timeout_seconds}s")
                result = TaskResult(
                    task_id=task_id,
                    mode=mode,
                    success=False,
                    error=f"timeout after {config.timeout_seconds}s",
                    turns=0,
                    mana_used=0,
                    wall_time_seconds=float(config.timeout_seconds),
                    tools_called=[],
                    tool_call_count=0,
                    final_output="",
                )
            print(f"    Success: {result.success}")
            time_str = f"{result.wall_time_seconds:.1f}s"
            mana_str = f"Mana: {result.mana_used}"
            turns_str = f"    Turns: {result.turns}, {mana_str}, Time: {time_str}"
            print(turns_str)
            tools_called = result.tools_called
            tools_str = ", ".join(set(tools_called)) if tools_called else "none"
            print(f"    Tools called: {result.tool_call_count} ({tools_str})")
            if result.error:
                print(f"    Error: {result.error}")

            results.append(asdict(result))

            # Small delay between runs to avoid rate limits
            await asyncio.sleep(2)

    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seeker vs baseline live eval")
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help="Task IDs to run (default: all).",
    )
    parser.add_argument(
        "--modes",
        nargs="*",
        default=None,
        choices=["baseline", "seeker"],
        help="Modes to run (default: both).",
    )
    args = parser.parse_args()

    config = EvalConfig.from_env()
    print(f"Model: {config.model_id}")
    print(f"Temperature: {config.temperature}")
    print(f"Max turns: {config.max_turns}")
    if args.tasks:
        print(f"Tasks: {args.tasks}")
    if args.modes:
        print(f"Modes: {args.modes}")

    results = asyncio.run(run_evaluation(config, tasks=args.tasks, modes=args.modes))

    # Save results
    output_file = Path(__file__).parent / f"results_{int(time.time())}.json"
    with output_file.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    by_mode: dict[str, dict[str, Any]] = {}
    for r in results:
        mode = r["mode"]
        if mode not in by_mode:
            by_mode[mode] = {
                "success": 0,
                "total": 0,
                "mana": 0,
                "turns": 0,
                "time": 0.0,
            }
        by_mode[mode]["total"] += 1
        by_mode[mode]["mana"] += r["mana_used"]
        by_mode[mode]["turns"] += r["turns"]
        by_mode[mode]["time"] += r["wall_time_seconds"]
        if r["success"]:
            by_mode[mode]["success"] += 1

    for mode, stats in by_mode.items():
        total = stats["total"]
        print(f"\n{mode.upper()}:")
        rate = stats["success"] / total * 100
        print(f"  Success rate: {stats['success']}/{total} ({rate:.1f}%)")
        print(f"  Avg mana: {stats['mana'] / total:.0f}")
        print(f"  Avg turns: {stats['turns'] / total:.1f}")
        print(f"  Avg time: {stats['time'] / total:.1f}s")


if __name__ == "__main__":  # pragma: no cover
    main()
