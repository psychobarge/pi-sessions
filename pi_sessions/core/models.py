from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple


class Entry(NamedTuple):
    """One conversation entry parsed from a pi session line.

    `ts` comes from the entry's own ISO `timestamp`, which pi writes on every
    entry of the session tree.
    """

    role: str  # user | assistant | tool | command | command-output | marker
    text: str
    ts: datetime | None = None  # aware, UTC; None when the entry carries none


@dataclass
class TokenStats:
    """Everything read from one full pass over a session file.

    pi keeps no session index, so this doubles as the session's metadata and
    is what the cache stores. Every field has a primitive default: the cache
    rebuilds instances by casting stored values to the default's type.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float = 0.0  # USD, as recorded by pi
    messages: int = 0  # user/assistant messages, all branches
    name: str = ""  # last session_info name (/name, --name)
    first_prompt: str = ""
    cwd: str = ""
    created: str = ""  # ISO timestamp of the session header
    session_id: str = ""
    model: str = ""  # provider/model, last seen
    parent_session: str = ""  # file this session was forked/cloned from
    branches: int = 0  # leaves of the entry tree

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def __iadd__(self, other: "TokenStats") -> "TokenStats":
        self.input += other.input
        self.output += other.output
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.cost += other.cost
        self.messages += other.messages
        return self


@dataclass
class Session:
    session_id: str
    jsonl_path: Path
    project_path: str
    first_prompt: str = ""
    summary: str = ""
    message_count: int = 0
    created: datetime | None = None
    modified: datetime | None = None
    model: str = ""
    parent_session: str = ""
    branches: int = 0
    is_live: bool = False  # modified recently — pi keeps no live-session registry
    is_archived: bool = False  # .jsonl moved into the archived/ subdirectory
    tokens: TokenStats = field(default_factory=TokenStats)

    @property
    def display_title(self) -> str:
        return self.summary or self.first_prompt or self.session_id


@dataclass
class Project:
    project_path: str
    encoded_dir: Path
    sessions: list[Session] = field(default_factory=list)
    is_archived: bool = False  # directory lives in the sessions archive
    alias: str = ""  # user-defined display name (see core.aliases)

    @property
    def default_name(self) -> str:
        return Path(self.project_path).name or self.project_path

    @property
    def display_name(self) -> str:
        return self.alias or self.default_name

    @property
    def total_tokens(self) -> TokenStats:
        agg = TokenStats()
        for s in self.sessions:
            agg += s.tokens
        return agg

    @property
    def has_live(self) -> bool:
        return any(s.is_live for s in self.sessions)
