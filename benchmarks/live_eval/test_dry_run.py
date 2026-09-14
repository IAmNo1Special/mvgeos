# ruff: noqa: T201
"""Dry-run test for live evaluation — verifies task setup without API calls."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from benchmarks.live_eval.config import load_tasks
from benchmarks.live_eval.runner import DistractorSpell, check_success


def test_task_loading() -> None:
    tasks = load_tasks()
    assert len(tasks) == 10
    categories = {t["category"] for t in tasks}
    assert categories == {"file_ops", "code_search", "synthesis"}
    print(f"Loaded {len(tasks)} tasks across {len(categories)} categories")


def test_task_setup() -> None:
    tasks = load_tasks()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_base = Path(tmp)
        for task in tasks:
            test_dir = tmp_base / task["task_id"]
            test_dir.mkdir(parents=True)
            for rel_path, content in task.get("setup", {}).get("files", {}).items():
                file_path = test_dir / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
                assert file_path.read_text() == content
    print("All task file setups verified")


def test_ground_truth_checks() -> None:
    tasks = load_tasks()
    for task in tasks:
        # Each task should have ground truth
        assert "ground_truth" in task
        assert task["ground_truth"]
        # Success criteria should exist
        assert "success_criteria" in task
        assert task["success_criteria"]
    print("All tasks have ground truth and success criteria")


def test_spell_definitions() -> None:
    # DistractorSpell is a placeholder - real spells come from coding_mvge agent
    distractors = [DistractorSpell() for _ in range(10)]
    assert len(distractors) == 10
    print("Distractor spells: 10 (placeholder)")


def test_check_success_basic() -> None:
    # Create a mock output that should pass
    tasks = load_tasks()
    task = next(t for t in tasks if t["task_id"] == "file_read_basic")

    with tempfile.TemporaryDirectory() as tmp:
        test_dir = Path(tmp) / task["task_id"]
        test_dir.mkdir(parents=True)
        (test_dir / "test_data" / "sample.txt").parent.mkdir(parents=True)
        (test_dir / "test_data" / "sample.txt").write_text(
            "This is a sample file for testing file read operations."
        )

        output = (
            "The file starts with: This is a sample file for testing "
            "file read operations."
        )
        result = check_success(task, output, test_dir)
        assert result is True, f"Expected True for valid output, got {result}"

        bad_output = "The file contains something else entirely."
        result = check_success(task, bad_output, test_dir)
        assert result is False, f"Expected False for invalid output, got {result}"

    print("check_success logic verified")


if __name__ == "__main__":  # pragma: no cover
    test_task_loading()
    test_task_setup()
    test_ground_truth_checks()
    test_spell_definitions()
    test_check_success_basic()
    print("\nAll dry-run tests passed!")
