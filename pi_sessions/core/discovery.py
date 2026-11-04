from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .cache import TokenCache
from .live import is_recent
from .manage import ARCHIVE_SUBDIR, SESSIONS_ARCHIVE_DIR, SESSIONS_DIR
from .models import Project, Session
from .parser import get_token_stats


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # normalize to local-naive so we can sort against mtime-derived values
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _decode_dir_name(name: str) -> str:
    """Best-effort `--a-b--` -> `/a/b`; lossy, used only without a header cwd."""
    return "/" + name.strip("-").replace("-", "/")


def _build_session(
    jsonl: Path, cache: TokenCache | None, archived: bool, seen_files: set[str] | None
) -> Session:
    if seen_files is not None:
        seen_files.add(str(jsonl))
    stats = get_token_stats(jsonl, cache)
    mtime: datetime | None = None
    live = False
    try:
        st = jsonl.stat()
        mtime = datetime.fromtimestamp(st.st_mtime)
        live = not archived and is_recent(st.st_mtime)
    except OSError:
        pass
    return Session(
        # file names are <timestamp>_<id>.jsonl. The header id names the live
        # document file, and whoever writes sessions controls it: no separators
        session_id=(
            stats.session_id
            if re.fullmatch(r"[\w.-]+", stats.session_id)
            else jsonl.stem.split("_", 1)[-1]
        ),
        jsonl_path=jsonl,
        project_path=stats.cwd,
        first_prompt=stats.first_prompt,
        summary=stats.name,
        message_count=stats.messages,
        created=_parse_iso(stats.created),
        modified=mtime,
        model=stats.model,
        parent_session=stats.parent_session,
        branches=stats.branches,
        is_live=live,
        is_archived=archived,
        tokens=stats,
    )


def _load_project(
    proj_dir: Path, cache: TokenCache | None, seen_files: set[str] | None
) -> Project:
    sessions = [_build_session(f, cache, False, seen_files) for f in proj_dir.glob("*.jsonl")]
    sessions += [
        _build_session(f, cache, True, seen_files)
        for f in (proj_dir / ARCHIVE_SUBDIR).glob("*.jsonl")
    ]
    sessions.sort(key=lambda s: s.modified or datetime.min, reverse=True)
    # the newest session's header has the real cwd; the directory name is lossy
    project_path = next((s.project_path for s in sessions if s.project_path), "")
    project_path = project_path or _decode_dir_name(proj_dir.name)
    for s in sessions:
        s.project_path = s.project_path or project_path
    return Project(project_path=project_path, encoded_dir=proj_dir, sessions=sessions)


def _latest_modified(p: Project) -> datetime:
    return max((s.modified or datetime.min) for s in p.sessions)


def _scan_dir(base: Path, cache: TokenCache | None, seen_files: set[str] | None) -> list[Project]:
    projects: list[Project] = []
    for proj_dir in sorted(base.iterdir()):
        if not proj_dir.is_dir():
            continue
        project = _load_project(proj_dir, cache, seen_files)
        if project.sessions:
            projects.append(project)
    projects.sort(key=_latest_modified, reverse=True)
    return projects


def discover_projects(
    base: Path | None = None,
    cache: TokenCache | None = None,
    archive_base: Path | None = None,
    seen_files: set[str] | None = None,
) -> list[Project]:
    """Scan pi projects (and archived projects), newest first.

    With no `base`, the real sessions root and its archive are scanned.
    Callers passing a custom `base` (tests) never get the user's archive
    mixed in unless they pass `archive_base`. `seen_files` collects every
    session file read, so the caller can prune the cache.
    """
    if base is None:
        base = SESSIONS_DIR
        archive_base = archive_base or SESSIONS_ARCHIVE_DIR
    if not base.is_dir():
        return []
    projects = _scan_dir(base, cache, seen_files)
    archived: list[Project] = []
    if archive_base is not None and archive_base.is_dir():
        archived = _scan_dir(archive_base, cache, seen_files)
        for project in archived:
            project.is_archived = True
            for s in project.sessions:
                s.is_archived = True
                s.is_live = False
    # archived projects always come after active ones
    return projects + archived
