from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import typer

from mvgeos_cli.auth import (
    load_api_key_from_auth,
    prompt_api_key,
    save_api_key_to_auth,
)


def test_load_api_key_from_auth_file_not_found(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    with patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_load_api_key_from_auth_valid_key(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text(
        json.dumps({"api_key": "sk-or-v1-valid-key"}), encoding="utf-8"
    )
    with patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() == "sk-or-v1-valid-key"


def test_load_api_key_from_auth_corrupt_json(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text("invalid json content {{{", encoding="utf-8")
    with patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_load_api_key_from_auth_non_string_key(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text(json.dumps({"api_key": 12345}), encoding="utf-8")
    with patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_save_api_key_to_auth(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    with patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path):
        res_path = save_api_key_to_auth("sk-or-v1-saved-key")
        assert res_path == fake_path
        assert fake_path.exists()
        data = json.loads(fake_path.read_text(encoding="utf-8"))
        assert data == {"api_key": "sk-or-v1-saved-key"}


def test_save_api_key_to_auth_permissions_posix(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    with (
        patch("mvgeos_cli.auth.AUTH_FILE_PATH", fake_path),
        patch("os.name", "posix"),
        patch.object(Path, "chmod") as mock_chmod,
    ):
        save_api_key_to_auth("sk-or-v1-saved-key")
        mock_chmod.assert_called_once_with(0o600)


def test_prompt_api_key_success() -> None:
    with patch("typer.prompt", return_value="  sk-or-v1-input-key  "):
        key = prompt_api_key()
        assert key == "sk-or-v1-input-key"


def test_prompt_api_key_keyboard_interrupt() -> None:
    with patch("typer.prompt", side_effect=KeyboardInterrupt):
        key = prompt_api_key()
        assert key is None


def test_prompt_api_key_typer_abort() -> None:
    with patch("typer.prompt", side_effect=typer.Abort):
        key = prompt_api_key()
        assert key is None


def test_prompt_api_key_eof_error() -> None:
    with patch("typer.prompt", side_effect=EOFError):
        key = prompt_api_key()
        assert key is None
