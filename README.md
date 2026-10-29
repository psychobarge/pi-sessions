# pi-sessions

A fast terminal UI for browsing, previewing, resuming and managing
[pi](https://github.com/earendil-works/pi) coding agent sessions.

A fork of [ccsessions](https://github.com/miskiewiczm/ccsessions) by Marek
Miśkiewicz, which does the same for Claude Code. The full behaviour is
specified in [SPECS.md](SPECS.md); changes from ccsessions are listed in
[CHANGELOG.md](CHANGELOG.md).

## Features

- **Project & session browser** — every pi project on your machine, newest
  first, with recently-active indicators (●), fork markers (⑂), message
  counts, token usage and cost
- **Conversation preview** — the tail of the active branch, rendered with
  roles, Markdown for pi's replies, tool calls (⚙), `!` commands (⌘) and
  compaction markers, without opening pi
- **One-key resume** — `r` replaces the TUI with `pi --session <file>` in the
  session's working directory; `c` copies the command to the clipboard (OSC 52)
- **Archive & delete** — move sessions out of `pi --resume` (reversibly) or
  delete them for good, per session or per project, with confirmation dialogs
- **Resizable panes** — drag the bars between panes with the mouse; sizes
  are remembered per layout across runs (`~/.config/pi-sessions/settings.json`)
- **Export** — Markdown with YAML front matter (ready for Quarto/Pandoc) or the
  raw JSONL, never overwriting an existing file
- **Live document** — `l` keeps `_session_<id>.md` in sync with a running
  session, so a live-reloading renderer can show it with LaTeX rendered
- **Fast** — session metadata is cached per file (mtime + size), scanning runs
  off the UI thread, previews read only the tail of large files

## Requirements

- Python ≥ 3.10
- pi installed (`pi` on PATH — needed only for resuming)
- macOS or Linux

## Installation

```bash
git clone https://github.com/psychobarge/pi-sessions
pip install -e pi-sessions
```

## Usage

```bash
pisessions
```

| Key | Action |
| --- | --- |
| `j` / `k` / arrows | Move within the focused pane |
| `Tab` / `Shift+Tab` | Switch panes |
| `r` | Resume the selected session (in place) |
| `c` | Copy the resume command to the clipboard |
| `a` | Archive ↔ restore session · archive ↔ restore project |
| `d` | Delete session / project (with confirmation) |
| `n` | Rename project (set a display alias) |
| `e` | Export the session (Markdown or raw JSONL) |
| `l` | Follow the session in a live Markdown document |
| `/` | Filter the focused list (projects or sessions) |
| `p` | Command palette (change theme) |
| `Ctrl+R` | Rescan now (a rescan also runs automatically) |
| `q` | Quit |

`a` and `d` act on the **session** when the Sessions pane is focused and on
the whole **project** when the Projects pane is focused.

pi keeps no record of running sessions, so ● means *modified in the last
`PI_SESSIONS_LIVE_SECONDS` seconds* (default 120). Sessions marked this way
cannot be archived or deleted.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PI_SESSIONS_ROOT` | pi's own (`PI_CODING_AGENT_SESSION_DIR`, `$PI_CODING_AGENT_DIR/sessions`, `~/.pi/agent/sessions`) | Where to read sessions |
| `PI_SESSIONS_PI_BIN` | `pi` | Command used to resume |
| `PI_SESSIONS_RESUME_ROOT` | — | Rewrite the sessions root in resume commands, for a pi that sees it elsewhere (container) |
| `PI_SESSIONS_LIVE_SECONDS` | `120` | Recently-active threshold |
| `PI_SESSIONS_TRASH` | `0` | Delete through the `trash` command |
| `PI_SESSIONS_LIVE_DIR` | session cwd | Where live documents go (use a plain directory for Quarto projects) |
| `PI_SESSIONS_REFRESH_SECONDS` | `10` | Auto-refresh interval, `0` disables |
| `PI_SESSIONS_THEME` | saved choice, else `ansi-dark` | Textual theme |
| `PI_SESSIONS_CODE_THEME` | follows the theme | Pygments style for code blocks |
| `PI_SESSIONS_NERD_FONT`, `PI_SESSIONS_EYE`, `PI_SESSIONS_EYE_OFF` | — | Live-document glyphs |

Settings and project aliases live in `~/.config/pi-sessions/`, the cache in
`~/.cache/pi-sessions/`.

### pi in a container

If pi runs in Docker with its agent directory in a named volume, the host
cannot see the sessions. Bind-mount a host directory over the container's
sessions directory (e.g. `-v ~/.pi/agent/sessions:/root/.pi/agent/sessions`),
then set `PI_SESSIONS_RESUME_ROOT=/root/.pi/agent/sessions` so resume
commands use the path pi sees.

## How it works

pi stores each session as `<sessions root>/--<encoded cwd>--/<timestamp>_<id>.jsonl`:
a header line, then entries linked into a tree. pi-sessions reads those files
and never modifies them. Archiving a session moves it into an `archived/`
subdirectory, which pi does not list. Archiving a project moves its directory
to `sessions-archive/` next to the sessions root. Everything happens locally;
no network requests.

## Development

```bash
pip install -e . --group dev
pytest
```

## License

[MIT](LICENSE)
