from __future__ import annotations

import json
import os
import time

from pi_sessions.core.cache import TokenCache
from pi_sessions.core.discovery import discover_projects
from pi_sessions.core.manage import ARCHIVE_SUBDIR

from conftest import PROJECT_DIR, SID, session_file, write_transcript


def test_metadata_comes_from_the_session_file(fake_base):
    projects = discover_projects(base=fake_base)
    assert len(projects) == 1
    p = projects[0]
    assert p.project_path == "/tmp/fake-project"
    assert p.display_name == "fake-project"
    s = p.sessions[0]
    assert s.session_id == SID
    assert s.first_prompt == "question 0"
    assert s.message_count == 4
    assert s.tokens.total == 30
    assert s.model == "deepseek/deepseek-flash"
    assert s.created is not None
    assert not s.is_archived


def test_name_wins_and_is_served_from_the_cache(fake_base, tmp_path):
    jsonl = session_file(fake_base / PROJECT_DIR)
    with jsonl.open("a", encoding="utf-8") as f:
        for i, name in enumerate(("first name", "final name")):
            f.write(json.dumps({"type": "session_info", "id": f"n{i}", "parentId": "a1", "name": name}) + "\n")
    cache = TokenCache(tmp_path / "cache.json")
    for _ in range(2):  # second pass is served from the cache
        s = discover_projects(base=fake_base, cache=cache)[0].sessions[0]
        assert s.summary == "final name"
        assert s.display_title == "final name"
        assert s.tokens.total == 30


def test_recently_modified_session_is_live(fake_base, monkeypatch):
    assert discover_projects(base=fake_base)[0].sessions[0].is_live
    old = time.time() - 3600
    os.utime(session_file(fake_base / PROJECT_DIR), (old, old))
    assert not discover_projects(base=fake_base)[0].sessions[0].is_live
    monkeypatch.setenv("PI_SESSIONS_LIVE_SECONDS", "7200")
    assert discover_projects(base=fake_base)[0].sessions[0].is_live


def test_id_falls_back_to_the_file_name(fake_base):
    f = session_file(fake_base / PROJECT_DIR)
    f.write_text("garbage\n", encoding="utf-8")
    s = discover_projects(base=fake_base)[0].sessions[0]
    assert s.session_id == SID
    # no header cwd: the lossy directory decoding is the last resort
    assert s.project_path == "/tmp/fake/project"


def test_archived_subdir_is_scanned(fake_base):
    arch = fake_base / PROJECT_DIR / ARCHIVE_SUBDIR
    arch.mkdir()
    sid2 = "22222222-aaaa-bbbb-cccc-000000000002"
    write_transcript(session_file(arch, sid2), sid=sid2)
    by_id = {s.session_id: s for s in discover_projects(base=fake_base)[0].sessions}
    assert by_id[sid2].is_archived and not by_id[sid2].is_live
    assert by_id[sid2].tokens.total == 30
    assert not by_id[SID].is_archived


def test_empty_base_yields_no_projects(tmp_path):
    assert discover_projects(base=tmp_path / "nope") == []


def test_archived_projects_listed_after_active(fake_base, tmp_path):
    arch_proj = tmp_path / "sessions-archive" / "--tmp-old-project--"
    arch_proj.mkdir(parents=True)
    sid2 = "33333333-aaaa-bbbb-cccc-000000000003"
    write_transcript(session_file(arch_proj, sid2), cwd="/tmp/old-project", sid=sid2)

    projects = discover_projects(base=fake_base, archive_base=tmp_path / "sessions-archive")
    assert len(projects) == 2
    assert not projects[0].is_archived
    archived = projects[1]
    assert archived.is_archived and archived.project_path == "/tmp/old-project"
    assert all(s.is_archived and not s.is_live for s in archived.sessions)


def test_newest_project_sorts_first(fake_base):
    old = time.time() - 3600
    os.utime(session_file(fake_base / PROJECT_DIR), (old, old))
    proj2 = fake_base / "--tmp-newer--"
    proj2.mkdir()
    write_transcript(session_file(proj2), cwd="/tmp/newer")
    assert [p.project_path for p in discover_projects(base=fake_base)][0] == "/tmp/newer"


def test_seen_files_lets_the_cache_be_pruned(fake_base, tmp_path):
    cache = TokenCache(tmp_path / "cache.json")
    seen: set[str] = set()
    discover_projects(base=fake_base, cache=cache, seen_files=seen)
    assert seen == {str(session_file(fake_base / PROJECT_DIR))}
    session_file(fake_base / PROJECT_DIR).unlink()
    seen.clear()
    discover_projects(base=fake_base, cache=cache, seen_files=seen)
    cache.prune(seen)
    assert cache._entries == {}


def test_header_id_with_path_separators_is_ignored(fake_base):
    # the id names the live document file: a crafted header must not steer it
    f = session_file(fake_base / PROJECT_DIR)
    lines = f.read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[0])
    head["id"] = "../../../etc/evil"
    f.write_text("\n".join([json.dumps(head), *lines[1:]]) + "\n", encoding="utf-8")
    assert discover_projects(base=fake_base)[0].sessions[0].session_id == SID
