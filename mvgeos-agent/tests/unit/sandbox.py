import pytest
from mvgeos_core.sandbox import MvgeSandbox, SandboxTimeoutError


def test_validate_ast_allows_safe_code() -> None:
    s = MvgeSandbox()
    s.validate_ast("x = 1 + 2")


def test_validate_ast_forbids_import_os() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("import os")


def test_validate_ast_forbids_from_import() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("from os import path")


def test_validate_ast_allows_allowed_module() -> None:
    s = MvgeSandbox()
    s.validate_ast("import os", allowed_modules={"os"})


def test_validate_ast_forbids_call_eval() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("eval('1')")


def test_execute_sync_simple() -> None:
    s = MvgeSandbox()
    result = s._execute_sync("x = 1 + 2", None)
    assert result["x"] == 3


def test_execute_sync_with_context() -> None:
    s = MvgeSandbox()
    result = s._execute_sync("y = x + 1", {"x": 5})
    assert result["y"] == 6


def test_execute_code_success() -> None:
    s = MvgeSandbox()
    result = s.execute_code("a = 10", timeout_seconds=10.0)
    assert result["a"] == 10


def test_execute_code_forbidden_raises() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.execute_code("import subprocess", timeout_seconds=1.0)


def test_execute_code_timeout() -> None:
    s = MvgeSandbox()
    with pytest.raises(SandboxTimeoutError):
        s.execute_code("while True: pass", timeout_seconds=0.3)


def test_execute_code_runtime_error() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="division by zero"):
        s.execute_code("x = 1 / 0", timeout_seconds=5.0)


def test_execute_code_filters_modules() -> None:
    s = MvgeSandbox()
    result = s.execute_code(
        "import math\ny = math.sqrt(16)", allowed_modules={"math"}, timeout_seconds=5.0
    )
    assert result["y"] == 4.0
    assert "math" not in result


def test_execute_sync_safe_import_forbidden() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden AST node"):
        s._execute_sync("import os", None)


def test_validate_ast_forbids_dunder_attribute() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="dunder"):
        s.validate_ast("x = ().__class__")


def test_validate_ast_forbids_dunder_subclass_traversal() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="dunder"):
        s.validate_ast("x = ().__class__.__base__.__subclasses__()")


def test_validate_ast_allowlist_rejects_unlisted_import() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="allowed_modules"):
        s.validate_ast("import socket", allowed_modules={"math"})


def test_validate_ast_allowlist_rejects_unlisted_from_import() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="allowed_modules"):
        s.validate_ast("from pathlib import Path", allowed_modules={"math"})


def test_validate_ast_allowlist_permits_listed_import() -> None:
    s = MvgeSandbox()
    s.validate_ast("import math", allowed_modules={"math"})


def test_execute_code_warns_without_allowlist() -> None:
    s = MvgeSandbox()
    with pytest.warns(UserWarning, match="best-effort"):
        s.execute_code("a = 1", timeout_seconds=10.0)
