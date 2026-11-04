"""Reading pi session files (`docs/session-format.md` in pi-coding-agent).

One JSON object per line: a `session` header, then entries linked into a
tree by `id`/`parentId`. Unknown types, roles and malformed lines are
skipped, never raised.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .models import Entry, TokenStats

if TYPE_CHECKING:
    from .cache import TokenCache


def _load(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _num(value: object) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _add_usage(stats: TokenStats, usage: object) -> None:
    if not isinstance(usage, dict):
        return
    stats.input += int(_num(usage.get("input")))
    stats.output += int(_num(usage.get("output")))
    stats.cache_read += int(_num(usage.get("cacheRead")))
    stats.cache_write += int(_num(usage.get("cacheWrite")))
    cost = usage.get("cost")
    if isinstance(cost, dict):
        stats.cost += float(_num(cost.get("total")))


def _text_of(content: object) -> str:
    """User/custom content: a string, or text blocks joined by newlines."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            b["text"].strip()
            for b in content
            if isinstance(b, dict)
            and b.get("type") == "text"
            and isinstance(b.get("text"), str)
            and b["text"].strip()
        )
    return ""


def compute_token_stats(jsonl_path: Path) -> TokenStats:
    """One streaming pass: tokens, cost, counts and session metadata."""
    stats = TokenStats()
    ids: set[str] = set()
    parents: set[str] = set()
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                obj = _load(line)
                if obj is None:
                    continue
                typ = obj.get("type")
                if typ == "session":
                    stats.session_id = str(obj.get("id") or "")
                    stats.cwd = str(obj.get("cwd") or "")
                    stats.created = str(obj.get("timestamp") or "")
                    stats.parent_session = str(obj.get("parentSession") or "")
                    continue
                eid, pid = obj.get("id"), obj.get("parentId")
                if isinstance(eid, str):
                    ids.add(eid)
                if isinstance(pid, str):
                    parents.add(pid)
                if typ == "session_info":
                    name = obj.get("name")
                    if isinstance(name, str):
                        stats.name = name.strip()
                elif typ == "model_change":
                    if obj.get("modelId"):
                        stats.model = f"{obj.get('provider') or '?'}/{obj['modelId']}"
                elif typ in ("usage", "compaction", "branch_summary"):
                    _add_usage(stats, obj.get("usage"))
                elif typ == "message":
                    msg = obj.get("message")
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role")
                    if role == "user":
                        stats.messages += 1
                        if not stats.first_prompt:
                            stats.first_prompt = _text_of(msg.get("content"))
                    elif role == "assistant":
                        stats.messages += 1
                        _add_usage(stats, msg.get("usage"))
                        if msg.get("model"):
                            stats.model = f"{msg.get('provider') or '?'}/{msg['model']}"
    except OSError:
        pass
    stats.branches = len(ids - parents)
    return stats


def get_token_stats(jsonl_path: Path, cache: "TokenCache | None" = None) -> TokenStats:
    """Like compute_token_stats, but skips the read when the cache is fresh."""
    if cache is None:
        return compute_token_stats(jsonl_path)
    try:
        stat = jsonl_path.stat()
    except OSError:
        return TokenStats()
    cached = cache.get(jsonl_path, stat)
    if cached is not None:
        return cached
    stats = compute_token_stats(jsonl_path)
    cache.put(jsonl_path, stats, stat)
    return stats


_TOOL_ARG_KEYS = (
    "command", "path", "file_path", "pattern", "query", "url", "prompt", "description", "skill",
)


