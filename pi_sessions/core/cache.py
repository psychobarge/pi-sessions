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
            self._entries = {k: v for k, v in data.items() if isinstance(v, dict)}

    def get(self, jsonl: Path, stat: os.stat_result | None = None) -> TokenStats | None:
        if stat is None:
            try:
                stat = jsonl.stat()
            except OSError:
                return None
        hit = self.get_partial(jsonl)
        if hit is None or (hit[1], hit[3]) != (stat.st_size, stat.st_mtime_ns):
            return None
        return hit[0]

    def get_partial(self, jsonl: Path) -> tuple[TokenStats, int, set[str], int] | None:
        """The cached stats, fresh or not, with the (size, leaf ids, mtime_ns) they cover."""
        entry = self._entries.get(str(jsonl))
        if not entry:
            return None
        try:
            # cast to each field's default type; a missing key (entry written
            # by an older version) raises KeyError and forces a re-read
            stats = TokenStats(
                **{f.name: type(f.default)(entry[f.name]) for f in fields(TokenStats)}
            )
            return stats, int(entry["size"]), set(entry["leaves"]), int(entry["mtime_ns"])
        except (KeyError, TypeError, ValueError):
            return None

    def put(
        self, jsonl: Path, stats: TokenStats, stat: os.stat_result, size: int, leaves: set[str]
    ) -> None:
        """`size` is how far the stats were read, short of a line still being written;
        `leaves` are the tree's leaf ids, which a later incremental read starts from."""
        self._entries[str(jsonl)] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": size,
            "leaves": sorted(leaves),
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
