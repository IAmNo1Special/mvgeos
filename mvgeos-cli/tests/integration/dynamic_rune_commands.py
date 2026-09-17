from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mvgeos_cli.main import app


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def test_uninstalled_rune_command_not_in_help(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_global = tmp_path / "global_empty"
    empty_global.mkdir()
    monkeypatch.setenv("MVGEOS_GLOBAL_DIR", str(empty_global))

    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mock-cmd" not in result.output
    assert "mcp" not in result.output


def test_installed_rune_command_via_cli_py(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_dir = tmp_path / "global_agents"
    ext_dir = global_dir / "extensions" / "mock-rune"
    ext_dir.mkdir(parents=True)

    # 1. manifest.json
    manifest_data = {
        "name": "mock-rune",
        "version": "0.1.0",
        "description": "Mock extension",
        "commands": ["mock-cmd"],
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2), encoding="utf-8"
    )

    # 2. cli.py
    (ext_dir / "cli.py").write_text(
        "import typer\n"
        "app = typer.Typer(help='Mock rune commands')\n"
        "@app.command()\n"
        "def ping():\n"
        "    print('MOCK PING OK')\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("MVGEOS_GLOBAL_DIR", str(global_dir))

    # Test that --help shows the dynamic command
    help_res = cli_runner.invoke(app, ["--help"])
    assert help_res.exit_code == 0
    assert "mock-cmd" in help_res.output

    # Test executing the dynamic subcommand
    res = cli_runner.invoke(app, ["mock-cmd", "ping"])
    assert res.exit_code == 0
    assert "MOCK PING OK" in res.output


def test_installed_rune_command_via_rune_factory(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_dir = tmp_path / "global_agents"
    ext_dir = global_dir / "extensions" / "factory-rune"
    ext_dir.mkdir(parents=True)

    manifest_data = {
        "name": "factory-rune",
        "version": "0.1.0",
        "description": "Factory extension",
        "commands": ["factory-cmd"],
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2), encoding="utf-8"
    )

    (ext_dir / "rune.py").write_text(
        "def rune_factory(api):\n"
        "    def handler(args):\n"
        "        return f'FACTORY ECHO: {args}'\n"
        "    api.register_command(\n"
        "        'factory-cmd', description='Factory command', handler=handler\n"
        "    )\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("MVGEOS_GLOBAL_DIR", str(global_dir))

    res = cli_runner.invoke(app, ["factory-cmd", "hello-world"])
    assert res.exit_code == 0
    assert "FACTORY ECHO: hello-world" in res.output
