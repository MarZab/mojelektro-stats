from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from mojelektro_api.client import MojElektroClient
from mojelektro_api.errors import AuthError, NotFoundError, TransportError
from mojelektro_api.models import Server


@pytest.mark.asyncio
async def test_client_sets_token_header() -> None:
    async with MojElektroClient("tok", server=Server.TEST) as client:
        assert client._http.headers["X-API-TOKEN"] == "tok"


@pytest.mark.asyncio
async def test_client_uses_server_base_url() -> None:
    async with MojElektroClient("tok", server=Server.TEST) as client:
        assert str(client._http.base_url).rstrip("/") == Server.TEST.base_url


@pytest.mark.asyncio
async def test_client_accepts_injected_http() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
    injected = httpx.AsyncClient(transport=transport, base_url=Server.TEST.base_url)
    async with MojElektroClient("tok", server=Server.TEST, http=injected) as client:
        assert client._http is injected


@pytest.mark.asyncio
async def test_get_merilno_mesto_returns_parsed_json() -> None:
    base = Server.TEST.base_url
    payload = {"gsrn": "100000000000000000", "merilneTocke": []}
    async with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(200, json=payload)
        async with MojElektroClient("tok", server=Server.TEST) as client:
            out = await client.get_merilno_mesto("abc")
    assert out == payload


@pytest.mark.asyncio
async def test_401_raises_auth_error() -> None:
    base = Server.TEST.base_url
    async with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(401, json={"opisNapake": "nope"})
        async with MojElektroClient("tok", server=Server.TEST) as client:
            with pytest.raises(AuthError):
                await client.get_merilno_mesto("abc")


@pytest.mark.asyncio
async def test_404_raises_not_found() -> None:
    base = Server.TEST.base_url
    async with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").respond(404, json={"opisNapake": "no"})
        async with MojElektroClient("tok", server=Server.TEST) as client:
            with pytest.raises(NotFoundError):
                await client.get_merilno_mesto("abc")


@pytest.mark.asyncio
async def test_connect_error_wrapped_in_transport_error() -> None:
    base = Server.TEST.base_url
    async with respx.mock(base_url=base) as router:
        router.get("/merilno-mesto/abc").mock(side_effect=httpx.ConnectError("nope"))
        async with MojElektroClient("tok", server=Server.TEST) as client:
            with pytest.raises(TransportError) as exc:
                await client.get_merilno_mesto("abc")
    assert isinstance(exc.value.original, httpx.ConnectError)


@pytest.mark.asyncio
async def test_get_meter_readings_passes_date_params() -> None:
    base = Server.TEST.base_url
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        for key, value in request.url.params.multi_items():
            captured[key] = value
        return httpx.Response(200, json={"usagePoint": "GSRN", "intervalBlocks": []})

    transport = httpx.MockTransport(_handler)
    injected = httpx.AsyncClient(transport=transport, base_url=base)
    async with MojElektroClient("tok", server=Server.TEST, http=injected) as client:
        out = await client.get_meter_readings(
            "GSRN",
            date(2026, 5, 1),
            date(2026, 6, 1),
            options=["32.0.2"],
        )

    assert captured["usagePoint"] == "GSRN"
    assert captured["startTime"] == "2026-05-01"
    assert captured["endTime"] == "2026-06-01"
    assert captured["option"] == "32.0.2"
    assert out["usagePoint"] == "GSRN"
