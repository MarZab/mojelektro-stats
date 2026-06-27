from __future__ import annotations

import httpx
import pytest

from mojelektro._http import raise_for_status
from mojelektro.errors import (
    AuthError,
    InvalidRequestError,
    MojElektroError,
    NotFoundError,
)


def _response(status: int, body: str = "") -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/x")
    return httpx.Response(status, request=request, text=body)


def test_2xx_does_not_raise() -> None:
    raise_for_status(_response(200))


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error(status: int) -> None:
    with pytest.raises(AuthError) as exc:
        raise_for_status(_response(status))
    assert exc.value.status_code == status


def test_not_found() -> None:
    with pytest.raises(NotFoundError):
        raise_for_status(_response(404))


def test_bad_request() -> None:
    with pytest.raises(InvalidRequestError):
        raise_for_status(_response(400, body='{"message":"bad input"}'))


def test_server_error_is_base_class() -> None:
    with pytest.raises(MojElektroError) as exc:
        raise_for_status(_response(503))
    assert exc.value.status_code == 503
    assert not isinstance(exc.value, AuthError | NotFoundError | InvalidRequestError)
