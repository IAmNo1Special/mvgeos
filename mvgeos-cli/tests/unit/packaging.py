"""Packaging contract: every third-party import is a declared dependency, and
every internal dependency is version-bounded.

The first test is a regression test for clean-install breakage: ``mvge`` failed
on a fresh install with ``ModuleNotFoundError: No module named 'dotenv'``
because ``mvgeos_agent`` imported it without declaring ``python-dotenv`` (and
the same for ``click`` in ``mvgeos_cli``). If the code imports it, ``pyproject``
must declare it.

The second test guards the published-wheel contract. ``[tool.uv.sources]
workspace = true`` never reaches wheel metadata -- ``uv_build`` copies
``[project.dependencies]`` verbatim -- so a bare internal name ships as an
unbounded ``Requires-Dist`` and floats to whatever sibling is newest on the
index. Nothing local fails when that happens; it only surfaces when a stranger
installs, which is exactly how these packages reached their first release.
"""

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from importlib.util import find_spec
from pathlib import Path


def _package_root() -> Path:
    # tests/unit/packaging.py -> <package>/
    return Path(__file__).resolve().parents[2]


def _declared_distributions() -> set[str]:
    pyproject = _package_root() / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    names: set[str] = set()
    for dep in data["project"]["dependencies"]:
        name = dep.strip()
        for sep in ("[", ";", "=", ">", "<", "!", "~"):
            name = name.split(sep)[0]
        names.add(name.strip().lower().replace("-", "_"))
    return names


def _third_party_imports() -> set[str]:
    src = _package_root() / "src"
    stdlib = sys.stdlib_module_names
    own = {p.name for p in src.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    found: set[str] = set()
    for py in sorted(src.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return {m for m in found if m not in stdlib and m not in own}


def test_all_third_party_imports_are_declared_dependencies() -> None:
    declared = _declared_distributions()
    provided: dict[str, set[str]] = {}
    for module, dists in packages_distributions().items():
        provided[module] = {d.lower().replace("-", "_") for d in dists}
    missing = sorted(
        mod
        for mod in _third_party_imports()
        if not _is_covered(mod, declared, provided)
    )
    assert not missing, (
        "third-party imports without a declared dependency in pyproject.toml: "
        + ", ".join(missing)
    )


def _is_covered(module: str, declared: set[str], provided: dict[str, set[str]]) -> bool:
    dists = provided.get(module)
    if dists is not None:
        return bool(dists & declared)
    # Editable workspace siblings carry no top_level metadata; they are
    # covered when the (normalized) distribution name is declared and the
    # module actually resolves in this environment.
    normalized = module.lower().replace("-", "_")
    return normalized in declared and find_spec(module) is not None


def _workspace_root() -> Path:
    # mvgeos-cli/tests/unit/packaging.py -> mvgeos-cli/ -> workspace root
    return _package_root().parent


def _member_directories(root: Path) -> list[Path]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    members = data["tool"]["uv"]["workspace"]["members"]
    return [root / member for member in members]


def _distribution_name(requirement: str) -> str:
    name = requirement.strip()
    for sep in ("[", ";", "=", ">", "<", "!", "~"):
        name = name.split(sep)[0]
    return name.strip().lower().replace("-", "_")


def test_internal_dependencies_are_version_bounded() -> None:
    root = _workspace_root()
    internal = {_distribution_name(p.name) for p in _member_directories(root)}
    internal.add(_distribution_name("mvgeos"))

    unbounded: list[str] = []
    for member in [*_member_directories(root), root]:
        data = tomllib.loads((member / "pyproject.toml").read_text(encoding="utf-8"))
        for requirement in data["project"]["dependencies"]:
            if _distribution_name(requirement) not in internal:
                continue
            if not any(op in requirement for op in ("=", ">", "<", "~", "!")):
                unbounded.append(f"{data['project']['name']}: {requirement.strip()}")

    assert not unbounded, (
        "internal dependencies without a version floor ship as an unbounded "
        "Requires-Dist and float to the newest sibling on the index: "
        + ", ".join(sorted(unbounded))
    )
