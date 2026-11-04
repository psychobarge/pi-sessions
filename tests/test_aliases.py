from __future__ import annotations

import json
from pathlib import Path

from pi_sessions.core.aliases import ProjectAliases
from pi_sessions.core.models import Project

ENCODED = Path("/tmp/projects")


def _project(path: str, dirname: str = "") -> Project:
    return Project(project_path=path, encoded_dir=ENCODED / (dirname or path.replace("/", "-")))


def test_display_name_prefers_alias():
    p = _project("/home/user/projekt_final")
    assert p.display_name == "projekt_final"
    p.alias = "PPSI 2026"
    assert p.display_name == "PPSI 2026"
    assert p.default_name == "projekt_final"


def test_set_save_load_roundtrip(tmp_path):
    store = tmp_path / "aliases.json"
    p = _project("/home/user/projekt_final")
    aliases = ProjectAliases(store)
    aliases.set(p, "PPSI 2026")
    aliases.save()

    reloaded = ProjectAliases(store)
    assert reloaded.get(p) == "PPSI 2026"
    assert reloaded.get(_project("/home/user/other")) == ""


def test_remove_restores_default(tmp_path):
    store = tmp_path / "aliases.json"
    p = _project("/home/user/p")
    aliases = ProjectAliases(store)
    aliases.set(p, "Alias")
    aliases.remove(p)
    aliases.save()

    ProjectAliases(store).apply([p])
    assert p.alias == ""
    assert p.display_name == "p"


def test_apply_sets_aliases_on_projects(tmp_path):
    store = tmp_path / "aliases.json"
    projects = [_project("/a"), _project("/b")]
    aliases = ProjectAliases(store)
    aliases.set(projects[0], "Alpha")
    aliases.apply(projects)
    assert projects[0].display_name == "Alpha"
    assert projects[1].display_name == "b"


def test_corrupted_store_is_tolerated(tmp_path):
    store = tmp_path / "aliases.json"
    store.write_text("{broken", encoding="utf-8")
    p = _project("/a")
    aliases = ProjectAliases(store)
    assert aliases.get(p) == ""
    aliases.set(p, "X")
    aliases.save()
    assert ProjectAliases(store).get(p) == "X"
