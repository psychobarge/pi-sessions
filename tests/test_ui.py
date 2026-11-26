from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console
from textual.command import CommandList
from textual.widgets import Static

import pi_sessions.ui.app as appmod
from pi_sessions.core import settings as settings_mod
from pi_sessions.core.models import Project, Session
from pi_sessions.core.resume import ResumeRequest
from pi_sessions.ui.app import PiSessionsApp


def _fake_projects() -> list[Project]:
    def session(sid: str, prompt: str) -> Session:
        return Session(
            session_id=sid,
            jsonl_path=Path(f"/nonexistent/{sid}.jsonl"),
            project_path="/tmp/x",
            first_prompt=prompt,
        )

    alpha = Project(
        project_path="/tmp/alpha",
        encoded_dir=Path("/tmp/enc-a"),
        sessions=[session("s1", "fix the parser"), session("s2", "write docs")],
    )
    beta = Project(
        project_path="/tmp/beta",
        encoded_dir=Path("/tmp/enc-b"),
        sessions=[session("s3", "deploy app")],
    )
    return [alpha, beta]


async def _exercise_filters(select_mode: bool) -> None:
    app = PiSessionsApp(select_mode=select_mode)
    with patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            from textual.widgets import DataTable, Input

            pt = app.query_one("#projects-table", DataTable)
            st = app.query_one("#sessions-table", DataTable)
            inp = app.query_one("#filter-input", Input)
            assert pt.row_count == 2

            # filter projects down to "beta"
            await pilot.press("/")
            for ch in "beta":
                await pilot.press(ch)
            await pilot.pause()
            assert pt.row_count == 1
            project = app._current_project()
            assert project is not None and project.display_name == "beta"

            # enter applies and returns focus; escape clears
            await pilot.press("enter")
            await pilot.pause()
            assert not inp.display and app.focused is pt
            await pilot.press("/")
            await pilot.press("escape")
            await pilot.pause()
            assert pt.row_count == 2
            # clearing the filter keeps the selected project, it does not snap back
            selected = app._current_project()
            assert selected is not None and selected.display_name == "beta"

            # back to the first project for the session filter
            await pilot.press("k")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.press("/")
            for ch in "docs":
                await pilot.press(ch)
            await pilot.pause()
            assert st.row_count == 1
            selected = app._current_session()
            assert selected is not None and selected.first_prompt == "write docs"
            await pilot.press("escape")
            await pilot.pause()
            assert st.row_count == 2


@pytest.mark.parametrize("select_mode", [False, True])
def test_filter_projects_and_sessions(select_mode):
    asyncio.run(_exercise_filters(select_mode))


@pytest.mark.parametrize(
    ("select_mode", "keys", "session_id"),
    [(False, ("tab", "j", "r"), "s2"), (True, ("tab", "j", "r"), "s2"), (True, ("enter",), "s1")],
)
def test_session_selection_keys(select_mode, keys, session_id):
    async def exercise():
        app = PiSessionsApp(select_mode=select_mode)
        with patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()):
            async with app.run_test(size=(120, 40)) as pilot:
                await app.workers.wait_for_complete()
                assert app.screen.active_bindings["r"].binding.description == (
                    "Select" if select_mode else "Resume"
                )
                await pilot.press(*keys)
        assert app.return_value == ResumeRequest(session_id, "/tmp/x", f"/nonexistent/{session_id}.jsonl")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("open_panel", "selector"),
    [("action_show_help_panel", "HelpPanel"), ("action_show_settings", "SettingsPanel")],
)
def test_picker_preserves_side_panel_keys_before_cancelling(open_panel, selector):
    async def exercise():
        app = PiSessionsApp(select_mode=True)
        with patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()):
            async with app.run_test(size=(120, 40)) as pilot:
                await app.workers.wait_for_complete()
                getattr(app, open_panel)()
                await pilot.pause()
                assert app.screen.query(selector)

                if selector == "SettingsPanel":
                    checkbox = app.query_one("#show_modified", appmod.Tick)
                    previous = checkbox.value
                    checkbox.focus()
                    await pilot.press("enter")
                    assert checkbox.value is not previous
                    assert app.return_code is None

                await pilot.press("escape")
                await pilot.pause()
                assert not app.screen.query(selector)
                assert app.return_code is None

                await pilot.press("escape")
                assert app.return_code == 0
        assert app.return_value is None

    asyncio.run(exercise())


