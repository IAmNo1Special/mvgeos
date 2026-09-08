from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from mvgeos_agent.auth import (
    AUTH_DIR_PERMS,
    AUTH_FILE_PERMS,
    enforce_file_permissions,
    load_api_key_from_auth,
    save_api_key_to_auth,
)


def test_auth_permission_constants() -> None:
    assert AUTH_FILE_PERMS == 0o600
    assert AUTH_DIR_PERMS == 0o700


def test_load_api_key_from_auth_file_not_found(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    with patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_load_api_key_from_auth_valid_key(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text(
        json.dumps({"api_key": "sk-or-v1-valid-key"}), encoding="utf-8"
    )
    with patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() == "sk-or-v1-valid-key"


def test_load_api_key_from_auth_corrupt_json(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text("invalid json content {{{", encoding="utf-8")
    with patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_load_api_key_from_auth_non_string_key(tmp_path: Path) -> None:
    fake_path = tmp_path / "openrouter.json"
    fake_path.write_text(json.dumps({"api_key": 12345}), encoding="utf-8")
    with patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path):
        assert load_api_key_from_auth() is None


def test_save_api_key_to_auth(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    with patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path):
        res_path = save_api_key_to_auth("sk-or-v1-saved-key")
        assert res_path == fake_path
        assert fake_path.exists()
        data = json.loads(fake_path.read_text(encoding="utf-8"))
        assert data == {"api_key": "sk-or-v1-saved-key"}


def test_save_api_key_to_auth_permissions_posix(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    with (
        patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path),
        patch("os.name", "posix"),
        patch.object(Path, "chmod") as mock_chmod,
    ):
        save_api_key_to_auth("sk-or-v1-saved-key")
        mock_chmod.assert_any_call(0o700)
        mock_chmod.assert_any_call(0o600)


def test_save_api_key_to_auth_uses_secure_os_open(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    real_open = os.open
    open_modes: list[int] = []

    def tracking_open(
        file: str | bytes | int | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
    ) -> int:
        open_modes.append(mode)
        return real_open(file, flags, mode)

    with (
        patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path),
        patch("os.open", side_effect=tracking_open),
    ):
        save_api_key_to_auth("sk-or-v1-saved-key")
        assert 0o600 in open_modes


def test_load_api_key_from_auth_enforces_permissions_posix(tmp_path: Path) -> None:
    fake_path = tmp_path / "auth" / "openrouter.json"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_text(
        json.dumps({"api_key": "sk-or-v1-posix-key"}), encoding="utf-8"
    )
    with (
        patch("mvgeos_agent.auth.AUTH_FILE_PATH", fake_path),
        patch("os.name", "posix"),
        patch("mvgeos_agent.auth.enforce_file_permissions") as mock_enforce,
    ):
        key = load_api_key_from_auth()
        assert key == "sk-or-v1-posix-key"
        mock_enforce.assert_called_once_with(fake_path)


def test_enforce_file_permissions_posix(tmp_path: Path) -> None:
    fake_dir = tmp_path / "auth"
    fake_dir.mkdir(parents=True, exist_ok=True)
    fake_file = fake_dir / "openrouter.json"
    fake_file.write_text("{}", encoding="utf-8")

    with (
        patch("os.name", "posix"),
        patch.object(Path, "chmod") as mock_chmod,
    ):
        enforce_file_permissions(fake_file, mode=0o600, dir_mode=0o700)
        mock_chmod.assert_any_call(0o700)
        mock_chmod.assert_any_call(0o600)


def test_enforce_file_permissions_nt_noop(tmp_path: Path) -> None:
    fake_file = tmp_path / "openrouter.json"
    fake_file.write_text("{}", encoding="utf-8")
    with (
        patch("os.name", "nt"),
        patch.object(Path, "chmod") as mock_chmod,
    ):
        enforce_file_permissions(fake_file)
        mock_chmod.assert_not_called()


def test_enforce_file_permissions_suppresses_oserror(tmp_path: Path) -> None:
    fake_file = tmp_path / "openrouter.json"
    fake_file.write_text("{}", encoding="utf-8")
    with (
        patch("os.name", "posix"),
        patch.object(Path, "chmod", side_effect=OSError("Chmod failed")),
    ):
        enforce_file_permissions(fake_file)
