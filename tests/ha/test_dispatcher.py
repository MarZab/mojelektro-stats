from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from custom_components.mojelektro_stats.const import SINK_INFLUXDB, SINK_STATISTICS
from custom_components.mojelektro_stats.dispatcher import Dispatcher
from mojelektro_api import KNOWN_READING_TYPES, MeterReadings

_RT_A = KNOWN_READING_TYPES[0]
_RT_B = KNOWN_READING_TYPES[1]


def _raw_code(info: object) -> str:
    return info.code.value.removeprefix("ReadingType=")  # type: ignore[attr-defined]


def _readings(rt_code: str, n: int = 2) -> dict[str, object]:
    return {
        "readingType": rt_code,
        "intervalReadings": [
            {"timestamp": f"2026-06-0{i + 1}T00:00:00+00:00", "value": f"{i}.0"} for i in range(n)
        ],
    }


@pytest.mark.asyncio
async def test_routes_each_block_to_every_chosen_sink() -> None:
    stats = AsyncMock()
    influx = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats, SINK_INFLUXDB: influx})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings(_raw_code(_RT_A))],
    }
    await dispatcher.dispatch("GSRN", payload, {_RT_A.name: [SINK_STATISTICS, SINK_INFLUXDB]})
    stats.write.assert_awaited_once()
    influx.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_list_means_no_dispatch() -> None:
    stats = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings(_raw_code(_RT_A))],
    }
    await dispatcher.dispatch("GSRN", payload, {_RT_A.name: []})
    stats.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_reading_type_is_dropped() -> None:
    stats = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings("not-a-real-code")],
    }
    await dispatcher.dispatch("GSRN", payload, {_RT_A.name: [SINK_STATISTICS]})
    stats.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_sink_choice_skips_block() -> None:
    stats = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings(_raw_code(_RT_A))],
    }
    # User asked for InfluxDB but no InfluxDB sink registered — skip silently.
    await dispatcher.dispatch("GSRN", payload, {_RT_A.name: [SINK_INFLUXDB]})
    stats.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_blocks_each_route_independently() -> None:
    stats = AsyncMock()
    influx = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats, SINK_INFLUXDB: influx})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings(_raw_code(_RT_A)), _readings(_raw_code(_RT_B))],
    }
    routing = {
        _RT_A.name: [SINK_STATISTICS],
        _RT_B.name: [SINK_INFLUXDB],
    }
    await dispatcher.dispatch("GSRN", payload, routing)
    stats.write.assert_awaited_once()
    influx.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_window_is_forwarded_to_sinks() -> None:
    stats = AsyncMock()
    dispatcher = Dispatcher({SINK_STATISTICS: stats})
    payload: MeterReadings = {
        "usagePoint": "GSRN",
        "intervalBlocks": [_readings(_raw_code(_RT_A))],
    }
    window = (date(2026, 5, 1), date(2026, 6, 1))
    await dispatcher.dispatch(
        "GSRN",
        payload,
        {_RT_A.name: [SINK_STATISTICS]},
        replace_window=window,
    )
    stats.write.assert_awaited_once()
    assert stats.write.await_args.kwargs["replace_window"] == window
