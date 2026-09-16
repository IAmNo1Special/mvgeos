"""MvgeOS host sandbox executor for process isolation and AST safety.

Trust model (read this before relying on it):

- This sandbox is **best-effort containment, not a security boundary**.
- It runs code in a spawned subprocess with a timeout and a restricted
  builtins set, and it rejects obviously dangerous syntax via an AST
  denylist. A determined adversary can still escape it (for example through
  standard-library modules the denylist does not cover).
- For anything security-sensitive, pass an explicit ``allowed_modules``
  allowlist: when provided, *every* import not on the list is rejected, both
  at AST-validation time and at runtime.
- Do not execute genuinely hostile code here. Treat this sandbox as a guard
  against accidents and casual misuse, not as isolation.
"""

import ast
import builtins
import multiprocessing
import types
import warnings
from typing import Any, cast


class SandboxTimeoutError(Exception):
    """Raised when sandbox code execution exceeds the timeout threshold."""


FORBIDDEN_NAMES = {
    "os",
    "sys",
    "subprocess",
    "eval",
    "exec",
    "open",
    "__import__",
    "builtins",
}


class ASTSafetyVisitor(ast.NodeVisitor):
    """AST visitor to verify safe syntax before execution."""

    def __init__(self, allowed_modules: set[str] | None = None) -> None:
        """Initializes ASTSafetyVisitor.

        Args:
            allowed_modules: Optional allowlist of importable top-level
                module names. When provided, any import not on the list is
                rejected. When omitted, the legacy denylist applies.
        """
        self.allowed_modules = allowed_modules

    def visit_Import(self, node: ast.Import) -> None:
        """Validates import statements against the module policy.

        Args:
            node: AST import node.

        Raises:
            ValueError: If an import statement targets a forbidden module.
        """
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if self.allowed_modules is not None:
                if base_mod not in self.allowed_modules:
                    raise ValueError(
                        f"Forbidden import: '{alias.name}' is not in allowed_modules."
                    )
            elif base_mod == "sys" or base_mod in FORBIDDEN_NAMES:
                raise ValueError(f"Forbidden AST node: import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Validates from-import statements against the module policy.

        Args:
            node: AST import-from node.

        Raises:
            ValueError: If a from-import statement targets a forbidden module.
        """
        if node.module:
            base_mod = node.module.split(".")[0]
            if self.allowed_modules is not None:
                if base_mod not in self.allowed_modules:
                    raise ValueError(
                        f"Forbidden import: 'from {node.module} import ...' "
                        "is not in allowed_modules."
                    )
            elif base_mod == "sys" or base_mod in FORBIDDEN_NAMES:
                raise ValueError(f"Forbidden AST node: from {node.module} import ...")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Blocks dunder attribute access (e.g. ``().__class__``).

        Args:
            node: AST attribute node.

        Raises:
            ValueError: If the attribute is a dunder name.
        """
        if node.attr.startswith("__") and node.attr.endswith("__"):
            raise ValueError(f"Forbidden dunder attribute access: {node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Validates function call nodes against forbidden functions.

        Args:
            node: AST call node.

        Raises:
            ValueError: If a call targets a forbidden function.
        """
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden function: {node.func.id}")
        self.generic_visit(node)


def _sandbox_process_target(
    code_str: str,
    context_globals: dict[str, Any] | None,
    queue: Any,
    allowed_modules: set[str] | None = None,
) -> None:
    """Target function executed inside isolated subprocess.

    Args:
        code_str: Code payload string.
        context_globals: Optional execution context globals.
        queue: Multiprocessing inter-process communication queue.
        allowed_modules: Optional set of allowed module names.
    """
    try:
        executor = MvgeSandbox()
        local_vars = executor._execute_sync(
            code_str, context_globals, allowed_modules=allowed_modules
        )
        serializable_vars = {
            k: v for k, v in local_vars.items() if not isinstance(v, types.ModuleType)
        }
        queue.put(("success", serializable_vars))
    except Exception as exc:
        queue.put(("error", str(exc)))


class MvgeSandbox:
    """MvgeOS host sandbox executor with AST validation and hard timeout termination.

    Best-effort containment, not a security boundary: pass an explicit
    ``allowed_modules`` allowlist to ``execute_code`` for anything
    security-sensitive. See the module docstring for the trust model.
    """

    def validate_ast(
        self, code_str: str, allowed_modules: set[str] | None = None
    ) -> ast.AST:
        """Parses and validates AST safety for code string.

        Args:
            code_str: Python code string.
            allowed_modules: Optional allowlist of importable top-level
                module names. When provided, any import not on the list is
                rejected. When omitted, the legacy denylist applies.

        Returns:
            Parsed AST module.

        Raises:
            ValueError: If AST contains unsafe nodes or calls.
        """
        parsed = ast.parse(code_str)
        visitor = ASTSafetyVisitor(allowed_modules=allowed_modules)
        visitor.visit(parsed)
        return parsed

    def _execute_sync(
        self,
        code_str: str,
        context_globals: dict[str, Any] | None,
        allowed_modules: set[str] | None = None,
    ) -> dict[str, Any]:
        """Synchronously executes code within safe builtins dict.

        Args:
            code_str: Python code string.
            context_globals: Global variable definitions.
            allowed_modules: Optional allowlist of importable top-level
                module names. When provided, any import not on the list is
                rejected at runtime as well as at AST-validation time.

        Returns:
            Resulting local variables dictionary.
        """
        self.validate_ast(code_str, allowed_modules=allowed_modules)

        def safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
            base_mod = name.split(".")[0]
            if allowed_modules is not None:
                if base_mod not in allowed_modules:
                    raise ValueError(
                        f"Forbidden import: '{name}' is not in allowed_modules."
                    )
            elif base_mod == "sys" or base_mod in FORBIDDEN_NAMES:
                raise ValueError(f"Import of module '{name}' is forbidden.")
            return builtins.__import__(name, *args, **kwargs)

        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "set": set,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "True": True,
            "False": False,
            "None": None,
            "__import__": safe_import,
        }
        exec_globals = {"__builtins__": safe_builtins}
        if context_globals:
            exec_globals.update(context_globals)
        local_vars: dict[str, Any] = {}
        exec(code_str, exec_globals, local_vars)
        return local_vars

    def execute_code(
        self,
        code_str: str,
        context_globals: dict[str, Any] | None = None,
        timeout_seconds: float = 5.0,
        allowed_modules: set[str] | None = None,
    ) -> dict[str, Any]:
        """Executes code in isolated subprocess with timeout enforcement.

        Args:
            code_str: Code string to execute.
            context_globals: Optional globals dictionary.
            timeout_seconds: Timeout limit in seconds.
            allowed_modules: Optional allowlist of importable top-level
                module names. When provided, any import not on the list is
                rejected. When omitted, the legacy denylist applies and a
                warning is emitted: without an allowlist this sandbox is
                best-effort containment, not a security boundary.

        Returns:
            Dictionary of resulting local variables.

        Raises:
            SandboxTimeoutError: If execution exceeds timeout threshold.
            ValueError: If code execution fails or violates AST rules.
        """
        if allowed_modules is None:
            warnings.warn(
                "MvgeSandbox called without an allowed_modules allowlist: "
                "the sandbox is best-effort containment, not a security "
                "boundary. Pass allowed_modules={...} to restrict imports "
                "to an allowlist.",
                UserWarning,
                stacklevel=2,
            )
        self.validate_ast(code_str, allowed_modules=allowed_modules)
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        process = ctx.Process(
            target=_sandbox_process_target,
            args=(code_str, context_globals, queue, allowed_modules),
        )
        process.start()
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            process.terminate()
            process.join()
            raise SandboxTimeoutError(
                f"Code execution timed out after {timeout_seconds} seconds."
            )

        if not queue.empty():
            status, payload = queue.get()
            if status == "success":
                return cast(dict[str, Any], payload)
            if status == "error":
                raise ValueError(payload)

        return {}
