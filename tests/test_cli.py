from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from pi_sessions import __main__ as cli
from pi_sessions import __version__
from pi_sessions.core.resume import ResumeRequest


@pytest.fixture
def commands(monkeypatch):
    app = Mock(return_code=0)
    launch = Mock(return_value=app)
    resume = Mock()
    monkeypatch.setattr(cli, "PiSessionsApp", launch)
    monkeypatch.setattr(cli, "execute_resume", resume)
    return app, launch, resume


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_version_exits_without_opening_browser(flag, commands, capsys):
    _, launch, _ = commands
    with pytest.raises(SystemExit) as error:
        cli.main([flag])
    assert error.value.code == 0
    assert capsys.readouterr().out == f"pisessions {__version__}\n"
    launch.assert_not_called()


def test_select_writes_absolute_path_without_launching_pi(commands, tmp_path, monkeypatch, capsys):
    app, launch, resume = commands
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PI_SESSIONS_RESUME_ROOT", "/mounted-elsewhere")
    path = 'my project/é "quoted"\nname.jsonl'
    app.run.return_value = ResumeRequest("abc", "/other/project", path)
    output = tmp_path / "result.json"

    assert cli.main(["--select", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == str(tmp_path / path)
    assert capsys.readouterr().out == ""
    launch.assert_called_once_with(select_mode=True)
    resume.assert_not_called()


@pytest.mark.parametrize("return_code", [0, 1])
def test_select_cancel_or_ui_failure_writes_nothing(commands, tmp_path, return_code):
    app, _, resume = commands
    app.run.return_value = None
    app.return_code = return_code
    output = tmp_path / "result.json"

    assert cli.main(["--select", "--output", str(output)]) == return_code
    assert not output.exists()
    resume.assert_not_called()


def test_select_never_overwrites_output(commands, tmp_path, capsys):
    app, _, resume = commands
    app.run.return_value = ResumeRequest("abc", "", "/sessions/abc.jsonl")
    output = tmp_path / "result.json"
    output.write_text("previous data", encoding="utf-8")

    assert cli.main(["--select", "--output", str(output)]) == 1
    assert "Could not write selection" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "previous data"
    resume.assert_not_called()


@pytest.mark.parametrize("argv", [["--select"], ["--output", "result.json"]])
def test_picker_requires_both_arguments(commands, argv):
    _, launch, _ = commands

    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2
    launch.assert_not_called()


def test_default_mode_still_resumes(commands):
    app, launch, resume = commands
    request = ResumeRequest("abc", "/project", "/sessions/abc.jsonl")
    app.run.return_value = request

    assert cli.main([]) == 0
    launch.assert_called_once_with(select_mode=False)
    resume.assert_called_once_with(request)