@pytest.mark.parametrize("restore", [False, True])
def test_picker_keeps_management_and_requires_restore_before_selection(fake_base, restore):
    transcript = next(fake_base.glob("*/*.jsonl"))
    os.utime(transcript, (0, 0))  # Use the normal archive guard for an inactive session.
    archived = transcript.parent / "archived" / transcript.name
    discover = appmod.discover_projects

    async def exercise():
        app = PiSessionsApp(select_mode=True)
        with patch.object(appmod, "discover_projects", lambda **kw: discover(base=fake_base, **kw)):
            async with app.run_test(size=(120, 40)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("tab")
                assert {"a", "d", "n", "e", "l", "c"} <= app.screen.active_bindings.keys()
                await pilot.press("d")
                assert len(app.screen_stack) == 2
                await pilot.press("enter")  # Delete dialog defaults to No, not picker Select.
                assert len(app.screen_stack) == 1 and transcript.is_file()

                await pilot.press("a")
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert archived.is_file() and not transcript.exists()
                await pilot.press("enter")
                assert app.return_code is None
                assert "restore it first" in str(app.query_one("#status", Static).render())
                if restore:
                    await pilot.press("a")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    assert transcript.is_file() and not archived.exists()
                    await pilot.press("enter")
                else:
                    await pilot.press("escape")

        if restore:
            assert isinstance(app.return_value, ResumeRequest)
            assert app.return_value.file == str(transcript)
        else:
            assert app.return_value is None and archived.is_file()

    asyncio.run(exercise())


async def _exercise_export(tmp_path: Path) -> None:
    import json

    from textual.widgets import Input

    projects = _fake_projects()
    # give the first session a real transcript so the export has content
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text(
        json.dumps({"type": "message", "message": {"role": "user", "content": "hello"}}) + "\n",
        encoding="utf-8",
    )
    projects[0].sessions[0].jsonl_path = transcript

    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("tab")  # focus the sessions pane
            await pilot.press("e")
            await pilot.pause()
            app.screen.query_one("#export-path", Input).value = str(tmp_path)
            await pilot.press("enter")
            await pilot.pause()
            exported = [p for p in tmp_path.iterdir() if p.suffix == ".md"]
            assert len(exported) == 1
            assert "### You\n\nhello" in exported[0].read_text(encoding="utf-8")

            # escape cancels without writing anything
            await pilot.press("e")
            await pilot.press("escape")
            await pilot.pause()
            assert len([p for p in tmp_path.iterdir() if p.suffix == ".md"]) == 1


def test_export_from_ui(tmp_path):
    asyncio.run(_exercise_export(tmp_path))


async def _exercise_refresh_keeps_selection() -> None:
    from textual.widgets import DataTable

    state = {"extra": False}

    def build(**_kw):
        projects = _fake_projects()
        if state["extra"]:
            fresh = Session(
                session_id="s-new",
                jsonl_path=Path("/nonexistent/new.jsonl"),
                project_path="/tmp/x",
                first_prompt="brand new session",
                is_live=True,
            )
            projects[0].sessions.insert(0, fresh)
        return projects

    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", build):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            stable = app.query_one("#sessions-table", DataTable)
            await pilot.press("tab")  # sessions pane
            await pilot.press("j")  # second session
            await pilot.pause()
            before = app._current_session()
            assert before is not None and before.first_prompt == "write docs"

            # a rescan that prepends a new live session must not move the cursor
            state["extra"] = True
            app._tick_refresh()
            await app.workers.wait_for_complete()
            for _ in range(4):
                await pilot.pause()

            after = app._current_session()
            assert stable.row_count == 3
            assert after is not None and after.first_prompt == "write docs"


def test_refresh_keeps_selection():
    asyncio.run(_exercise_refresh_keeps_selection())


async def _exercise_watch(tmp_path: Path) -> None:
    import json

    projects = _fake_projects()
    session = projects[0].sessions[0]
    transcript = tmp_path / "watched.jsonl"
    transcript.write_text(
        json.dumps({"type": "message", "message": {"role": "user", "content": "hello"}}) + "\n",
        encoding="utf-8",
    )
    session.jsonl_path = transcript
    session.project_path = str(tmp_path)
    session.is_live = True

    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("tab")  # sessions pane
            assert app._watch_state(session) == ""

            await pilot.press("l")  # start following
            await pilot.pause()
            doc = tmp_path / f"_session_{session.session_id}.md"
            assert doc.is_file()
            assert app._watch_state(session) == "live"
            assert "### You\n\nhello" in doc.read_text(encoding="utf-8")

            # the details pane advertises the document path
            console = Console(width=100, record=True, file=io.StringIO())
            console.print(app.query_one("#preview-content", Static).content)
            assert "Live document" in console.export_text()

            await pilot.press("l")  # stop following
            await pilot.pause()
            assert doc.is_file()  # the file stays behind
            assert app._watch_state(session) == "stale"


def test_watch_toggle_creates_and_keeps_document(tmp_path):
    asyncio.run(_exercise_watch(tmp_path))


async def _exercise_refresh_keeps_scroll() -> None:
    projects = _fake_projects()
    projects[0].sessions = [
        Session(
            session_id=f"s{i}",
            jsonl_path=Path(f"/nonexistent/s{i}.jsonl"),
            project_path="/tmp/x",
            first_prompt=f"task {i}",
        )
        for i in range(60)
    ]
    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            from textual.widgets import DataTable

            st = app.query_one("#sessions-table", DataTable)
            await pilot.press("tab")  # sessions pane
            for _ in range(40):
                await pilot.press("j")
            st.scroll_to(y=st.scroll_y - 3, animate=False, immediate=True)
            await pilot.pause()
            row, scroll_y = st.cursor_row, st.scroll_y
            assert scroll_y > 0

            app._tick_refresh()  # auto-refresh rescan
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert st.cursor_row == row
            assert st.scroll_y == scroll_y


def test_refresh_keeps_selection_and_scroll():
    asyncio.run(_exercise_refresh_keeps_scroll())


async def _exercise_refresh_keeps_project_sharing_path() -> None:
    # two project rows can share a path: the selection follows the directory
    projects = _fake_projects()
    projects[1].project_path = projects[0].project_path
    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            from textual.widgets import DataTable

            pt = app.query_one("#projects-table", DataTable)
            pt.move_cursor(row=1)
            await pilot.pause()
            selected = app._current_project()

            app._tick_refresh()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app._current_project() is selected


def test_refresh_keeps_project_sharing_a_path():
    asyncio.run(_exercise_refresh_keeps_project_sharing_path())


async def _exercise_square_brackets_in_titles(tmp_path: Path) -> None:
    """A session named with /name can contain anything, including markup."""
    from textual.widgets import Static

    projects = _fake_projects()
    projects[0].sessions[0].summary = "[urgent] refactor the parser"
    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # the status bar must show the name whole, not swallow the brackets
            app._set_status("Session deleted: [urgent] refactor the parser")
            await pilot.pause()
            assert "[urgent]" in str(app.query_one("#status", Static).render())

            # and so must a dialog built from the same title
            await pilot.press("tab")
            await pilot.press("e")
            await pilot.pause()
            title = str(app.screen.query_one("#export-title", Static).render())
            assert "[urgent]" in title
            await pilot.press("escape")
            await pilot.pause()


def test_square_brackets_in_titles_survive(tmp_path):
    asyncio.run(_exercise_square_brackets_in_titles(tmp_path))


async def _exercise_focused_pane_border() -> None:
    from textual.color import Color

    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: {}),
        patch.object(appmod, "save_settings", lambda _s: None),
    ):
        app = PiSessionsApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            app.theme = "monokai"
            await pilot.pause()
            accent = Color.parse(app.current_theme.accent)
            primary = Color.parse(app.current_theme.primary)
            projects = app.query_one("#projects-table")
            sessions = app.query_one("#sessions-table")
            assert projects.styles.border_top[1] == accent
            assert sessions.styles.border_top[1] == primary

            # the accent border follows the focus
            await pilot.press("tab")
            await pilot.pause()
            assert projects.styles.border_top[1] == primary
            assert sessions.styles.border_top[1] == accent


