from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.mojelektro.const import (
    CONF_IDENTIFIKATOR,
    CONF_ROUTING,
    SINK_STATISTICS,
)
from custom_components.mojelektro.coordinator import MojElektroDataUpdateCoordinator
from custom_components.mojelektro.dispatcher import Dispatcher
from mojelektro import KNOWN_READING_TYPES, AuthError, NotFoundError, TransportError

_RT = KNOWN_READING_TYPES[0]
_EMPTY_PAYLOAD = {"usagePoint": "GSRN1", "intervalBlocks": []}


def _coord(
    hass: HomeAssistant,
    client: AsyncMock,
    *,
    usage_points: list[dict[str, object]] | None = None,
    backfill_days: int = 90,
    sinks: dict[str, object] | None = None,
) -> MojElektroDataUpdateCoordinator:
    return MojElektroDataUpdateCoordinator(
        hass,
        client=client,
        usage_points=usage_points
        or [
            {
                CONF_IDENTIFIKATOR: "GSRN1",
                CONF_ROUTING: {_RT.name: [SINK_STATISTICS]},
            }
        ],
        dispatcher=Dispatcher(sinks or {SINK_STATISTICS: AsyncMock()}),
        backfill_days=backfill_days,
    )


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_advances_last_synced_end_on_success(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(return_value=_EMPTY_PAYLOAD)
    coord = _coord(hass, client)
    await coord._async_update_data()
    assert coord.last_synced_end["GSRN1"] == date(2026, 6, 7)


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_first_sync_starts_backfill_days_before_cutoff(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(return_value=_EMPTY_PAYLOAD)
    coord = _coord(hass, client, backfill_days=10)
    await coord._async_update_data()
    args, _ = client.get_meter_readings.call_args
    assert args[0] == "GSRN1"
    assert args[1] == date(2026, 5, 28)  # cutoff_date (06-07) minus 10 days
    assert args[2] == date(2026, 6, 7)


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_transport_error_does_not_advance_and_raises_update_failed(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(side_effect=TransportError("boom"))
    coord = _coord(hass, client)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert "GSRN1" not in coord.last_synced_end


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_auth_error_raises_config_entry_auth_failed(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(side_effect=AuthError("nope"))
    coord = _coord(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
    assert "GSRN1" not in coord.last_synced_end


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_not_found_warning_skips_point_without_raising(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(side_effect=NotFoundError("missing"))
    coord = _coord(hass, client)
    await coord._async_update_data()  # no raise
    assert "GSRN1" not in coord.last_synced_end


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_per_point_isolation_one_fails_one_succeeds(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()

    async def side(usage_point: str, *_args: object, **_kwargs: object) -> dict[str, object]:
        if usage_point == "GSRN_BAD":
            raise TransportError("bad")
        return {"usagePoint": usage_point, "intervalBlocks": []}

    client.get_meter_readings = AsyncMock(side_effect=side)
    coord = _coord(
        hass,
        client,
        usage_points=[
            {
                CONF_IDENTIFIKATOR: "GSRN_OK",
                CONF_ROUTING: {_RT.name: [SINK_STATISTICS]},
            },
            {
                CONF_IDENTIFIKATOR: "GSRN_BAD",
                CONF_ROUTING: {_RT.name: [SINK_STATISTICS]},
            },
        ],
    )
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.last_synced_end == {"GSRN_OK": date(2026, 6, 7)}


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_90_day_backfill_chunks_into_three_calls(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    """API caps a single request at 35 days; 90 → 35+35+20."""
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(return_value=_EMPTY_PAYLOAD)
    coord = _coord(hass, client, backfill_days=90)
    await coord._async_update_data()
    assert client.get_meter_readings.await_count == 3
    starts = [c.args[1] for c in client.get_meter_readings.await_args_list]
    ends = [c.args[2] for c in client.get_meter_readings.await_args_list]
    assert starts == [date(2026, 3, 9), date(2026, 4, 13), date(2026, 5, 18)]
    assert ends == [date(2026, 4, 13), date(2026, 5, 18), date(2026, 6, 7)]
    assert coord.last_synced_end["GSRN1"] == date(2026, 6, 7)


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_chunk_failure_preserves_partial_progress(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    """Second chunk fails → last_synced_end carries the first chunk's end forward."""
    from mojelektro import TransportError as _TE

    client = AsyncMock()
    calls: list[date] = []

    async def side(
        usage_point: str, start: date, end: date, **_kwargs: object
    ) -> dict[str, object]:
        calls.append(end)
        if len(calls) == 2:
            raise _TE("boom")
        return {"usagePoint": usage_point, "intervalBlocks": []}

    client.get_meter_readings = AsyncMock(side_effect=side)
    coord = _coord(hass, client, backfill_days=90)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    # First chunk succeeded → progress survives.
    assert coord.last_synced_end["GSRN1"] == date(2026, 4, 13)


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_no_routed_options_advances_without_fetch(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    """All measurements set to skip → coordinator advances without calling the API."""
    client = AsyncMock()
    client.get_meter_readings = AsyncMock()
    coord = _coord(
        hass,
        client,
        usage_points=[
            {
                CONF_IDENTIFIKATOR: "GSRN1",
                CONF_ROUTING: {_RT.name: []},
            }
        ],
    )
    await coord._async_update_data()
    client.get_meter_readings.assert_not_awaited()
    assert coord.last_synced_end["GSRN1"] == date(2026, 6, 7)


@pytest.mark.ha
@freeze_time("2026-06-07T08:00:00+00:00")
async def test_async_backfill_from_passes_replace_window_per_chunk(
    recorder_mock: object, hass: HomeAssistant
) -> None:
    client = AsyncMock()
    client.get_meter_readings = AsyncMock(return_value=_EMPTY_PAYLOAD)
    dispatcher = AsyncMock()
    coord = MojElektroDataUpdateCoordinator(
        hass,
        client=client,
        usage_points=[
            {
                CONF_IDENTIFIKATOR: "GSRN1",
                CONF_ROUTING: {_RT.name: [SINK_STATISTICS]},
            }
        ],
        dispatcher=dispatcher,
    )
    start = date(2026, 3, 1)
    requests = await coord.async_backfill_from(start)
    assert requests == 3
    assert dispatcher.dispatch.await_count == 3
    windows = [
        call.kwargs["replace_window"] for call in dispatcher.dispatch.await_args_list
    ]
    assert windows == [
        (date(2026, 3, 1), date(2026, 4, 5)),
        (date(2026, 4, 5), date(2026, 5, 10)),
        (date(2026, 5, 10), date(2026, 6, 7)),
    ]
