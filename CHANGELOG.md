# Changelog

All notable changes to this project are documented here.

## [0.1.0] — 2026-11-04

First release. pi-sessions is a fork of
[ccsessions](https://github.com/miskiewiczm/ccsessions) 0.4.0 by Marek
Miśkiewicz (MIT), adapted from Claude Code to the
[pi](https://github.com/earendil-works/pi) coding agent. The history of
ccsessions is kept in this repository.

### Changed from ccsessions
- Reads pi sessions (`~/.pi/agent/sessions/--<cwd>--/<timestamp>_<id>.jsonl`,
  format v3) instead of `~/.claude/projects`. The sessions root follows pi's
  own settings (`PI_CODING_AGENT_SESSION_DIR`, `PI_CODING_AGENT_DIR`), or
  `PI_SESSIONS_ROOT`.
- pi keeps no session index: titles (`/name`), first prompt, working directory,
  token and cost totals are read from the session file and cached per file
  (mtime + size).
- pi keeps no record of running sessions: ● means modified in the last
  `PI_SESSIONS_LIVE_SECONDS` (default 120).
- Resume runs `pi --session <file>` (`PI_SESSIONS_PI_BIN` picks the command,
  `PI_SESSIONS_RESUME_ROOT` rewrites the path for a pi running in a container).
- Preview and export follow the active branch of pi's session tree, and show
  `!` commands, compactions and displayed extension messages.
- Project archive is `sessions-archive/` next to the sessions root; session
  delete can go through `trash` (`PI_SESSIONS_TRASH=1`).
- Command `pisessions`, package `pi-sessions-tui`, settings in
  `~/.config/pi-sessions/`, cache in `~/.cache/pi-sessions/`, env vars
  `PI_SESSIONS_*` instead of `CCSESSIONS_*`.

### Added
- Cost (USD, as recorded by pi) in the details pane and Markdown export.
- Model, fork origin (⑂) and branch count for each session.
- Resizable panes: drag the bars between panes; sizes are remembered per
  layout (wide / narrow), double-click a bar to reset it, "Reset layout" in the
  command palette.
- The focused pane's border uses the accent colour.

### Removed
- Claude Code specifics: `sessions-index.json`, sessions whose file lives on
  another machine (✕), sidechains, git branch, worktree labels, legacy alias
  keys.

### Fixed
- The details pane advertised `w` for the live document; the key is `l`.
- A session id read from a crafted session header can no longer steer where
  the live document is written.
