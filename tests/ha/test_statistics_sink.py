from __future__ import annotations

import re
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.mojelektro_stats.sinks.statistics import StatisticsSink
from mojelektro_api import BY_NAME, KNOWN_READING_TYPES

# Mirrors homeassistant.components.recorder.statistics.VALID_STATISTIC_ID
_VALID_STATISTIC_ID = re.compile(r"^(?!.+__)(?!_)[\da-z_]+(?<!_):(?!_)[\da-z_]+(?<!_)$")


@pytest.mark.ha
@pytest.mark.parametrize("info", KNOWN_READING_TYPES)
async def test_statistic_id_matches_ha_regex(
    recorder_mock: object, hass: object, info: object
) -> None:
    """Every catalog reading type must produce a statistic_id HA accepts.

    HA's `VALID_STATISTIC_ID` regex bans dashes — we use dash-friendly slugs
    for entity unique_ids but flatten to underscores for statistic_ids.
    """
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured: list[str] = []

    def fake_import(_hass: object, metadata: dict, _data: list) -> None:
        captured.append(metadata["statistic_id"])

    with patch(
        "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
        side_effect=fake_import,
    ):
        await sink.write(
            "4-1234567",
            info,  # type: ignore[arg-type]
            [{"timestamp": "2026-06-01T00:00:00+00:00", "value": "1.0"}],
        )
    assert len(captured) == 1
    statistic_id = captured[0]
    assert _VALID_STATISTIC_ID.match(statistic_id), statistic_id
    # Domain half must equal the source (HA also asserts this).
    domain, _ = statistic_id.split(":", 1)
    assert domain == "mojelektro_stats"


def _four_quarter_readings(hour: datetime, values: list[float]) -> list[dict[str, str]]:
    """Four 15-minute readings within a single hour."""
    return [
        {
            "timestamp": (hour.replace(minute=15 * i)).isoformat(),
            "value": str(v),
        }
        for i, v in enumerate(values)
    ]


@pytest.mark.ha
async def test_energy_aggregates_4_quarter_hours_into_hourly_sum(
    recorder_mock: object, hass: object
) -> None:
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured_data: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured_data.append(list(data))

    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    h1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)
    readings = _four_quarter_readings(h0, [0.1, 0.2, 0.3, 0.4]) + _four_quarter_readings(
        h1, [1.0, 1.0, 1.0, 1.0]
    )
    info = BY_NAME["A_PLUS_15MIN"]
    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(0.0, None)),
    ):
        await sink.write("4-1234567", info, readings)  # type: ignore[arg-type]

    data = captured_data[0]
    assert len(data) == 2
    assert data[0]["start"] == h0
    # Hourly sum 0.1+0.2+0.3+0.4 = 1.0; cumulative also = 1.0 (first hour).
    assert data[0]["sum"] == pytest.approx(1.0)
    assert data[1]["start"] == h1
    # Hour 2 contributes 4.0; cumulative = 1.0 + 4.0 = 5.0.
    assert data[1]["sum"] == pytest.approx(5.0)
    # No mean field on energy.
    assert "mean" not in data[0]


@pytest.mark.ha
async def test_power_aggregates_to_hourly_mean_min_max(
    recorder_mock: object, hass: object
) -> None:
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured_data: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured_data.append(list(data))

    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    readings = _four_quarter_readings(h0, [1.0, 2.0, 3.0, 4.0])
    info = BY_NAME["P_PLUS_15MIN"]
    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(0.0, None)),
    ):
        await sink.write("4-1234567", info, readings)  # type: ignore[arg-type]

    data = captured_data[0]
    assert len(data) == 1
    # Power is instantaneous: report the hour's distribution, not a running sum.
    assert data[0]["mean"] == pytest.approx(2.5)
    assert data[0]["min"] == pytest.approx(1.0)
    assert data[0]["max"] == pytest.approx(4.0)
    assert "sum" not in data[0]


@pytest.mark.ha
async def test_energy_anchors_on_existing_sum_so_chunk_boundary_doesnt_dip(
    recorder_mock: object, hass: object
) -> None:
    """Regression: a chunked 90-day backfill used to restart cumulative at 0
    on every chunk, so HA saw the chunk boundary as a negative-consumption
    meter reset. Now we anchor on the last existing sum."""
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured_data: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured_data.append(list(data))

    info = BY_NAME["A_PLUS_15MIN"]
    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    readings = _four_quarter_readings(h0, [0.5, 0.5, 0.5, 0.5])  # hourly delta = 2.0

    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(100.0, None)),
    ):
        await sink.write("4-1234567", info, readings)  # type: ignore[arg-type]

    assert captured_data[0][0]["sum"] == pytest.approx(102.0)