def _summarize_tool_call(name: str, args: object) -> str:
    if not isinstance(args, dict):
        return name
    for key in _TOOL_ARG_KEYS:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            first = val.strip().splitlines()[0]
            if len(first) > 80:
                first = first[:77] + "..."
            return f"{name}: {first}"
    return name


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        # fromisoformat only learned to read the trailing "Z" in 3.11
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def entries_from_obj(obj: dict) -> list[Entry]:
    """Turn one session entry into zero or more conversation entries."""
    typ = obj.get("type")
    ts = _parse_ts(obj.get("timestamp"))

    if typ == "compaction":
        before = obj.get("tokensBefore")
        detail = f" ({before:,} tokens summarized)" if isinstance(before, int) else ""
        return [Entry("marker", f"⧉ compaction{detail}", ts)]
    if typ == "branch_summary":
        return [Entry("marker", "⑂ branch switch", ts)]
    if typ == "custom_message":
        if obj.get("display") is not True:
            return []
        text = _text_of(obj.get("content"))
        return [Entry("command-output", f"[{obj.get('customType') or 'extension'}] {text}", ts)] if text else []
    if typ != "message":
        return []

    msg = obj.get("message")
    if not isinstance(msg, dict):
        return []
    role = msg.get("role")

    if role == "user":
        text = _text_of(msg.get("content"))
        return [Entry("user", text, ts)] if text else []

    if role == "bashExecution":
        command = msg.get("command")
        if not isinstance(command, str) or not command.strip():
            return []
        out = [Entry("command", f"! {command.strip()}", ts)]
        output = msg.get("output")
        if isinstance(output, str) and output.strip():
            out.append(Entry("command-output", output.strip(), ts))
        return out

    if role != "assistant" or not isinstance(msg.get("content"), list):
        return []
    entries: list[Entry] = []
    for b in msg["content"]:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        if btype == "text" and isinstance(b.get("text"), str) and b["text"].strip():
            entries.append(Entry("assistant", b["text"].strip(), ts))
        elif btype == "toolCall":
            name = str(b.get("name") or "?")
            entries.append(Entry("tool", _summarize_tool_call(name, b.get("arguments")), ts))
    return entries


def entries_from_line(line: str) -> list[Entry]:
    obj = _load(line)
    return entries_from_obj(obj) if obj is not None else []


def active_branch(objs: list[dict]) -> list[dict]:
    """Entries on the path from the last entry back to the root, in file order.

    Walks `parentId` only through the entries given (the tail of a file
    yields the tail of the branch). Entries without an `id` (legacy v1
    files) all count as on the branch.
    """
    by_id = {o["id"]: o for o in objs if isinstance(o.get("id"), str) and o.get("type") != "session"}
    if not by_id:
        return objs
    leaf = next(o for o in reversed(objs) if o.get("id") in by_id and o.get("type") != "session")
    chain: set[str] = set()
    cur: dict | None = leaf
    while cur is not None and cur["id"] not in chain:
        chain.add(cur["id"])
        cur = by_id.get(cur.get("parentId"))
    return [o for o in objs if o.get("id") in chain or not isinstance(o.get("id"), str)]


def _entries(objs: Iterable[dict]) -> list[Entry]:
    out: list[Entry] = []
    for o in objs:
        out.extend(entries_from_obj(o))
    return out


def read_conversation_tail(
    jsonl_path: Path,
    max_entries: int = 40,
    max_bytes: int = 512_000,
) -> list[Entry]:
    """Last entries of the active branch, newest last.

    Only the tail of the file (max_bytes) is read, so this stays fast even
    for transcripts spanning many megabytes.
    """
    try:
        with open(jsonl_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # the first line is usually cut mid-record
    objs = [o for o in map(_load, lines) if o is not None]
    return _entries(active_branch(objs))[-max_entries:]


def iter_conversation(jsonl_path: Path) -> Iterator[Entry]:
    """Stream the active branch of the whole conversation.

    Two passes: the first keeps only `id -> parentId`, the second parses the
    entries on the branch one line at a time, so even huge transcripts never
    land in memory at once.
    """
    parent: dict[str, object] = {}
    last = None
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                obj = _load(line)
                if obj is None or obj.get("type") == "session":
                    continue
                if isinstance(obj.get("id"), str):
                    parent[obj["id"]] = obj.get("parentId")
                    last = obj["id"]
        chain: set[str] = set()
        cur = last
        while isinstance(cur, str) and cur in parent and cur not in chain:
            chain.add(cur)
            cur = parent[cur]
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                obj = _load(line)
                if obj is None:
                    continue
                eid = obj.get("id")
                if not isinstance(eid, str) or eid in chain:
                    yield from entries_from_obj(obj)
    except OSError:
        return
