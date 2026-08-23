import pytest

from mvgeos_agent.sandbox import MvgeSandbox
from mvgeos_agent.types import SandboxTimeoutError


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
    result = s.execute_code("a = 10", timeout_seconds=2.0)
    assert result["a"] == 10


def test_execute_code_forbidden_raises() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.execute_code("import subprocess", timeout_seconds=1.0)


def test_execute_code_timeout() -> None:
    s = MvgeSandbox()
    with pytest.raises(SandboxTimeoutError):
        s.execute_code("while True: pass", timeout_seconds=0.3)