@pytest.mark.ha
async def test_back_to_back_chunks_carry_cumulative_via_in_memory_cache(
    recorder_mock: object, hass: object
) -> None:
    """The recorder is async-queued, so chunk N+1 can't rely on the DB seeing
    chunk N's just-written sum. The in-memory tail cache covers the gap."""
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured.append(list(data))

    info = BY_NAME["A_PLUS_15MIN"]
    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    h1 = datetime(2026, 6, 2, 0, 0, tzinfo=UTC)
    chunk_a = _four_quarter_readings(h0, [0.5, 0.5, 0.5, 0.5])  # hourly=2.0
    chunk_b = _four_quarter_readings(h1, [0.5, 0.5, 0.5, 0.5])  # hourly=2.0

    # The DB lookup ALWAYS returns 0 — simulating the recorder race where
    # chunk A's write hasn't flushed before chunk B asks for the baseline.
    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(0.0, None)),
    ):
        await sink.write("4-1234567", info, chunk_a)  # type: ignore[arg-type]
        await sink.write("4-1234567", info, chunk_b)  # type: ignore[arg-type]

    # Chunk A: cumulative 0 -> 2.0
    assert captured[0][0]["sum"] == pytest.approx(2.0)
    # Chunk B: cumulative MUST continue from 2.0, NOT restart at 0.
    assert captured[1][0]["sum"] == pytest.approx(4.0)


@pytest.mark.ha
async def test_stanje_uses_value_directly_without_accumulation(
    recorder_mock: object, hass: object
) -> None:
    """STANJE (daily cumulative meter state) readings ARE the cumulative total
    — we shouldn't sum-accumulate them on top of themselves."""
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured_data: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured_data.append(list(data))

    info = BY_NAME["A_PLUS_T0_DAILY"]
    # Three daily reads, each carrying the meter's lifetime total at that day.
    readings = [
        {"timestamp": "2026-06-01T00:00:00+00:00", "value": "1000.0"},
        {"timestamp": "2026-06-02T00:00:00+00:00", "value": "1005.0"},
        {"timestamp": "2026-06-03T00:00:00+00:00", "value": "1010.0"},
    ]
    # _previous_sum_before would normally return some baseline but for STANJE
    # we don't use it — assert that explicitly by giving it a poison value.
    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(9999.0, None)),
    ):
        await sink.write("4-1234567", info, readings)  # type: ignore[arg-type]

    sums = [row["sum"] for row in captured_data[0]]
    assert sums == [pytest.approx(1000.0), pytest.approx(1005.0), pytest.approx(1010.0)]


@pytest.mark.ha
async def test_replace_window_deletes_existing_statistics_before_import(
    recorder_mock: object, hass: object
) -> None:
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    info = BY_NAME["A_PLUS_15MIN"]
    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    readings = _four_quarter_readings(h0, [0.5, 0.5, 0.5, 0.5])
    window = (date(2026, 6, 1), date(2026, 6, 2))
    delete_mock = AsyncMock()

    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
        ),
        patch.object(StatisticsSink, "_delete_statistics_in_window", delete_mock),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(0.0, None)),
    ):
        await sink.write(
            "4-1234567",
            info,  # type: ignore[arg-type]
            readings,
            replace_window=window,
        )

    delete_mock.assert_awaited_once()
    args = delete_mock.await_args.args
    assert args[0] == "mojelektro_stats:41234567_a_plus_15"
    assert args[1] == datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    assert args[2] == datetime(2026, 6, 2, 0, 0, tzinfo=UTC)


@pytest.mark.ha
async def test_overlapping_chunk_boundary_does_not_double_count(
    recorder_mock: object, hass: object
) -> None:
    """API fetch windows share their end/start date; chunk N+1 must not
    re-accumulate hours already folded into the tail baseline from chunk N."""
    sink = StatisticsSink(hass)  # type: ignore[arg-type]
    captured: list[list[dict]] = []

    def fake(_hass: object, _md: dict, data: list) -> None:
        captured.append(list(data))

    info = BY_NAME["A_PLUS_15MIN"]
    h0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    h1 = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)
    chunk_a = _four_quarter_readings(h0, [0.5, 0.5, 0.5, 0.5])  # hourly=2.0
    # Chunk B repeats the boundary hour and adds the next one.
    chunk_b = _four_quarter_readings(h0, [0.5, 0.5, 0.5, 0.5]) + _four_quarter_readings(
        h1, [0.5, 0.5, 0.5, 0.5]
    )

    with (
        patch(
            "custom_components.mojelektro_stats.sinks.statistics.async_add_external_statistics",
            side_effect=fake,
        ),
        patch.object(StatisticsSink, "_previous_sum_before", return_value=(0.0, None)),
    ):
        await sink.write("4-1234567", info, chunk_a)  # type: ignore[arg-type]
        await sink.write("4-1234567", info, chunk_b)  # type: ignore[arg-type]

    assert captured[0][0]["sum"] == pytest.approx(2.0)
    # Only hour 2 from chunk B should be written; hour 1 was already in the tail.
    assert len(captured[1]) == 1
    assert captured[1][0]["start"] == h1
    assert captured[1][0]["sum"] == pytest.approx(4.0)
