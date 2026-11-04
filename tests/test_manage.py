from __future__ import annotations

from unittest.mock import patch

import pytest

import pi_sessions.core.manage as manage
from pi_sessions.core.discovery import discover_projects
from pi_sessions.core.manage import (
    ManageError,
    archive_project,
    archive_session,
    delete_project,
    delete_session,
    restore_session,
    sessions_root,
)

from conftest import PROJECT_DIR


def _session(base):
    return discover_projects(base=base)[0].sessions[0]


def test_archive_and_restore_session(fake_base):
    s = _session(fake_base)
    dest = archive_session(s)
    assert dest.parent.name == manage.ARCHIVE_SUBDIR
    assert dest.is_file()

    s = _session(fake_base)
    assert s.is_archived
    restored = restore_session(s)
    assert restored.parent.name == PROJECT_DIR
    assert not _session(fake_base).is_archived


def test_restore_requires_archived_session(fake_base):
    with pytest.raises(ManageError):
        restore_session(_session(fake_base))


def test_delete_session_removes_file(fake_base):
    s = _session(fake_base)
    delete_session(s)
    assert not s.jsonl_path.exists()


def test_delete_session_goes_through_trash_when_asked(fake_base, monkeypatch):
    s = _session(fake_base)
    monkeypatch.setenv("PI_SESSIONS_TRASH", "1")
    with patch.object(manage.shutil, "which", return_value="/usr/bin/trash"), patch.object(
        manage.subprocess, "run"
    ) as run:
        delete_session(s)
    run.assert_called_once()
    assert run.call_args.args[0] == ["trash", str(s.jsonl_path)]
    assert s.jsonl_path.exists()  # the mocked trash did not move it


def test_archive_project_moves_directory(fake_base, tmp_path):
    arch_base = tmp_path / "sessions-archive"
    with patch.object(manage, "SESSIONS_ARCHIVE_DIR", arch_base):
        dest = archive_project(discover_projects(base=fake_base)[0])
    assert dest.is_dir()
    assert not (fake_base / PROJECT_DIR).exists()
    assert discover_projects(base=fake_base) == []


def test_restore_project_moves_directory_back(fake_base, tmp_path):
    arch_base = tmp_path / "sessions-archive"
    with patch.object(manage, "SESSIONS_ARCHIVE_DIR", arch_base), patch.object(
        manage, "SESSIONS_DIR", fake_base
    ):
        archive_project(discover_projects(base=fake_base)[0])
        archived = discover_projects(base=fake_base, archive_base=arch_base)[0]
        assert archived.is_archived
        manage.restore_project(archived)
    assert (fake_base / PROJECT_DIR).is_dir()
    restored = discover_projects(base=fake_base, archive_base=arch_base)
    assert len(restored) == 1 and not restored[0].is_archived


def test_delete_project_removes_directory(fake_base):
    delete_project(discover_projects(base=fake_base)[0])
    assert not (fake_base / PROJECT_DIR).exists()


def test_sessions_root_follows_pi_env_vars(monkeypatch, tmp_path):
    for var in ("PI_SESSIONS_ROOT", "PI_CODING_AGENT_SESSION_DIR", "PI_CODING_AGENT_DIR"):
        monkeypatch.delenv(var, raising=False)
    assert sessions_root().parts[-3:] == (".pi", "agent", "sessions")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "agent"))
    assert sessions_root() == tmp_path / "agent" / "sessions"
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(tmp_path / "s"))
    assert sessions_root() == tmp_path / "s"
    monkeypatch.setenv("PI_SESSIONS_ROOT", str(tmp_path / "mine"))
    assert sessions_root() == tmp_path / "mine"