def test_focused_pane_border_uses_accent():
    asyncio.run(_exercise_focused_pane_border())


async def _exercise_drag_border(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: settings_mod.load_settings(settings_path)),
        patch.object(
            appmod, "save_settings", lambda s: settings_mod.save_settings(s, settings_path)
        ),
    ):
        # built inside the patch: __init__ reads the saved layout
        app = PiSessionsApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            group = app.query_one("#group")
            assert group.region.width == 80

            # the panes touch: no gap between the left column and Conversation
            assert app.query_one("#conv-scroll").region.x == 80

            # wide: dragging the left column's right border to column 49 narrows it
            await pilot.mouse_down(None, offset=(79, 10))
            await pilot.hover(None, offset=(49, 10))
            await pilot.mouse_up(None, offset=(49, 10))
            await pilot.pause()
            assert group.region.width == 50
            saved = appmod.load_settings()["layout"]
            assert saved["wide"] == {"group": {"width": 31.25}}

            # narrow: the wide width is dropped, the CSS layout takes over
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert group.region.width == 120

            # back to wide: the dragged width comes back
            await pilot.resize_terminal(160, 40)
            await pilot.pause()
            assert group.region.width == 50

            # double-click puts the default 50% back and forgets the drag
            # (on Conversation's left border: either side of the seam works)
            await pilot.double_click(None, offset=(50, 10))
            await pilot.pause()
            assert group.region.width == 80
            assert appmod.load_settings()["layout"]["wide"] == {}

            # a click without moving must not shift the pane by a rounding cell
            sessions = app.query_one("#sessions-table")
            before = sessions.region.height
            seam = (10, sessions.region.y)  # Sessions' top border, under Projects
            await pilot.click(None, offset=seam)
            await pilot.pause()
            assert sessions.region.height == before

            # drag, then two double-clicks in a row: each one resets
            await pilot.mouse_down(None, offset=seam)
            await pilot.hover(None, offset=(10, 30))
            await pilot.mouse_up(None, offset=(10, 30))
            await pilot.pause()
            assert sessions.region.height != before
            seam = (10, sessions.region.y)  # the border moved with the drag
            for _ in range(2):
                await pilot.double_click(None, offset=seam)
                await pilot.pause()
                assert sessions.region.height == before

            # Sessions' bottom border resizes #sub; Projects above keeps its rows
            projects = app.query_one("#projects-table")
            rows = projects.region.height
            seam = (10, sessions.region.bottom - 1)
            await pilot.mouse_down(None, offset=seam)
            await pilot.hover(None, offset=(10, seam[1] + 4))
            await pilot.mouse_up(None, offset=(10, seam[1] + 4))
            await pilot.pause()
            assert projects.region.height == rows
            assert sessions.region.height == before + 4


