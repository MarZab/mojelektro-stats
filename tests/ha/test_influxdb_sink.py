from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from custom_components.mojelektro_stats.const import INFLUXDB_V1, INFLUXDB_V2
from custom_components.mojelektro_stats.sinks.influxdb import (
    InfluxDBAuthError,
    InfluxDBConnectionError,
    InfluxDBDatabaseNotFound,
    InfluxDBError,
    InfluxDBSink,
    _parse_flux_count_csv,
    probe_influxdb_connection,
)
from mojelektro_api import BY_NAME

_SHOW_DATABASES = {
    "results": [
        {
            "series": [
                {
                    "name": "databases",
                    "columns": ["name"],
                    "values": [["_internal"], ["homeassistant"]],
                }
            ]
        }
    ]
}

_COUNT_CSV = """# datatype,string,long,dateTime:RFC3339,dateTime:RFC3339,long
,result,table,_start,_stop,_value
,_result,0,1970-01-01T00:00:00Z,2026-06-01T00:00:00Z,42
"""


def _sink(http: httpx.AsyncClient, api_version: str = INFLUXDB_V2) -> InfluxDBSink:
    return InfluxDBSink(
        http,
        url="http://influx:8086",
        org="home",
        bucket="elektro",
        token="dev",
        api_version=api_version,
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


@pytest.mark.asyncio
@respx.mock
async def test_v1_replace_window_skips_delete_entirely() -> None:
    # InfluxDB 1.x has no predicate-delete API, so a v1 sink must not even
    # attempt the delete — it writes as an upsert instead.
    delete_route = respx.post("http://influx:8086/api/v2/delete").respond(204)
    write_route = respx.post("http://influx:8086/api/v2/write").respond(204)
    info = BY_NAME["A_PLUS_15MIN"]
    window = (date(2026, 6, 1), date(2026, 6, 2))
    async with httpx.AsyncClient() as http:
        await _sink(http, api_version=INFLUXDB_V1).write(
            "4-1234567",
            info,
            [{"timestamp": "2026-06-01T00:00:00+00:00", "value": "0.123"}],
            replace_window=window,
        )

    assert delete_route.call_count == 0
    assert write_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_v2_replace_window_tolerates_missing_delete_endpoint() -> None:
    # Defense in depth: even a v2 server that 404s on delete must not abort the
    # write.
    delete_route = respx.post("http://influx:8086/api/v2/delete").respond(404)
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


@pytest.mark.asyncio
@respx.mock
async def test_v1_probe_passes_when_database_exists() -> None:
    db_route = respx.get("http://influx:8086/query").respond(200, json=_SHOW_DATABASES)
    respx.post("http://influx:8086/api/v2/query").respond(200, text=_COUNT_CSV)
    async with httpx.AsyncClient() as http:
        count = await probe_influxdb_connection(
            http,
            url="http://influx:8086",
            org="-",
            bucket="homeassistant/autogen",
            token="homeassistant:secret",
            api_version=INFLUXDB_V1,
        )
    assert count == 42
    # Database check used Basic auth derived from the username:password token.
    assert db_route.calls[0].request.headers["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
@respx.mock
async def test_v1_probe_raises_when_database_missing() -> None:
    respx.get("http://influx:8086/query").respond(200, json=_SHOW_DATABASES)
    write_or_query = respx.post("http://influx:8086/api/v2/query").respond(200, text=_COUNT_CSV)
    async with httpx.AsyncClient() as http:
        with pytest.raises(InfluxDBDatabaseNotFound):
            await probe_influxdb_connection(
                http,
                url="http://influx:8086",
                org="-",
                bucket="missing_db/autogen",
                token="homeassistant:secret",
                api_version=INFLUXDB_V1,
            )
    # Existence check fails fast — the point-count query is never issued.
    assert write_or_query.call_count == 0
