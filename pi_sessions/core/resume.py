from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from .manage import SESSIONS_DIR


@dataclass
class ResumeRequest:
    session_id: str
    cwd: str
    file: str  # session file, as seen from this machine


class ResumeError(RuntimeError):
    pass


def pi_bin() -> str:
    return os.environ.get("PI_SESSIONS_PI_BIN", "").strip() or "pi"


def session_arg(req: ResumeRequest) -> str:
    """The file to hand to `pi --session`.

    A file path is unambiguous where an id may be partial-matched or offered
    as a fork. PI_SESSIONS_RESUME_ROOT rewrites the sessions root for a pi
    that sees it elsewhere (a container mounting it at /root/.pi/agent/sessions).
    """
    remap = os.environ.get("PI_SESSIONS_RESUME_ROOT", "").strip()
    if remap:
        try:
            rel = Path(req.file).relative_to(SESSIONS_DIR)
        except ValueError:
            return req.file
        return str(Path(remap) / rel)
    return req.file


def build_resume_command(req: ResumeRequest) -> str:
    """Shell command that resumes the session — for copy/paste into a terminal."""
    cmd = f"{shlex.quote(pi_bin())} --session {shlex.quote(session_arg(req))}"
    if req.cwd and os.path.isdir(req.cwd):
        cmd = f"cd {shlex.quote(req.cwd)} && {cmd}"
    return cmd


def execute_resume(req: ResumeRequest) -> None:
    """Replace the current process with `pi --session <file>` in the session cwd.

    pi runs a resumed session in its own cwd anyway; the chdir matters for
    launchers (pi-sandbox) that mount the current directory.
    Does not return on success (os.execvp replaces the process image).
    """
    name = pi_bin()
    binary = shutil.which(name)
    if not binary:
        raise ResumeError(f"`{name}` not found in PATH")
    if req.cwd and os.path.isdir(req.cwd):
        os.chdir(req.cwd)
    os.execvp(binary, [name, "--session", session_arg(req)])
