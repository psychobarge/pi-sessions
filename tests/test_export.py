from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pi_sessions.core.export import (
    MARKDOWN,
    RAW,
    ExportError,
    default_filename,
    export_session,
    markdown_chunks,
    normalize_markdown,
    resolve_destination,
)
from pi_sessions.core.models import Entry, Session, TokenStats

from conftest import assistant, header, text, user, write_jsonl


def _session(tmp_path: Path) -> Session:
    jsonl = tmp_path / "sess.jsonl"
    objs = [
        header(),
        user("u0", None, "how do I sort a list?"),
        assistant("a0", "u0", [
            text("Use `sorted()`:\n\n```python\nsorted(xs)\n```"),
            {"type": "toolCall", "id": "c", "name": "bash", "arguments": {"command": "python3 -c 1"}},
        ]),
        {"type": "message", "id": "b0", "parentId": "a0",
         "message": {"role": "bashExecution", "command": "ls", "output": "a.txt"}},
        {"type": "compaction", "id": "c0", "parentId": "b0", "summary": "s", "tokensBefore": 10},
    ]
    for o in objs:
        o.pop("timestamp", None)  # exercise the no-timestamp fallback
    write_jsonl(jsonl, objs)
    return Session(
        session_id="abc-123",
        jsonl_path=jsonl,
        project_path="/tmp/proj",
        summary="Sorting lists in Python",
        message_count=3,
        modified=datetime(2026, 8, 1, 10, 30),
        model="deepseek/deepseek-flash",
        parent_session="/s/parent.jsonl",
        tokens=TokenStats(input=10, output=20, cost=0.0123),
    )


def test_default_filename_uses_date_and_slug(tmp_path):
    s = _session(tmp_path)
    assert default_filename(s, MARKDOWN) == "2026-08-01-sorting-lists-in-python.md"
    assert default_filename(s, RAW) == "2026-08-01-sorting-lists-in-python.jsonl"


def test_directory_input_gets_generated_filename(tmp_path):
    s = _session(tmp_path)
    dest = resolve_destination(str(tmp_path), s, MARKDOWN)
    assert dest.parent == tmp_path
    assert dest.name.endswith("-sorting-lists-in-python.md")


def test_explicit_filename_is_respected(tmp_path):
    s = _session(tmp_path)
    dest = resolve_destination(str(tmp_path / "notes.md"), s, MARKDOWN)
    assert dest == tmp_path / "notes.md"


def test_existing_files_are_never_overwritten(tmp_path):
    s = _session(tmp_path)
    (tmp_path / "notes.md").write_text("keep me", encoding="utf-8")
    dest = resolve_destination(str(tmp_path / "notes.md"), s, MARKDOWN)
    assert dest == tmp_path / "notes-1.md"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "keep me"


def test_missing_directory_raises(tmp_path):
    s = _session(tmp_path)
    with pytest.raises(ExportError):
        resolve_destination(str(tmp_path / "nope" / "x.md"), s, MARKDOWN)


def test_markdown_export_content(tmp_path):
    s = _session(tmp_path)
    dest = export_session(s, str(tmp_path / "out.md"), MARKDOWN)
    text = dest.read_text(encoding="utf-8")
    # front matter
    assert text.startswith("---\n")
    assert 'title: "Sorting lists in Python"' in text
    assert 'session_id: "abc-123"' in text
    assert 'model: "deepseek/deepseek-flash"' in text
    assert 'parent_session: "/s/parent.jsonl"' in text
    assert "  total: 30" in text
    assert "cost: 0.0123" in text
    assert "exported_by: pi-sessions" in text
    # conversation
    # fixtures carry no per-record timestamps, so the day section falls back
    assert "## Conversation\n" in text
    assert "### You\n\nhow do I sort a list?" in text
    assert "### Pi" in text
    assert "```python\nsorted(xs)\n```" in text  # code fences survive verbatim
    assert "- ⚙ `bash: python3 -c 1`" in text
    assert "- ⌘ `! ls`" in text
    assert "_⧉ compaction (10 tokens summarized)_" in text


def test_raw_export_is_byte_identical(tmp_path):
    s = _session(tmp_path)
    dest = export_session(s, str(tmp_path / "copy.jsonl"), RAW)
    assert dest.read_bytes() == s.jsonl_path.read_bytes()


def test_headings_are_demoted_below_role_headings():
    out = normalize_markdown("## Section\ntext\n### Sub")
    assert "#### Section" in out
    assert "##### Sub" in out


def test_turns_are_grouped_into_one_section_per_day():
    stamps = [
        datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 3, 12, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc),
    ]
    entries = [
        Entry("user", "wednesday question", stamps[0]),
        Entry("assistant", "wednesday answer", stamps[1]),
        Entry("user", "friday question", stamps[2]),
    ]
    out = "".join(markdown_chunks(entries))
    headings = [ln for ln in out.splitlines() if ln.startswith("#")]
    # days are derived the same way the renderer does it, so the assertion
    # holds in any timezone rather than only where UTC dates survive
    expected = sorted({f"## {s.astimezone():%Y-%m-%d}" for s in stamps})
    # one section per distinct day, never one per turn
    assert [h for h in headings if h.startswith("## ")] == expected
    assert sum(h.startswith("### ") for h in headings) == 3
    # the day carries the date, so the speaker heading only needs the clock
    assert any(h.startswith("### You · ") and len(h) == len("### You · 00:00") for h in headings)


def test_headings_inside_code_fences_are_untouched():
    out = normalize_markdown("```\n## not a heading\n```")
    assert "## not a heading" in out


def test_bare_fences_get_txt_info_string():
    assert "```txt" in normalize_markdown("```\nplain output\n```")
    assert "```python" in normalize_markdown("```python\nx = 1\n```")


def test_blank_line_inserted_before_glued_list():
    out = normalize_markdown("**Lead in.** Two changes:\n- first\n- second")
    assert "Two changes:\n\n- first\n- second" in out


def test_insight_block_gets_inner_blank_lines():
    text = "`★ Insight ─────`\n- point\n`─────────────`"
    out = normalize_markdown(text)
    assert "`★ Insight ─────`\n\n- point\n\n`─────────────`" == out


def test_consecutive_tool_calls_form_a_tight_list(tmp_path):
    jsonl = tmp_path / "tools.jsonl"
    write_jsonl(jsonl, [header(), assistant("a0", None, [
        {"type": "toolCall", "id": "1", "name": "edit", "arguments": {"path": "/a.py"}},
        {"type": "toolCall", "id": "2", "name": "edit", "arguments": {"path": "/b.py"}},
    ])])
    s = _session(tmp_path)
    s.jsonl_path = jsonl
    dest = export_session(s, str(tmp_path / "tools.md"), MARKDOWN)
    assert "- ⚙ `edit: /a.py`\n- ⚙ `edit: /b.py`\n" in dest.read_text(encoding="utf-8")


def test_command_output_is_fenced_as_txt(tmp_path):
    s = _session(tmp_path)
    dest = export_session(s, str(tmp_path / "out.md"), MARKDOWN)
    text = dest.read_text(encoding="utf-8")
    assert "```txt\na.txt\n```" in text


def test_export_missing_transcript_raises(tmp_path):
    s = _session(tmp_path)
    s.jsonl_path.unlink()
    with pytest.raises(ExportError):
        export_session(s, str(tmp_path), MARKDOWN)
