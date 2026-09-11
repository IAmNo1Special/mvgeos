from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mvgeos_runes.installer import DEFAULT_MARKETPLACE_URL, install_rune


def _create_mock_rune_dir(
    path: Path, name: str, python_deps: list[str] | None = None
) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "name": name,
        "version": "1.0.0",
        "description": f"Test rune {name}",
        "entry_point": "main.py",
    }
    if python_deps is not None:
        manifest_data["python_deps"] = python_deps
    (path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    (path / "main.py").write_text("# entry point\n", encoding="utf-8")
    return path


def test_install_rune_empty_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Rune source cannot be empty"):
        install_rune("", target_dir=tmp_path)


def test_install_rune_local_path(tmp_path: Path) -> None:
    source_dir = tmp_path / "my_local_rune"
    _create_mock_rune_dir(source_dir, "my_local_rune")

    target_dir = tmp_path / "extensions"
    dest = install_rune(str(source_dir), target_dir=target_dir)

    assert dest == target_dir / "my_local_rune"
    assert (dest / "manifest.json").is_file()
    assert (dest / "main.py").is_file()


def test_install_rune_git_url(tmp_path: Path) -> None:
    target_dir = tmp_path / "extensions"
    git_url = "https://github.com/org/sample-rune.git"

    def fake_git_clone(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:2] == ["git", "clone"]:
            dest_dir = Path(cmd[3])
            _create_mock_rune_dir(dest_dir, "sample-rune")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_git_clone) as mock_run:
        dest = install_rune(git_url, target_dir=target_dir)

    assert dest == target_dir / "sample-rune"
    assert (dest / "manifest.json").is_file()
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][:2] == ["git", "clone"]


def test_install_rune_marketplace_success(tmp_path: Path) -> None:
    target_dir = tmp_path / "extensions"
    marketplace_payload = {
        "runes": {
            "openrouter-realm": {
                "name": "openrouter-realm",
                "git": "https://github.com/IAmNo1Special/openrouter-realm.git",
                "description": "OpenRouter provider realm",
            }
        }
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = marketplace_payload
    mock_resp.raise_for_status = MagicMock()

    def fake_git_clone(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:2] == ["git", "clone"]:
            dest_dir = Path(cmd[3])
            _create_mock_rune_dir(dest_dir, "openrouter-realm")
        return MagicMock(returncode=0)

    with (
        patch("httpx.get", return_value=mock_resp) as mock_get,
        patch("subprocess.run", side_effect=fake_git_clone) as mock_subproc,
    ):
        dest = install_rune("openrouter-realm", target_dir=target_dir)

    assert dest == target_dir / "openrouter-realm"
    assert (dest / "manifest.json").is_file()
    mock_get.assert_called_once_with(DEFAULT_MARKETPLACE_URL, timeout=15.0)
    mock_subproc.assert_called_once()


def test_install_rune_marketplace_with_subpath_success(tmp_path: Path) -> None:
    target_dir = tmp_path / "extensions"
    marketplace_payload = {
        "runes": {
            "openrouter-realm": {
                "name": "openrouter-realm",
                "git": "https://github.com/IAmNo1Special/mvgeos-marketplace.git",
                "path": "runes/openrouter-realm",
                "description": "OpenRouter provider realm",
            }
        }
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = marketplace_payload
    mock_resp.raise_for_status = MagicMock()

    def fake_git_clone(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:2] == ["git", "clone"]:
            clone_target = Path(cmd[-1])
            _create_mock_rune_dir(
                clone_target / "runes" / "openrouter-realm", "openrouter-realm"
            )
        return MagicMock(returncode=0)

    with (
        patch("httpx.get", return_value=mock_resp) as mock_get,
        patch("subprocess.run", side_effect=fake_git_clone) as mock_subproc,
    ):
        dest = install_rune("openrouter-realm", target_dir=target_dir)

    assert dest == target_dir / "openrouter-realm"
    assert (dest / "manifest.json").is_file()
    assert (dest / "main.py").is_file()
    mock_get.assert_called_once_with(DEFAULT_MARKETPLACE_URL, timeout=15.0)
    mock_subproc.assert_called_once()
    called_cmd = mock_subproc.call_args[0][0]
    assert called_cmd[:4] == ["git", "clone", "--depth", "1"]


def test_install_rune_marketplace_not_found(tmp_path: Path) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"runes": {}}
    mock_resp.raise_for_status = MagicMock()

    with (
        patch("httpx.get", return_value=mock_resp),
        pytest.raises(ValueError, match="Rune 'unknown-rune' not found in marketplace"),
    ):
        install_rune("unknown-rune", target_dir=tmp_path)


def test_install_rune_marketplace_fetch_error(tmp_path: Path) -> None:
    with (
        patch("httpx.get", side_effect=httpx.RequestError("Connection failed")),
        pytest.raises(ValueError, match="Failed to fetch marketplace index"),
    ):
        install_rune("openrouter-realm", target_dir=tmp_path)


def test_install_rune_missing_manifest_raises_error(tmp_path: Path) -> None:
    source_dir = tmp_path / "invalid_rune"
    source_dir.mkdir()
    (source_dir / "some_code.py").write_text("# code\n", encoding="utf-8")

    target_dir = tmp_path / "extensions"
    with pytest.raises(ValueError, match="Invalid rune: manifest.json missing"):
        install_rune(str(source_dir), target_dir=target_dir)


def test_install_rune_executes_python_deps(tmp_path: Path) -> None:
    source_dir = tmp_path / "rune_with_deps"
    _create_mock_rune_dir(
        source_dir, "rune_with_deps", python_deps=["fastapi>=0.100.0", "pydantic>=2.0"]
    )

    target_dir = tmp_path / "extensions"
    with patch("subprocess.run") as mock_subproc:
        dest = install_rune(str(source_dir), target_dir=target_dir)

    assert dest == target_dir / "rune_with_deps"
    mock_subproc.assert_called_once_with(
        ["uv", "pip", "install", "fastapi>=0.100.0", "pydantic>=2.0"],
        check=True,
        capture_output=True,
        text=True,
    )
