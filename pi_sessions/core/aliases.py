from __future__ import annotations

import json
from pathlib import Path

from .models import Project

DEFAULT_ALIASES_PATH = Path.home() / ".config" / "pi-sessions" / "aliases.json"


class ProjectAliases:
    """Cosmetic display names for projects, keyed by project directory name.

    Purely a pi-sessions-side overlay — nothing under ~/.pi is touched, so
    the default (path-derived) name is always recoverable by removing the
    alias. The directory name survives archiving (the directory moves, its
    name does not).
    """

    def __init__(self, path: Path = DEFAULT_ALIASES_PATH) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self._data = {
                k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)
            }

    def get(self, project: Project) -> str:
        return self._data.get(project.encoded_dir.name, "")

    def set(self, project: Project, alias: str) -> None:
        self._data[project.encoded_dir.name] = alias

    def remove(self, project: Project) -> None:
        self._data.pop(project.encoded_dir.name, None)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self.path)
        except OSError:
            pass

    def apply(self, projects: list[Project]) -> None:
        for p in projects:
            p.alias = self.get(p)
