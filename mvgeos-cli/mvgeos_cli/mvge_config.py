from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MvgeConfig(BaseModel):
    """Configuration for an Mvge agent instance."""

    name: str
    source_path: Path
    config: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class MvgeOSConfig(BaseModel):
    """Global MvgeOS configuration."""

    default_mvge: str = "default"
    mvges: dict[str, MvgeConfig] = Field(default_factory=dict)
    _config_path: Path = Path("~/.agents/.mvgeos/mvge.json").expanduser()

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def load(cls, config_path: Path) -> MvgeOSConfig:
        """Load config from file, creating default if not exists."""
        if not config_path.exists():
            config = cls()
        else:
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                config = cls(**data)
            except json.JSONDecodeError, OSError:
                config = cls()
        config._config_path = config_path
        return config

    def save(self, config_path: Path) -> None:
        """Save config to file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Convert Path objects to strings for JSON serialization
        data = self.model_dump(mode="json")
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def ensure_default_mvge(self, source_path: Path) -> Path:
        """Ensure default mvge exists, installing from source if needed."""
        default_name = self.default_mvge
        if default_name not in self.mvges:
            # Install default mvge from source
            mvge_dir = Path("~/.agents/.mvgeos/mvges/default").expanduser()
            mvge_dir.parent.mkdir(parents=True, exist_ok=True)
            if not mvge_dir.exists():
                shutil.copytree(source_path, mvge_dir, dirs_exist_ok=True)
            self.mvges[default_name] = MvgeConfig(
                name="default",
                source_path=Path("~/.agents/.mvgeos/mvges/default").expanduser(),
            )
            self.save(self._config_path)
        return Path(self.mvges[default_name].source_path).expanduser()


def get_mvgeos_config() -> MvgeOSConfig:
    """Load the global MvgeOS configuration."""
    config_path = Path("~/.agents/.mvgeos/mvge.json").expanduser()
    return MvgeOSConfig.load(config_path)


def ensure_default_mvge(source_path: Path) -> Path:
    """Ensure default mvge is installed and return its path."""
    config = get_mvgeos_config()
    return config.ensure_default_mvge(Path(source_path))
