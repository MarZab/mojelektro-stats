from __future__ import annotations

import pytest

from mojelektro_api.errors import (
    AuthError,
    InvalidRequestError,
    MojElektroError,
    NotFoundError,
    TransportError,
)


def test_hierarchy() -> None:
    for cls in (AuthError, InvalidRequestError, NotFoundError, TransportError):
        assert issubclass(cls, MojElektroError)


def test_transport_error_keeps_original() -> None:
    original = ConnectionError("boom")
    err = TransportError("transport failed", original=original)
    assert err.original is original


def test_mojelektro_error_carries_status_code() -> None:
    err = MojElektroError("nope", status_code=503)
    assert err.status_code == 503
    assert "503" in repr(err)


def test_default_status_code_is_none() -> None:
    err = MojElektroError("nope")
    assert err.status_code is None


def test_invalid_request_error_subclass() -> None:
    with pytest.raises(MojElektroError):
        raise InvalidRequestError("bad")
