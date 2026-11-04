from __future__ import annotations

from datetime import datetime, timezone

from pi_sessions.core.parser import (
    compute_token_stats,
    iter_conversation,
    read_conversation_tail,
)

from conftest import SID, USAGE, assistant, header, text, user, write_jsonl, write_transcript


def test_token_stats_and_metadata(tmp_path):
    f = tmp_path / "s.jsonl"
    write_transcript(f, exchanges=3, cwd="/home/user/proj")
    stats = compute_token_stats(f)
    assert stats.input == 30
    assert stats.output == 15
    assert stats.total == 45
    assert round(stats.cost, 6) == 0.003
    assert stats.messages == 6
    assert stats.session_id == SID
    assert stats.cwd == "/home/user/proj"
    assert stats.created == "2026-10-14T14:40:04.385Z"
    assert stats.first_prompt == "question 0"
    assert stats.model == "deepseek/deepseek-flash"
    assert stats.branches == 1


def test_name_last_one_wins_and_extra_usage_counts(tmp_path):
    f = tmp_path / "s.jsonl"
    write_jsonl(
        f,
        [
            header(parentSession="/x/parent.jsonl"),
            user("u0", None, "hi"),
            {"type": "session_info", "id": "n1", "parentId": "u0", "name": "first"},
            {"type": "session_info", "id": "n2", "parentId": "n1", "name": " final "},
            {"type": "usage", "id": "g1", "parentId": "n2", "kind": "cache_warm", "usage": USAGE},
            {"type": "compaction", "id": "c1", "parentId": "g1", "summary": "s", "usage": USAGE},
            {"type": "model_change", "id": "m1", "parentId": "c1", "provider": "openai", "modelId": "gpt-x"},
        ],
    )
    stats = compute_token_stats(f)
    assert stats.name == "final"
    assert stats.parent_session == "/x/parent.jsonl"
    assert stats.input == 20  # usage entry + compaction usage
    assert stats.messages == 1
    assert stats.model == "openai/gpt-x"


def test_malformed_lines_are_ignored(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text('not json\n{"type":"message"}\n[1]\n{"broken\n', encoding="utf-8")
    stats = compute_token_stats(f)
    assert stats.total == 0
    assert read_conversation_tail(f) == []


def test_conversation_tail_roles(tmp_path):
    f = tmp_path / "s.jsonl"
    write_jsonl(
        f,
        [
            header(),
            {"type": "message", "id": "s0", "parentId": None,
             "message": {"role": "system", "content": "", "sections": {}}},
            user("u0", "s0", "hello"),
            assistant("a0", "u0", [
                {"type": "thinking", "thinking": "hmm"},
                text("hi!"),
                {"type": "toolCall", "id": "c", "name": "bash", "arguments": {"command": "ls -la"}},
                {"type": "toolCall", "id": "d", "name": "read", "arguments": {"path": "a.py"}},
            ]),
            {"type": "message", "id": "t0", "parentId": "a0",
             "message": {"role": "toolResult", "toolName": "bash", "content": [text("out")]}},
            {"type": "message", "id": "b0", "parentId": "t0",
             "message": {"role": "bashExecution", "command": "git status", "output": "clean\n"}},
            {"type": "custom_message", "id": "x0", "parentId": "b0", "customType": "plan",
             "content": "PLAN MODE", "display": True},
            {"type": "custom_message", "id": "x1", "parentId": "x0", "customType": "hidden",
             "content": "secret", "display": False},
            {"type": "compaction", "id": "c0", "parentId": "x1", "summary": "s", "tokensBefore": 5000},
            {"type": "custom", "id": "y0", "parentId": "c0", "customType": "z", "data": {}},
            {"type": "message", "id": "w0", "parentId": "y0",
             "message": {"role": "someFutureRole", "content": "?"}},
        ],
    )
    assert [(e.role, e.text) for e in read_conversation_tail(f)] == [
        ("user", "hello"),
        ("assistant", "hi!"),
        ("tool", "bash: ls -la"),
        ("tool", "read: a.py"),
        ("command", "! git status"),
        ("command-output", "clean"),
        ("command-output", "[plan] PLAN MODE"),
        ("marker", "⧉ compaction (5,000 tokens summarized)"),
    ]


def test_user_content_as_plain_string(tmp_path):
    f = tmp_path / "s.jsonl"
    obj = user("u0", None, "x")
    obj["message"]["content"] = "  plain string  "
    write_jsonl(f, [header(), obj])
    assert [e.text for e in read_conversation_tail(f)] == ["plain string"]
    assert compute_token_stats(f).first_prompt == "plain string"


def _branched(f):
    # u0 -> a0 -> u1 (abandoned) ; a0 -> u2 -> a2 (active: written last)
    write_jsonl(
        f,
        [
            header(),
            user("u0", None, "root"),
            assistant("a0", "u0", [text("first answer")]),
            user("u1", "a0", "abandoned question"),
            assistant("a1", "u1", [text("abandoned answer")]),
            user("u2", "a0", "second try"),
            assistant("a2", "u2", [text("better answer")]),
        ],
    )


def test_only_the_active_branch_is_shown(tmp_path):
    f = tmp_path / "s.jsonl"
    _branched(f)
    expected = ["root", "first answer", "second try", "better answer"]
    assert [e.text for e in read_conversation_tail(f)] == expected
    assert [e.text for e in iter_conversation(f)] == expected
    assert compute_token_stats(f).branches == 2


def test_legacy_entries_without_ids_follow_file_order(tmp_path):
    f = tmp_path / "s.jsonl"
    objs = [user("x", None, "one"), assistant("y", None, [text("two")])]
    for o in objs:
        del o["id"], o["parentId"]
    write_jsonl(f, [header(), *objs])
    assert [e.text for e in read_conversation_tail(f)] == ["one", "two"]
    assert [e.text for e in iter_conversation(f)] == ["one", "two"]


def test_entries_carry_entry_timestamps(tmp_path):
    f = tmp_path / "s.jsonl"
    stamped = user("u0", None, "hello", ts="2026-09-05T08:59:59.744Z")
    unstamped = assistant("a0", "u0", [text("hi!")])
    del unstamped["timestamp"]
    malformed = user("u1", "a0", "bye", ts="not a date")
    write_jsonl(f, [header(), stamped, unstamped, malformed])
    a, b, c = read_conversation_tail(f)
    assert a.ts == datetime(2026, 9, 5, 8, 59, 59, 744000, tzinfo=timezone.utc)
    assert b.ts is None
    assert c.ts is None


def test_tail_reads_only_end_of_file(tmp_path):
    f = tmp_path / "s.jsonl"
    write_transcript(f, exchanges=200)
    tail = read_conversation_tail(f, max_entries=5, max_bytes=2000)
    assert len(tail) == 5
    # the freshest entries win
    assert tail[-1].text.endswith("199")