def test_drag_border_resizes_and_remembers(tmp_path):
    asyncio.run(_exercise_drag_border(tmp_path))


def test_load_layout_ignores_malformed_entries():
    layout = appmod._load_layout(
        {
            "wide": {"group": {"width": 40}, "conv-scroll": {"width": 10}},
            "narrow": {"group": {"height": "x"}},
        }
    )
    assert layout == {"wide": {"group": {"width": 40.0}}, "narrow": {}}
    assert appmod._load_layout(None) == {"wide": {}, "narrow": {}}


async def _exercise_reset_layout(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    # sizes dragged earlier in both layouts
    settings_mod.save_settings(
        {
            "theme": "nord",
            "layout": {"wide": {"group": {"width": 30}}, "narrow": {"group": {"height": 70}}},
        },
        settings_path,
    )
    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: settings_mod.load_settings(settings_path)),
        patch.object(
            appmod, "save_settings", lambda s: settings_mod.save_settings(s, settings_path)
        ),
    ):
        # built inside the patch: __init__ reads the saved layout
        app = PiSessionsApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            group = app.query_one("#group")
            assert group.region.width == 48

            commands = [c.title for c in app.get_system_commands(app.screen)]
            assert "Reset layout" in commands
            app.action_reset_layout()
            await pilot.pause()
            assert group.region.width == 80
            saved = settings_mod.load_settings(settings_path)
            assert saved["layout"] == {"wide": {}, "narrow": {}}
            assert saved["theme"] == "nord"

            # the narrow layout is back to its default too (50% of 37 rows)
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert group.region.height == 18


