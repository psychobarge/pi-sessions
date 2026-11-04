from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .models import Project, Session

ARCHIVE_SUBDIR = "archived"


def sessions_root() -> Path:
    """Where pi keeps its sessions, resolved the way pi does.

    PI_SESSIONS_ROOT (ours) wins, for a root pi itself cannot tell us about
    — e.g. a host directory mounted into a pi container.
    """
    for var in ("PI_SESSIONS_ROOT", "PI_CODING_AGENT_SESSION_DIR"):
        value = os.environ.get(var, "").strip()
        if value:
            return Path(value).expanduser()
    agent_dir = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
    base = Path(agent_dir).expanduser() if agent_dir else Path.home() / ".pi" / "agent"
    return base / "sessions"


SESSIONS_DIR = sessions_root()
# next to the sessions root: ~/.pi/agent/sessions-archive by default
SESSIONS_ARCHIVE_DIR = SESSIONS_DIR.parent / "sessions-archive"


class ManageError(RuntimeError):
    pass


def archive_session(session: Session) -> Path:
    """Move the .jsonl into the archived/ subdirectory — pi lists only the
    files directly in a project directory, so it disappears from
    `pi --resume` but stays on disk and can be restored."""
    if not session.jsonl_path.is_file():
        raise ManageError("session file not found")
    dest_dir = session.jsonl_path.parent / ARCHIVE_SUBDIR
    try:
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / session.jsonl_path.name
        session.jsonl_path.rename(dest)
    except OSError as e:
        raise ManageError(str(e)) from e
    return dest


def restore_session(session: Session) -> Path:
    """Move the .jsonl from archived/ back into the project directory."""
    if not session.jsonl_path.is_file():
        raise ManageError("file not found in the archive")
    if session.jsonl_path.parent.name != ARCHIVE_SUBDIR:
        raise ManageError("session is not archived")
    dest = session.jsonl_path.parent.parent / session.jsonl_path.name
    try:
        session.jsonl_path.rename(dest)
    except OSError as e:
        raise ManageError(str(e)) from e
    return dest


def _use_trash() -> bool:
    flag = os.environ.get("PI_SESSIONS_TRASH", "").lower() not in ("", "0", "false", "no")
    return flag and shutil.which("trash") is not None


def delete_session(session: Session) -> None:
    """Delete the session file — through `trash` when PI_SESSIONS_TRASH is set,
    as pi's own /resume does."""
    if not session.jsonl_path.is_file():
        return
    try:
        if _use_trash():
            subprocess.run(["trash", str(session.jsonl_path)], check=True, capture_output=True)
        else:
            session.jsonl_path.unlink()
    except (OSError, subprocess.CalledProcessError) as e:
        raise ManageError(str(e)) from e


def archive_project(project: Project) -> Path:
    """Move the whole project directory into the sessions archive."""
    try:
        SESSIONS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ManageError(str(e)) from e
    dest = SESSIONS_ARCHIVE_DIR / project.encoded_dir.name
    if dest.exists():
        raise ManageError(f"archive already contains directory {dest.name}")
    try:
        shutil.move(str(project.encoded_dir), str(dest))
    except OSError as e:
        raise ManageError(str(e)) from e
    return dest


def restore_project(project: Project) -> Path:
    """Move an archived project directory back into the sessions root."""
    if not project.encoded_dir.is_dir():
        raise ManageError("project directory not found")
    dest = SESSIONS_DIR / project.encoded_dir.name
    if dest.exists():
        raise ManageError(f"sessions directory already contains {dest.name}")
    try:
        shutil.move(str(project.encoded_dir), str(dest))
    except OSError as e:
        raise ManageError(str(e)) from e
    return dest


def delete_project(project: Project) -> None:
    """Permanently delete the whole project directory."""
    try:
        shutil.rmtree(project.encoded_dir)
    except OSError as e:
        raise ManageError(str(e)) from e
