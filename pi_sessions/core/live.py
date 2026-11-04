from __future__ import annotations

import os
import time

DEFAULT_LIVE_SECONDS = 120.0


def live_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("PI_SESSIONS_LIVE_SECONDS", DEFAULT_LIVE_SECONDS)))
    except ValueError:
        return DEFAULT_LIVE_SECONDS


def is_recent(mtime: float, now: float | None = None) -> bool:
    """pi keeps no live-session registry (no pid file, no lock), so a session
    counts as live when its file changed within PI_SESSIONS_LIVE_SECONDS.

    ponytail: mtime heuristic — an idle open session reads as stopped; a pi
    extension writing heartbeats (SPECS §8 level 3) is the upgrade.
    """
    return ((now if now is not None else time.time()) - mtime) < live_seconds()