def test_reset_layout_command(tmp_path):
    asyncio.run(_exercise_reset_layout(tmp_path))


async def _exercise_title_fits() -> None:
    projects = _fake_projects()
    projects[0].project_path = "/tmp/" + "y" * 200
    projects[0].sessions[0].first_prompt = "x" * 200
    app = PiSessionsApp()
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.pause()
            tables = [app.query_one("#projects-table"), app.query_one("#sessions-table")]
            narrow = []
            for t in tables:
                # long names are elided instead of scrolling the table sideways
                assert t.virtual_size.width <= t.scrollable_content_region.width
                narrow.append(t.columns["fit"].width)
            await pilot.resize_terminal(200, 40)
            await pilot.pause()
            await pilot.pause()
            for t, before in zip(tables, narrow, strict=True):
                assert t.columns["fit"].width > before


def test_title_column_fits_pane():
    asyncio.run(_exercise_title_fits())


async def _exercise_sort() -> None:
    app = PiSessionsApp()
    projects = _fake_projects()
    for s, n in zip(projects[0].sessions, (3, 9), strict=True):
        s.message_count = n
    with patch.object(appmod, "discover_projects", lambda **_kw: projects):
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            from textual.widgets import DataTable

            st = app.query_one("#sessions-table", DataTable)

            def click_msgs() -> None:
                col = st.columns["msgs"]
                idx = st.get_column_index("msgs")
                app.on_data_table_header_selected(
                    DataTable.HeaderSelected(st, col.key, idx, col.label)
                )

            # header hover lights only the hovered label, and only a sortable one
            from textual.coordinate import Coordinate

            msgs = Coordinate(-1, st.get_column_index("msgs"))
            title = Coordinate(-1, st.get_column_index("fit"))
            assert st._should_highlight(msgs, msgs, "row")
            assert not st._should_highlight(title, title, "row")
            assert not st._should_highlight(msgs, Coordinate(-1, msgs.column + 1), "row")

            ids = lambda: [s.session_id for s in app._vsessions]  # noqa: E731
            assert ids() == ["s1", "s2"]
            click_msgs()
            assert ids() == ["s2", "s1"] and str(st.columns["msgs"].label) == "Msgs ▼"
            click_msgs()
            assert ids() == ["s1", "s2"] and str(st.columns["msgs"].label) == "Msgs ▲"
            click_msgs()
            assert ids() == ["s1", "s2"] and str(st.columns["msgs"].label) == "Msgs"

            # every sortable column, both tables, must have comparable keys
            for table in (st, app.query_one("#projects-table", DataTable)):
                for key in appmod.SORTABLE[table.id]:
                    col = table.columns[key]
                    for _ in range(3):
                        app.on_data_table_header_selected(
                            DataTable.HeaderSelected(table, col.key, 0, col.label)
                        )


def test_header_click_cycles_sort() -> None:
    asyncio.run(_exercise_sort())


