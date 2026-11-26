"""Regenerate the README screenshots from fake sessions: python docs/screenshots.py"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

DOCS = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp())
os.environ["HOME"] = str(tmp)  # isolate settings, aliases and cache before importing the app
root = tmp / "sessions"
os.environ["PI_SESSIONS_ROOT"] = str(root)
os.environ["PI_SESSIONS_REFRESH_SECONDS"] = "0"

U = lambda i, p, t, ts: {
    "type": "message",
    "id": i,
    "parentId": p,
    "timestamp": ts,
    "message": {"role": "user", "content": [{"type": "text", "text": t}]},
}


def A(i, p, blocks, ts, n):
    usage = {
        "input": n,
        "output": n // 8,
        "cacheRead": n * 3,
        "cacheWrite": 0,
        "totalTokens": n * 4,
        "cost": {"total": n / 400_000},
    }
    return {
        "type": "message",
        "id": i,
        "parentId": p,
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": blocks,
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "usage": usage,
        },
    }


T = lambda t: {"type": "text", "text": t}
C = lambda name, **a: {"type": "toolCall", "name": name, "arguments": a}


def session(cwd, day, sid, turns, age=0):
    Path(cwd).mkdir(parents=True, exist_ok=True)  # so Details shows no "does not exist"
    proj = root / ("--" + cwd.strip("/").replace("/", "-") + "--")
    proj.mkdir(parents=True, exist_ok=True)
    ts = f"2026-11-{day:02d}T09:{sid:02d}:00.000Z"
    objs = [
        {"type": "session", "version": 3, "id": f"0000000{sid}-demo", "timestamp": ts, "cwd": cwd}
    ]
    parent = None
    for k, (q, blocks, n) in enumerate(turns):
        objs += [U(f"u{k}", parent, q, ts), A(f"a{k}", f"u{k}", blocks, ts, n)]
        parent = f"a{k}"
    f = proj / f"{ts.replace(':', '-').replace('.', '-')}_{sid}.jsonl"
    f.write_text("\n".join(map(json.dumps, objs)) + "\n")
    t = time.time() - age
    os.utime(f, (t, t))


home = str(tmp / "code")
session(
    f"{home}/weather-api",
    18,
    1,
    [
        (
            "Fix /forecast failing on accented cities",
            [
                C("read", path="src/routes/forecast.py"),
                C("bash", command="pytest tests/test_forecast.py -q"),
                T(
                    "The city name is passed to the upstream URL **without encoding**, so `ç` breaks the request.\n\n"
                    '```python\nurl = f"{BASE}/forecast?q={quote(city)}"\n```\n\nI added a test with `Besançon` and `Saint-Étienne`.'
                ),
            ],
            12000,
        ),
        (
            "Good. Also cache the upstream responses for 10 minutes",
            [
                C("edit", path="src/upstream.py"),
                C("bash", command="pytest -q"),
                T(
                    "Done: responses are cached **per city and day** for 10 minutes with `functools.lru_cache` "
                    "wrapped in a TTL. All 48 tests pass."
                ),
            ],
            18000,
        ),
    ],
    age=30,
)
session(
    f"{home}/weather-api",
    16,
    2,
    [
        (
            "Add rate limiting",
            [C("read", path="src/app.py"), T("Added a token bucket per API key.")],
            9000,
        )
    ],
    age=2 * 86400,
)
session(
    f"{home}/blog",
    17,
    3,
    [
        (
            "Draft a post on moving to Astro",
            [C("write", path="posts/jekyll-to-astro.md"), T("Draft written.")],
            15000,
        )
    ],
    age=86400,
)
session(
    f"{home}/dotfiles",
    12,
    4,
    [
        (
            "Show git branch in the prompt",
            [C("edit", path="zsh/prompt.zsh"), T("Uses `vcs_info`.")],
            4000,
        )
    ],
    age=6 * 86400,
)
session(
    f"{home}/invoice-parser",
    9,
    5,
    [
        (
            "Extract totals from PDFs",
            [C("bash", command="ls samples/"), T("Using pdfplumber, then OCR as a fallback.")],
            30000,
        )
    ],
    age=9 * 86400,
)
session(
    f"{home}/invoice-parser",
    8,
    6,
    [("Set up the project with uv and pytest", [T("Project initialised.")], 3000)],
    age=10 * 86400,
)

sys.path.insert(0, str(DOCS.parent))
from pi_sessions.ui.app import PiSessionsApp  # noqa: E402 — after the sys.path insert


async def shoot(size, name):
    app = PiSessionsApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause(1.5)
        await pilot.press("tab")  # focus the sessions pane
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / name))


asyncio.run(shoot((160, 42), "screenshot-wide.svg"))
asyncio.run(shoot((110, 48), "screenshot-narrow.svg"))
