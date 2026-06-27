from __future__ import annotations

import pytest
import respx
import typer

from cli._resolve import resolve_gsrn_mm, resolve_gsrn_mt
from mojelektro_api import MojElektroClient, Server
from mojelektro_api.errors import NotFoundError

_BASE = Server.TEST.base_url


@pytest.mark.asyncio
async def test_resolve_gsrn_mm_passes_through_18_digit_input() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        out = await resolve_gsrn_mm(client, "100000000000000000")
    assert out == "100000000000000000"
    assert not router.routes  # no API call needed


@pytest.mark.asyncio
async def test_resolve_gsrn_mm_looks_up_short_identifier() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        router.get("/merilno-mesto/4-0000000").respond(
            200,
            json={
                "identifikator": {
                    "enotniIdentifikatorMerilnegaMesta": "4-0000000",
                    "gsrn": "100000000000000000",
                },
                "merilneTocke": [{"gsrn": "200000000000000000", "vrsta": "OMTO"}],
            },
        )
        out = await resolve_gsrn_mm(client, "4-0000000")
    assert out == "100000000000000000"


@pytest.mark.asyncio
async def test_resolve_gsrn_mt_passes_through_18_digit_input() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        out = await resolve_gsrn_mt(client, "200000000000000000")
    assert out == "200000000000000000"
    assert not router.routes


@pytest.mark.asyncio
async def test_resolve_gsrn_mt_looks_up_short_identifier() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        router.get("/merilno-mesto/4-0000000").respond(
            200,
            json={
                "identifikator": {
                    "enotniIdentifikatorMerilnegaMesta": "4-0000000",
                    "gsrn": "100000000000000000",
                },
                "merilneTocke": [{"gsrn": "200000000000000000", "vrsta": "OMTO"}],
            },
        )
        out = await resolve_gsrn_mt(client, "4-0000000")
    assert out == "200000000000000000"


@pytest.mark.asyncio
async def test_resolve_gsrn_mt_raises_when_no_merilne_tocke() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        router.get("/merilno-mesto/4-0000000").respond(
            200,
            json={
                "identifikator": {
                    "enotniIdentifikatorMerilnegaMesta": "4-0000000",
                    "gsrn": "100000000000000000",
                },
                "merilneTocke": [],
            },
        )
        with pytest.raises(typer.BadParameter):
            await resolve_gsrn_mt(client, "4-0000000")


@pytest.mark.asyncio
async def test_resolve_gsrn_mm_propagates_api_errors() -> None:
    async with (
        respx.mock(base_url=_BASE) as router,
        MojElektroClient("tok", server=Server.TEST) as client,
    ):
        router.get("/merilno-mesto/missing").respond(404, json={"opisNapake": "no"})
        with pytest.raises(NotFoundError):
            await resolve_gsrn_mm(client, "missing")
