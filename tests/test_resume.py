from __future__ import annotations

from unittest.mock import patch

import pi_sessions.core.resume as resume
from pi_sessions.core.resume import ResumeRequest, build_resume_command


def test_command_includes_cd_for_existing_directory(tmp_path):
    proj = tmp_path / "my project"  # space forces quoting
    proj.mkdir()
    cmd = build_resume_command(ResumeRequest("abc-123", str(proj), "/s/x_abc-123.jsonl"))
    assert cmd == f"cd '{proj}' && pi --session /s/x_abc-123.jsonl"


def test_command_skips_cd_for_missing_directory(tmp_path):
    cmd = build_resume_command(ResumeRequest("abc", str(tmp_path / "gone"), "/s/f.jsonl"))
    assert cmd == "pi --session /s/f.jsonl"


def test_pi_bin_and_resume_root_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_SESSIONS_PI_BIN", "my-pi")
    monkeypatch.setenv("PI_SESSIONS_RESUME_ROOT", "/root/.pi/agent/sessions")
    with patch.object(resume, "SESSIONS_DIR", tmp_path):
        inside = ResumeRequest("abc", "", str(tmp_path / "--p--" / "f.jsonl"))
        assert build_resume_command(inside) == "my-pi --session /root/.pi/agent/sessions/--p--/f.jsonl"
        outside = ResumeRequest("abc", "", "/elsewhere/f.jsonl")
        assert build_resume_command(outside) == "my-pi --session /elsewhere/f.jsonl"
