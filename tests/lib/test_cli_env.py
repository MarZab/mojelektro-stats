from __future__ import annotations

from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from cli import app
from cli._env import USAGE_POINT_ENVVAR, load_dotenv, parse_dotenv
from mojelektro_api import Server


def test_parse_dotenv_handles_comments_quotes_and_export() -> None:
    text = "\n".join(
        [
            "# comment",
            "",
            "MOJELEKTRO_APIKEY=abc",
            'MOJELEKTRO_USAGE_POINT="4-123"',
            "export QUOTED='x y'",
            "NOT_A_PAIR",
            "EMPTY=",
        ]
    )
    assert parse_dotenv(text) == {
        "MOJELEKTRO_APIKEY": "abc",
        "MOJELEKTRO_USAGE_POINT": "4-123",
        "QUOTED": "x y",
        "EMPTY": "",
    }


def test_load_dotenv_does_not_override_existing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from-file\nB=from-file\n", encoding="utf-8")
    environ = {"A": "from-shell"}
    load_dotenv(env_file, environ)
    assert environ == {"A": "from-shell", "B": "from-file"}


def test_load_dotenv_missing_file_is_noop(tmp_path: Path) -> None:
    environ: dict[str, str] = {}
    load_dotenv(tmp_path / "missing.env", environ)
    assert environ == {}


def test_readings_uses_usage_point_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the env var set, `readings` no longer falls back to help; in a
    non-TTY run it gets as far as asking for --type."""
    monkeypatch.setenv(USAGE_POINT_ENVVAR, "4-123")
    result = CliRunner().invoke(app, ["readings"])
    assert result.exit_code == 2
    assert "--type" in result.stderr


def test_info_uses_usage_point_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(USAGE_POINT_ENVVAR, "abc")
    with respx.mock(base_url=Server.TEST.base_url) as router:
        route = router.get("/merilno-mesto/abc").respond(404, json={"opisNapake": "no"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info"])
    assert route.called
    assert result.exit_code == 4


def test_explicit_argument_beats_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(USAGE_POINT_ENVVAR, "from-env")
    with respx.mock(base_url=Server.TEST.base_url) as router:
        route = router.get("/merilno-mesto/abc").respond(404, json={"opisNapake": "no"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert route.called
    assert result.exit_code == 4
