from __future__ import annotations

import json
from pathlib import Path

import pytest

SID = "11111111-aaaa-bbbb-cccc-000000000001"
PROJECT_DIR = "--tmp-fake-project--"


def session_file(proj_dir: Path, sid: str = SID, stamp: str = "2026-10-14T14-40-04-385Z") -> Path:
    """pi names session files <timestamp>_<id>.jsonl."""
    return proj_dir / f"{stamp}_{sid}.jsonl"


def header(sid: str = SID, cwd: str = "/tmp/fake-project", **extra) -> dict:
    return {
        "type": "session",
        "version": 3,
        "id": sid,
        "timestamp": "2026-10-14T14:40:04.385Z",
        "cwd": cwd,
        **extra,
    }


def user(eid: str, parent: str | None, text: str, ts: str = "2026-10-14T14:41:00.000Z") -> dict:
    return {
        "type": "message",
        "id": eid,
        "parentId": parent,
        "timestamp": ts,
        "message": {"role": "user", "content": [{"type": "text", "text": text}], "timestamp": 0},
    }


def assistant(
    eid: str,
    parent: str | None,
    blocks: list[dict],
    usage: dict | None = None,
    ts: str = "2026-10-14T14:41:05.000Z",
) -> dict:
    msg = {
        "role": "assistant",
        "content": blocks,
        "provider": "deepseek",
        "model": "deepseek-flash",
        "timestamp": 0,
    }
    if usage is not None:
        msg["usage"] = usage
    return {"type": "message", "id": eid, "parentId": parent, "timestamp": ts, "message": msg}


def text(t: str) -> dict:
    return {"type": "text", "text": t}


USAGE = {
    "input": 10,
    "output": 5,
    "cacheRead": 0,
    "cacheWrite": 0,
    "totalTokens": 15,
    "cost": {"total": 0.001},
}


def write_jsonl(path: Path, objs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n", encoding="utf-8")


def write_transcript(
    path: Path,
    cwd: str = "/tmp/fake-project",
    exchanges: int = 2,
    usage_per_reply: dict | None = None,
    sid: str = SID,
) -> None:
    """Write a minimal but realistic linear pi session."""
    usage = usage_per_reply or USAGE
    objs: list[dict] = [header(sid, cwd)]
    parent = None
    for i in range(exchanges):
        objs.append(user(f"u{i}", parent, f"question {i}"))
        objs.append(assistant(f"a{i}", f"u{i}", [text(f"**answer** {i}")], usage))
        parent = f"a{i}"
    write_jsonl(path, objs)


@pytest.fixture
def fake_base(tmp_path: Path) -> Path:
    """A fake ~/.pi/agent/sessions with one project and one session."""
    base = tmp_path / "sessions"
    proj = base / PROJECT_DIR
    proj.mkdir(parents=True)
    write_transcript(session_file(proj))
    return base
