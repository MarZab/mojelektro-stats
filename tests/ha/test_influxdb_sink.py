from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from custom_components.mojelektro.sinks.influxdb import (
    InfluxDBAuthError,
    InfluxDBConnectionError,
    InfluxDBError,
    InfluxDBSink,
    _parse_flux_count_csv,
    probe_influxdb_connection,
)
from mojelektro import BY_NAME

_COUNT_CSV = """# datatype,string,long,dateTime:RFC3339,dateTime:RFC3339,long
,result,table,_start,_stop,_value
,_result,0,1970-01-01T00:00:00Z,2026-06-01T00:00:00Z,42
"""


def _sink(http: httpx.AsyncClient) -> InfluxDBSink:
    return InfluxDBSink(
        http,
        url="http://influx:8086",
        org="home",
        bucket="elektro",
        token="dev",
    )


def test_parse_flux_count_csv() -> None:
    assert _parse_flux_count_csv(_COUNT_CSV) == 42
    assert _parse_flux_count_csv("") == 0


@pytest.mark.asyncio
@respx.mock
async def test_line_protocol_includes_unit_and_drops_oznaka() -> None:
    route = respx.post("http://influx:8086/api/v2/write").respond(204)
    info = BY_NAME["A_PLUS_15MIN"]
    async with httpx.AsyncClient() as http:
        await _sink(http).write(
            "4-1234567",
            info,
            [{"timestamp": "2026-06-01T00:00:00+00:00", "value": "0.123"}],
        )

    body = route.calls.last.request.content.decode()
    assert "usage_point=4-1234567" in body
    assert "reading_type=A_PLUS_15MIN" in body
    assert "unit=kWh" in body
    assert "oznaka" not in body


@pytest.mark.asyncio
@respx.mock
async def test_unit_tag_uses_kw_for_power_readings() -> None:
    respx.post("http://influx:8086/api/v2/write").respond(204)
    info = BY_NAME["P_PLUS_15MIN"]
    async with httpx.AsyncClient() as http:
        sink = _sink(http)
        await sink.write(
            "4-1234567",
            info,
            [{"timestamp": "2026-06-01T00:00:00+00:00", "value": "1.5"}],
        )
    body = respx.calls.last.request.content.decode()
    assert "unit=kW " in body or body.endswith("unit=kW")  # tag-set delimiter
    assert "reading_type=P_PLUS_15MIN" in body


@pytest.mark.asyncio
@respx.mock
async def test_connection_returns_existing_point_count() -> None:
    respx.post("http://influx:8086/api/v2/query").respond(200, text=_COUNT_CSV)
    async with httpx.AsyncClient() as http:
        count = await probe_influxdb_connection(
            http,
            url="http://influx:8086",
            org="home",
            bucket="elektro",
            token="dev",
        )
    assert count == 42


@pytest.mark.asyncio
@respx.mock
async def test_connection_auth_error() -> None:
    respx.post("http://influx:8086/api/v2/query").respond(401, text="unauthorized")
    async with httpx.AsyncClient() as http:
        with pytest.raises(InfluxDBAuthError):
            await probe_influxdb_connection(
                http,
                url="http://influx:8086",
                org="home",
                bucket="elektro",
                token="bad",
            )


@pytest.mark.asyncio
@respx.mock
async def test_connection_server_error() -> None:
    respx.post("http://influx:8086/api/v2/query").respond(500, text="boom")
    async with httpx.AsyncClient() as http:
        with pytest.raises(InfluxDBError):
            await probe_influxdb_connection(
                http,
                url="http://influx:8086",
                org="home",
                bucket="elektro",
                token="dev",
            )


@pytest.mark.asyncio
@respx.mock
async def test_connection_transport_error() -> None:
    respx.post("http://influx:8086/api/v2/query").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(InfluxDBConnectionError):
            await probe_influxdb_connection(
                http,
                url="http://influx:8086",
                org="home",
                bucket="elektro",
                token="dev",
            )


@pytest.mark.asyncio
@respx.mock
async def test_replace_window_deletes_before_write() -> None:
    delete_route = respx.post("http://influx:8086/api/v2/delete").respond(204)
    write_route = respx.post("http://influx:8086/api/v2/write").respond(204)
    info = BY_NAME["A_PLUS_15MIN"]
    window = (date(2026, 6, 1), date(2026, 6, 2))
    async with httpx.AsyncClient() as http:
        await _sink(http).write(
            "4-1234567",
            info,
            [{"timestamp": "2026-06-01T00:00:00+00:00", "value": "0.123"}],
            replace_window=window,
        )

    assert delete_route.call_count == 1
    assert write_route.call_count == 1
    delete_body = delete_route.calls[0].request.content.decode()
    assert '"start":"2026-06-01T00:00:00Z"' in delete_body
    assert '"stop":"2026-06-02T00:00:00Z"' in delete_body
    assert "4-1234567" in delete_body
    assert "A_PLUS_15MIN" in delete_body
    assert delete_route.calls[0].request.url.params["org"] == "home"
    assert delete_route.calls[0].request.url.params["bucket"] == "elektro"
