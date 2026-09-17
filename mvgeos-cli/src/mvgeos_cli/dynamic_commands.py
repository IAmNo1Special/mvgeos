from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
from pathlib import Path
from typing import Any, cast

import click
import typer
from mvgeos_runes.loader import _inject_rune_paths
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneManifest


def get_extension_dirs(
    cwd: Path | None = None,
    global_dir: Path | None = None,
) -> list[Path]:
    """Return all existing extension search directories in precedence order."""
    dirs: list[Path] = []

    # 1. Custom env var
    env_ext = os.environ.get("MVGEOS_EXTENSION_DIR")
    if env_ext:
        p = Path(env_ext).expanduser()
        if p.is_dir():
            dirs.append(p)

    # 2. Project-level: <cwd>/.agents/extensions/ and <cwd>/extensions/
    c_dir = cwd or Path.cwd()
    proj_dot_agents = c_dir / ".agents" / "extensions"
    if proj_dot_agents.is_dir():
        dirs.append(proj_dot_agents)

    proj_ext = c_dir / "extensions"
    if proj_ext.is_dir() and proj_ext not in dirs:
        dirs.append(proj_ext)

    # 3. User-level: ~/.agents/extensions/ (or MVGEOS_GLOBAL_DIR)
    g_env = global_dir or (
        Path(os.environ["MVGEOS_GLOBAL_DIR"])
        if os.environ.get("MVGEOS_GLOBAL_DIR")
        else Path("~/.agents").expanduser()
    )
    user_ext = g_env / "extensions"
    if user_ext.is_dir() and user_ext not in dirs:
        dirs.append(user_ext)

    return dirs


def discover_installed_rune_commands(
    cwd: Path | None = None,
    global_dir: Path | None = None,
) -> dict[str, tuple[Path, RuneManifest]]:
    """Scan extension directories and map command names to their parent rune."""
    cmd_map: dict[str, tuple[Path, RuneManifest]] = {}

    for ext_dir in get_extension_dirs(cwd=cwd, global_dir=global_dir):
        try:
            for child in ext_dir.iterdir():
                if not child.is_dir():
                    continue
                manifest = load_manifest(child)
                if manifest is None or not manifest.enabled:
                    continue
                for cmd in manifest.commands:
                    if cmd not in cmd_map:
                        cmd_map[cmd] = (child, manifest)
        except (OSError, PermissionError):
            continue

    return cmd_map


def load_rune_cli_command(
    cmd_name: str,
    cwd: Path | None = None,
    global_dir: Path | None = None,
) -> click.Command | None:
    """Dynamically mount a Click command from an installed rune."""
    cmd_map = discover_installed_rune_commands(cwd=cwd, global_dir=global_dir)
    if cmd_name not in cmd_map:
        return None

    rune_dir, manifest = cmd_map[cmd_name]
    entry = rune_dir / (manifest.entry_point or "rune.py")
    _inject_rune_paths(rune_dir, entry)

    # Strategy 1: Check cli.py
    cli_py = rune_dir / "cli.py"
    if cli_py.is_file():
        spec = importlib.util.spec_from_file_location(
            f"mvgeos_rune_cli_{manifest.name}", cli_py
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                for attr_name in (
                    "app",
                    "cli",
                    cmd_name,
                    cmd_name.replace("-", "_"),
                    f"{cmd_name}_app",
                    f"{cmd_name}_cli",
                    f"{cmd_name.replace('-', '_')}_app",
                    f"{cmd_name.replace('-', '_')}_cli",
                    "main",
                ):
                    if hasattr(mod, attr_name):
                        target = getattr(mod, attr_name)
                        if isinstance(target, typer.Typer):
                            if (
                                len(target.registered_commands) == 1
                                and not target.registered_groups
                                and not target.registered_callback
                            ):

                                @target.callback()
                                def _default_group_callback() -> None:
                                    pass

                            cmd_obj = typer.main.get_command(target)
                            cmd_obj.name = cmd_name
                            return cast(click.Command, cmd_obj)
                        if isinstance(target, click.Command):
                            target.name = cmd_name
                            return target
            except Exception:
                pass

    # Strategy 2: Check rune.py or rune_factory
    rune_py = rune_dir / (manifest.entry_point or "rune.py")
    if rune_py.is_file():
        spec = importlib.util.spec_from_file_location(
            f"mvgeos_rune_{manifest.name}", rune_py
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                # Check for click/typer command in rune.py
                for attr_name in (
                    "app",
                    "cli",
                    cmd_name,
                    cmd_name.replace("-", "_"),
                    f"{cmd_name}_app",
                    f"{cmd_name}_cli",
                    f"{cmd_name.replace('-', '_')}_app",
                    f"{cmd_name.replace('-', '_')}_cli",
                    "main",
                ):
                    if hasattr(mod, attr_name):
                        target = getattr(mod, attr_name)
                        if isinstance(target, typer.Typer):
                            if (
                                len(target.registered_commands) == 1
                                and not target.registered_groups
                                and not target.registered_callback
                            ):

                                @target.callback()
                                def _default_group_callback_rune() -> None:
                                    pass

                            cmd_obj = typer.main.get_command(target)
                            cmd_obj.name = cmd_name
                            return cast(click.Command, cmd_obj)
                        if isinstance(target, click.Command):
                            target.name = cmd_name
                            return target

                # Check rune_factory registering commands
                if hasattr(mod, "rune_factory"):
                    runner = RuneRunner()
                    api = RuneAPI(runner, rune_name=manifest.name)
                    factory_res = mod.rune_factory(api)
                    if inspect.iscoroutine(factory_res):
                        asyncio.run(factory_res)

                    for rc in runner.get_commands():
                        if rc.name == cmd_name:

                            @click.command(
                                name=cmd_name,
                                help=rc.description
                                or f"Execute {cmd_name} extension command",
                            )
                            @click.argument(
                                "extra_args", nargs=-1, type=click.UNPROCESSED
                            )
                            @click.pass_context
                            def _dynamic_cmd(
                                ctx: click.Context,
                                extra_args: tuple[str, ...],
                                _handler: Any = rc.handler,
                            ) -> None:
                                args_str = " ".join(extra_args)
                                if _handler is None:
                                    return
                                try:
                                    sig = inspect.signature(_handler)
                                    accepts = len(sig.parameters) > 0
                                except (ValueError, TypeError):
                                    accepts = True

                                if inspect.iscoroutinefunction(_handler):
                                    res = asyncio.run(
                                        _handler(args_str) if accepts else _handler()
                                    )
                                else:
                                    res = _handler(args_str) if accepts else _handler()
                                if res is not None:
                                    click.echo(str(res))

                            return _dynamic_cmd
            except Exception:
                pass

    return None
