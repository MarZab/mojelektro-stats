from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from cli import app
from mojelektro import Server


def test_auth_error_exits_3() -> None:
    base = Server.TEST.base_url
    with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(401, json={"opisNapake": "x"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert result.exit_code == 3
    assert "AuthError" in result.stderr


def test_not_found_exits_4() -> None:
    base = Server.TEST.base_url
    with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(404, json={"opisNapake": "no"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert result.exit_code == 4
    assert "NotFoundError" in result.stderr


def test_transport_error_exits_5() -> None:
    base = Server.TEST.base_url
    with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").mock(side_effect=httpx.ConnectError("x"))
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert result.exit_code == 5
    assert "TransportError" in result.stderr


def test_invalid_request_exits_2() -> None:
    base = Server.TEST.base_url
    with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(400, json={"opisNapake": "bad"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert result.exit_code == 2
    assert "InvalidRequestError" in result.stderr


def test_other_mojelektro_error_exits_1() -> None:
    base = Server.TEST.base_url
    with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(503, json={"opisNapake": "down"})
        result = CliRunner().invoke(app, ["--token", "t", "--server", "test", "info", "abc"])
    assert result.exit_code == 1
    assert "MojElektroError" in result.stderr