async def _exercise_show_modified_setting(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: settings_mod.load_settings(settings_path)),
        patch.object(
            appmod, "save_settings", lambda s: settings_mod.save_settings(s, settings_path)
        ),
    ):
        app = PiSessionsApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#sessions-table")
            assert "modified" in table.columns
            app._sort["sessions-table"] = ("modified", True)
            wide_before = table.columns["fit"].width

            commands = [c.title for c in app.get_system_commands(app.screen)]
            assert "Settings" in commands
            app.action_show_settings()
            await pilot.pause()
            await pilot.click("#show_modified")
            await pilot.pause()
            assert "modified" not in table.columns
            assert table.row_count and len(table.get_row_at(0)) == len(table.columns)
            assert "sessions-table" not in app._sort  # sort on a hidden column is dropped
            assert settings_mod.load_settings(settings_path)["show_modified"] is False

            def details() -> str:
                console = Console(width=200, record=True, file=io.StringIO())
                console.print(app.query_one("#preview-content", Static).content)
                return console.export_text()

            assert "Resume command : press c to copy" in details()  # hidden by default
            await pilot.click("#show_resume_command")
            await pilot.pause()
            assert "Resume command : press c to copy" not in details()
            assert "Resume command" in details()
            assert settings_mod.load_settings(settings_path)["show_resume_command"] is True
            await pilot.press("escape")
            await pilot.pause()
            assert table.columns["fit"].width > wide_before  # Title takes the room

        # the choice survives a restart
        app = PiSessionsApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "modified" not in app.query_one("#sessions-table").columns


def test_show_modified_setting(tmp_path):
    asyncio.run(_exercise_show_modified_setting(tmp_path))


async def _exercise_fit_table_shrink() -> None:
    from textual.app import App

    class FitApp(App):
        def compose(self):
            yield appmod.FitTable()

        def on_mount(self) -> None:
            table = self.query_one(appmod.FitTable)
            table.styles.width = 60
            table.add_column("Title", key="fit")
            table.add_column("Tokens")
            table.add_row("x" * 80, "12.3k")

    app = FitApp()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        table = app.query_one(appmod.FitTable)
        table.styles.width = 40
        # no further events: the fit width must settle within the resize's idle
        await asyncio.sleep(0.3)
        assert table.virtual_size.width == table.size.width
        assert not table.show_horizontal_scrollbar


def test_fit_table_shrink_leaves_no_horizontal_scrollbar():
    asyncio.run(_exercise_fit_table_shrink())


async def _exercise_theme_preview(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_mod.save_settings({"theme": "nord"}, settings_path)
    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: settings_mod.load_settings(settings_path)),
        patch.object(
            appmod, "save_settings", lambda s: settings_mod.save_settings(s, settings_path)
        ),
    ):
        app = PiSessionsApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            app.search_themes()
            await pilot.pause()
            assert app.theme == "nord"  # opening alone doesn't switch
            await pilot.press("down")
            await pilot.pause()
            previewed = app.theme
            assert previewed != "nord"
            await pilot.press("escape")
            await pilot.pause()
            assert app.theme == "nord"  # Esc restores

            app.search_themes()
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            assert app.theme == previewed  # Enter keeps the preview
            assert settings_mod.load_settings(settings_path)["theme"] == previewed

            # a click highlights and selects in one go, after the palette closed
            app.search_themes()
            await pilot.pause()
            await pilot.click(CommandList, offset=(3, 12))
            await pilot.pause()
            assert app.theme != previewed


def test_theme_preview(tmp_path):
    asyncio.run(_exercise_theme_preview(tmp_path))


async def _exercise_one_side_panel() -> None:
    with (
        patch.object(appmod, "discover_projects", lambda **_kw: _fake_projects()),
        patch.object(appmod, "load_settings", lambda: {}),
        patch.object(appmod, "save_settings", lambda _s: None),
    ):
        app = PiSessionsApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()

            def panels() -> tuple[int, int]:
                return len(app.screen.query("HelpPanel")), len(app.screen.query("SettingsPanel"))

            app.action_show_help_panel()
            await pilot.pause()
            assert panels() == (1, 0)
            app.action_show_settings()
            await pilot.pause()
            assert panels() == (0, 1)  # settings replaces keys
            app.action_show_help_panel()
            await pilot.pause()
            assert panels() == (1, 0)  # and the other way round
            await pilot.press("escape")
            await pilot.pause()
            assert panels() == (0, 0)


def test_keys_and_settings_panels_are_exclusive():
    asyncio.run(_exercise_one_side_panel())
