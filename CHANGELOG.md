# Changelog

All notable changes to this project are documented here.

## [1.1.0] - unreleased

## [1.0.0] — 2026-11-26

### Added
- `pisessions --select --output FILE` keeps the full browser available and returns
  the chosen session's JSONL path to the caller instead of launching Pi.
- **Settings** in the command palette (`p`), in a side panel docked right like
  the keys panel (only one of them is open at a time). First option, under
  Columns: hide any column but the name, in Projects (Sessions, Tokens) and in
  Sessions (Msgs, Tokens, Modified), so names get more room. All shown by
  default. Saved as `"show_project_sessions"`, `"show_project_tokens"`,
  `"show_msgs"`, `"show_tokens"` and `"show_modified"` in
  `~/.config/pi-sessions/settings.json`.
  Under Details: show the resume command in full. Off by default: it can't be
  copied with the mouse, so the pane shows `Resume command : press c to copy
  to clipboard`. Saved as `"show_resume_command"`.
- The header shows the installed version. On launch, a background check asks
  PyPI for the latest release; when it is newer, the header shows it with the
  upgrade command. Disable with `"check_updates": false` in
  `~/.config/pi-sessions/settings.json`.
- `pisessions --version` prints the installed version.
- `n` on the Sessions pane names the session, the way pi's `/name` does: the
  name is written into the session file, so pi shows it too. Empty input clears
  it. Live sessions are refused: rename those from pi.
- Click a numeric or date column header (Msgs, Tokens, Modified; Sessions,
  Tokens on Projects) to sort: descending ▼, then ascending ▲, then back to
  the default order. Hovering the header highlights only those clickable
  labels, instead of the whole header row.
- Reworked the theme picker (Change theme in the palette): each theme is
  previewed live as you move through the list (↑/↓ or typing); Enter keeps it,
  Esc restores the previous theme. The picker is narrower and no longer dims
  the app, so the preview stays visible around it.
- `foxberry` light theme, with matching code block colors. Palette by
  [miskiewiczm](https://github.com/miskiewiczm/foxberry) (MIT).
- The keys panel and the settings panel have a close button and close with
  Escape.

### Changed
- "Fork of" in Details shows the parent session's title instead of its file
  name (the file name stays when the parent can't be found).

### Fixed
- Details colors (state, model, labels, token lines) with `ansi-*` themes:
  they were dropped in exported screenshots since the pane moved to Rich
  tables.
- Long project names and session titles no longer push the other columns out
  of a narrow pane: they are cut with `…` to fit the pane width and grow back
  when it widens. The full name stays visible in Details.
- Auto-refresh no longer resets the horizontal scroll of the Projects and
  Sessions tables.
- Titles and project names get more room: the status and watch icons share
  one narrow column, the live dot sits next to the project name, and the
  blank margin after the last column is gone (it was counted twice, plus a
  scrollbar slot reserved even when no scrollbar showed).

## [0.2.0] — 2026-11-18

### Changed from ccsessions
- Narrow layout: Projects and Sessions now share the top row and Details takes
  the full width below them, instead of a Projects column beside Sessions
  stacked above Details. Default widths of Projects and Sessions are unchanged.
  A saved Sessions height from an earlier drag is ignored.
- Panes are resized by dragging their borders: the split bars between them
  are gone, so the panes touch. Double-click a border to reset it.
- Details: token counts sit to the right of ID / CWD / dates instead of below
  them. A long CWD wraps inside its column.

### Fixed
- Dragging a pane border no longer selects the text of the panes it crosses.
- A border now moves only the two panes beside it: in the narrow layout,
  the Details/Conversation border leaves the Projects | Sessions row alone, and
  in the wide layout the Sessions/Details border leaves Projects alone.
- Slow rescans no longer pile up, and a superseded scan no longer overwrites
  a newer one.
- Renaming a project no longer moves the cursor back to its old row.
- A live session's file is no longer read in full at every rescan: only the
  lines added since the last one are.
- Running the test suite no longer overwrites the saved theme and layout in
  `~/.config/pi-sessions/settings.json`.

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
