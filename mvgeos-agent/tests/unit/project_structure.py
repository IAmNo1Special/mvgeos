from pathlib import Path


def test_no_init_py_in_test_directories() -> None:
    """Assert that no __init__.py file exists in any test directory across the monorepo.

    With pytest --import-mode=importlib, placing __init__.py in test directories
    causes test modules with identical relative paths across workspace packages
    (e.g., tests/unit/types.py) to shadow each other during collection.
    """
    root_dir = Path(__file__).resolve().parents[3]
    forbidden_files: list[Path] = []

    for test_dir in root_dir.glob("*/tests"):
        if test_dir.is_dir():
            for init_file in test_dir.rglob("__init__.py"):
                forbidden_files.append(init_file.relative_to(root_dir))

    assert not forbidden_files, (
        f"Found forbidden __init__.py in test directories: {forbidden_files}. "
        "Test directories must NOT contain __init__.py files."
    )
