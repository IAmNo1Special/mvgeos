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


# Attribute-form targets. visit_Call used to match only bare ast.Name, so
# anything reached through an attribute - os.system, subprocess.run - sailed
# past the denylist even while the bare form was rejected.


def test_validate_ast_forbids_attribute_form_call() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("import os\nos.system('echo x')")


def test_validate_ast_forbids_attribute_form_call_without_import() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("os.system('echo x')")


def test_validate_ast_forbids_subprocess_attribute_form() -> None:
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("import subprocess\nsubprocess.run(['echo', 'x'])")


def test_validate_ast_forbids_allowlisted_module_attribute_form() -> None:
    """An allowlist entry must not hand back command execution.

    ``allowed_modules`` constrains which modules may be imported. Listing a
    forbidden module must not become the grant that makes ``os.system``
    reachable, which is how heal-my-goap's GOAP sandbox was defeated.
    """
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast(
            "import os\nos.system('echo x')",
            allowed_modules={"pathlib", "subprocess", "os", "urllib", "json", "re"},
        )


def test_validate_ast_forbids_environment_subscript_on_allowlisted_module() -> None:
    """Credential theft needs no call: ``os.environ[...]`` is a Subscript."""
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast(
            "import os\nleaked = os.environ['OPENROUTER_API_KEY']",
            allowed_modules={"os"},
        )


def test_execute_code_rejects_attribute_form_escape() -> None:
    """End-to-end: the escape must fail before the payload ever runs."""
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.execute_code(
            "import os\nos.system('echo x')",
            allowed_modules={"os", "subprocess"},
            timeout_seconds=5.0,
        )


def test_validate_ast_allows_import_of_allowlisted_forbidden_module() -> None:
    """The documented guarantee: the import passes, no use of it ever does.

    ``allowed_modules`` narrows the import surface. Listing ``os`` lets
    ``import os`` parse, but the module is unusable: attribute access rooted
    at ``os`` is refused at every site. Asserting both halves keeps the
    contract honest instead of implying the allow-list is a grant.
    """
    s = MvgeSandbox()
    s.validate_ast("import os", allowed_modules={"os"})
    for code in (
        "import os\nos.system('echo x')",
        "import os\nleaked = os.environ['OPENROUTER_API_KEY']",
    ):
        with pytest.raises(ValueError, match="Forbidden"):
            s.validate_ast(code, allowed_modules={"os"})


def test_validate_ast_hard_bans_sys_even_when_allowlisted() -> None:
    """sys defeats the restricted builtins; an allowlist must not re-grant it."""
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s.validate_ast("import sys", allowed_modules={"sys", "json"})


def test_execute_sync_hard_bans_sys_even_when_allowlisted() -> None:
    """The runtime import hook must agree with AST validation."""
    s = MvgeSandbox()
    with pytest.raises(ValueError, match="Forbidden"):
        s._execute_sync("import sys", None, allowed_modules={"sys", "json"})


def test_validate_ast_still_permits_allowed_non_forbidden_attribute_calls() -> None:
    """The fix must not blanket-ban attribute access."""
    s = MvgeSandbox()
    s.validate_ast(
        "import pathlib\np = pathlib.Path('/tmp/x')",
        allowed_modules={"pathlib"},
    )
