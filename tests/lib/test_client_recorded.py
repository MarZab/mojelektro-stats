"""Recorded happy-path tests against the production Moj Elektro API.

Cassettes live next to this file under ``cassettes/test_client_recorded/``
and are committed to the repo. The three real identifiers (identifikator,
gsrnMm, gsrnMt) and the API token are scrubbed at record time — see
conftest.py for the scrubbing rules.

Dates in the meter-readings test are hardcoded so the replay request URL
matches the recorded cassette. Re-record after changing them.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from mojelektro_api import MojElektroClient, Server


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_recorded_reading_types(mojelektro_token: str) -> None:
    """Hits /reading-type via raw httpx so we can refresh the catalog cassette.

    The lib's runtime client no longer exposes this endpoint (the catalog is
    hardcoded in `custom_components/mojelektro_stats/lib/mojelektro_api/reading_types.py`).
    `scripts/regen-reading-types.py` reads the cassette produced by this test;
    re-record (`--record-mode=once`) after the upstream catalog grows or the
    path-aware scrub changes, then run `make regen-reading-types`.
    """
    async with httpx.AsyncClient(
        base_url=Server.PRODUCTION.base_url,
        headers={"X-API-TOKEN": mojelektro_token, "Accept": "application/json"},
    ) as http:
        response = await http.get("/reading-type")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    for item in body:
        assert "readingType" in item
        assert "oznaka" in item


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_recorded_merilno_mesto(
    mojelektro_token: str,
    mojelektro_identifikator: str,
) -> None:
    async with MojElektroClient(mojelektro_token, server=Server.PRODUCTION) as client:
        out = await client.get_merilno_mesto(mojelektro_identifikator)
    assert out is not None
    assert isinstance(out, dict)


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_recorded_merilna_tocka(
    mojelektro_token: str,
    mojelektro_gsrn_mt: str,
) -> None:
    async with MojElektroClient(mojelektro_token, server=Server.PRODUCTION) as client:
        out = await client.get_merilna_tocka(mojelektro_gsrn_mt)
    assert out is not None
    assert isinstance(out, dict)


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_recorded_meter_readings_window(
    mojelektro_token: str,
    mojelektro_gsrn_mm: str,
) -> None:
    # Hardcoded so the replay URL matches the cassette. Re-record to change.
    # `options` is effectively required — the API returns HTTP 400 (empty
    # body) without at least one reading-type code. Using A+ 15-minute
    # received energy, which every meter has.
    start = date(2026, 5, 30)
    end = date(2026, 6, 6)
    options = ["ReadingType=32.0.2.4.1.2.12.0.0.0.0.0.0.0.0.3.72.0"]
    async with MojElektroClient(mojelektro_token, server=Server.PRODUCTION) as client:
        out = await client.get_meter_readings(mojelektro_gsrn_mm, start, end, options=options)
    blocks = out.get("intervalBlocks", [])
    assert blocks, "expected at least one interval block in the response"
    assert blocks[0].get("intervalReadings"), "expected readings in the first block"
