from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from .models import TokenStats

DEFAULT_CACHE_PATH = Path.home() / ".cache" / "pi-sessions" / "stats.json"


class TokenCache:
    """Per-session-file stats cache — pi keeps no session index, so this is it.

    An entry stays valid as long as the file's (st_mtime_ns, st_size) are
    unchanged — large finished sessions are read from disk only once.
    """

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path
        self._entries: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self._entries = {
                k: v for k, v in data.items() if isinstance(v, dict)
            }

    def get(self, jsonl: Path, stat: os.stat_result | None = None) -> TokenStats | None:
        entry = self._entries.get(str(jsonl))
        if not entry:
            return None
        if stat is None:
            try:
                stat = jsonl.stat()
            except OSError:
                return None
        if entry.get("mtime_ns") != stat.st_mtime_ns or entry.get("size") != stat.st_size:
            return None
        try:
            # cast to each field's default type; a missing key (entry written
            # by an older version) raises KeyError and forces a re-read
            return TokenStats(
                **{f.name: type(f.default)(entry[f.name]) for f in fields(TokenStats)}
            )
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, jsonl: Path, stats: TokenStats, stat: os.stat_result) -> None:
        self._entries[str(jsonl)] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            **asdict(stats),
        }
        self._dirty = True

    def prune(self, existing: set[str]) -> None:
        """Drop entries for files that no longer exist on disk."""
        stale = [k for k in self._entries if k not in existing]
        for k in stale:
            del self._entries[k]
            self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._entries), encoding="utf-8")
            tmp.replace(self.path)
            self._dirty = False
        except OSError:
            pass
