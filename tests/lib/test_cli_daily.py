from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx
import typer
from typer.testing import CliRunner

from cli import app
from cli._daily import (
    LOCAL_TZ,
    chunk_window,
    closing_day,
    fetch_range,
    register_by_day,
    sum_by_day,
    usage_by_day,
)
from cli._format import OutputFormat
from cli.daily import (
    DAILY_TYPES_ENVVAR,
    DEFAULT_DAILY_TYPES,
    compute_daily,
    render_daily,
    resolve_daily_types,
    resolve_days,
)
from mojelektro_api import Server
from mojelektro_api.models import IntervalBlock, MeterReadings
from mojelektro_api.reading_types import BY_NAME

_GSRN = "100000000000000000"
A_PLUS_T0 = BY_NAME["A_PLUS_T0_DAILY"]
A_PLUS_15 = BY_NAME["A_PLUS_15MIN"]


def _block(name: str, readings: list[tuple[str, str]]) -> IntervalBlock:
    raw = BY_NAME[name].code.value.removeprefix("ReadingType=")
    return {
        "readingType": raw,
        "intervalReadings": [{"timestamp": ts, "value": v} for ts, v in readings],
    }


def _payload(*blocks: IntervalBlock) -> MeterReadings:
    return {"usagePoint": _GSRN, "intervalBlocks": list(blocks)}


# --- closing_day -----------------------------------------------------------


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        # Daily register at local midnight closes the previous day.
        ("2026-10-25T00:00:00+02:00", date(2026, 10, 24)),
        # 15-minute interval ending at 00:15 belongs to the same day.
        ("2026-10-25T00:15:00+02:00", date(2026, 10, 25)),
        # Same instant as local midnight, but stamped in UTC.
        ("2026-10-24T22:00:00+00:00", date(2026, 10, 24)),
        # DST spring forward (CET -> CEST on Mar 29, 23 h day).
        ("2026-03-30T00:00:00+02:00", date(2026, 3, 29)),
        # DST fall back (CEST -> CET on Oct 25, 25 h day).
        ("2026-10-26T00:00:00+01:00", date(2026, 10, 25)),
        # Naive timestamps are treated as local time.
        ("2026-06-02T00:00:00", date(2026, 6, 1)),
    ],
)
def test_closing_day(timestamp: str, expected: date) -> None:
    assert closing_day(timestamp) == expected


def test_closing_day_rejects_garbage() -> None:
    assert closing_day("not-a-date") is None


# --- register / usage ------------------------------------------------------


def test_usage_is_difference_of_consecutive_closing_readings() -> None:
    payload = _payload(
        _block(
            "A_PLUS_T0_DAILY",
            [
                ("2026-10-24T00:00:00+02:00", "1000.0"),  # closes Oct 23
                ("2026-10-25T00:00:00+02:00", "1045.4"),  # closes Oct 24
                ("2026-10-26T00:00:00+01:00", "1045.6"),  # closes Oct 25 (DST day)
            ],
        )
    )
    registers = register_by_day([payload], A_PLUS_T0)
    usage = usage_by_day(registers, [date(2026, 10, 24), date(2026, 10, 25)])
    assert usage == {date(2026, 10, 24): Decimal("45.4"), date(2026, 10, 25): Decimal("0.2")}


def test_usage_is_none_when_a_reading_is_missing() -> None:
    registers = {date(2026, 10, 24): Decimal(10)}
    usage = usage_by_day(registers, [date(2026, 10, 24), date(2026, 10, 25)])
    assert usage == {date(2026, 10, 24): None, date(2026, 10, 25): None}


def test_overlapping_chunks_are_deduplicated() -> None:
    reading = ("2026-10-25T00:00:00+02:00", "5")
    a = _payload(_block("A_PLUS_15MIN", [reading]))
    b = _payload(_block("A_PLUS_15MIN", [reading]))
    assert sum_by_day([a, b], A_PLUS_15) == {date(2026, 10, 24): Decimal(5)}


def test_fifteen_minute_sum_covers_a_25_hour_dst_day() -> None:
    # Intervals ending 00:15 Oct 25 .. 00:00 Oct 26 local: 25 h = 100 slots.
    start = datetime(2026, 10, 24, 22, 15, tzinfo=UTC)
    stamps = [
        (start + timedelta(minutes=15 * i)).astimezone(LOCAL_TZ).isoformat() for i in range(100)
    ]
    payload = _payload(_block("A_PLUS_15MIN", [(ts, "1") for ts in stamps]))
    assert sum_by_day([payload], A_PLUS_15) == {date(2026, 10, 25): Decimal(100)}


# --- fetch windows ---------------------------------------------------------


def test_fetch_range_pads_one_day_each_side() -> None:
    assert fetch_range(date(2026, 10, 23), date(2026, 10, 25)) == (
        date(2026, 10, 22),
        date(2026, 10, 27),
    )


def test_chunk_window_respects_api_cap() -> None:
    chunks = chunk_window(date(2026, 1, 1), date(2026, 3, 1))
    assert chunks == [
        (date(2026, 1, 1), date(2026, 2, 5)),
        (date(2026, 2, 5), date(2026, 3, 1)),
    ]


# --- option resolution -----------------------------------------------------


def test_default_types() -> None:
    assert [t.name for t in resolve_daily_types(None, None)] == list(DEFAULT_DAILY_TYPES)


def test_env_types_accept_commas_and_spaces() -> None:
    types = resolve_daily_types(None, "A_PLUS_T0_DAILY, A_MINUS_T0_DAILY  R_PLUS_T0_DAILY")
    assert [t.name for t in types] == ["A_PLUS_T0_DAILY", "A_MINUS_T0_DAILY", "R_PLUS_T0_DAILY"]


def test_explicit_types_beat_env() -> None:
    types = resolve_daily_types(["A_MINUS_T0_DAILY"], "A_PLUS_T0_DAILY")
    assert [t.name for t in types] == ["A_MINUS_T0_DAILY"]


@pytest.mark.parametrize("name", ["A_PLUS_15MIN", "NOPE"])
def test_rejects_non_register_types(name: str) -> None:
    with pytest.raises(typer.BadParameter, match="not a daily register type"):
        resolve_daily_types([name], None)


def test_default_days_end_yesterday() -> None:
    assert resolve_days(None, None, 7, date(2026, 11, 15)) == (
        date(2026, 11, 8),
        date(2026, 11, 14),
    )


def test_start_only_counts_forward() -> None:
    assert resolve_days(date(2026, 10, 1), None, 3, date(2026, 11, 15)) == (
        date(2026, 10, 1),
        date(2026, 10, 3),
    )


def test_start_after_end_is_rejected() -> None:
    with pytest.raises(typer.BadParameter):
        resolve_days(date(2026, 10, 5), date(2026, 10, 1), 7, date(2026, 11, 15))


def test_days_must_be_positive() -> None:
    with pytest.raises(typer.BadParameter):
        resolve_days(None, None, 0, date(2026, 11, 15))


# --- rendering -------------------------------------------------------------


def test_table_has_total_blank_missing_and_negative_marker() -> None:
    days = [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]
    labels = ["A+_T0"]
    rows: list[dict[str, Decimal | None]] = [
        {"A+_T0": Decimal("45.4")},
        {"A+_T0": None},
        {"A+_T0": Decimal("-1.0")},
    ]
    out = render_daily(labels, days, rows, OutputFormat.TABLE)
    lines = out.splitlines()
    assert lines[0].split() == ["date", "A+_T0"]
    assert lines[2].split() == ["2026-10-24", "45.4"]
    assert lines[3].split() == ["2026-10-25"]
    assert lines[4].split() == ["2026-10-26", "-1.0", "!"]
    assert lines[6].split() == ["total", "44.4"]
    assert "register went backwards" in lines[-1]


def test_json_uses_numbers_and_null() -> None:
    days = [date(2026, 10, 24), date(2026, 10, 25)]
    rows: list[dict[str, Decimal | None]] = [{"A+_T0": Decimal("45.4")}, {"A+_T0": None}]
    out = json.loads(render_daily(["A+_T0"], days, rows, OutputFormat.JSON))
    assert out == [
        {"date": "2026-10-24", "A+_T0": 45.4},
        {"date": "2026-10-25", "A+_T0": None},
    ]


def test_check_adds_sum_and_diff_columns() -> None:
    days = [date(2026, 10, 24)]
    payload = _payload(
        _block(
            "A_PLUS_T0_DAILY",
            [("2026-10-24T00:00:00+02:00", "100"), ("2026-10-25T00:00:00+02:00", "103")],
        ),
        _block(
            "A_PLUS_15MIN",
            [("2026-10-24T12:00:00+02:00", "1"), ("2026-10-24T13:00:00+02:00", "1.5")],
        ),
    )
    labels, rows = compute_daily([payload], [A_PLUS_T0], days, check=True)
    assert labels == ["A+_T0", "15min", "diff"]
    assert rows == [{"A+_T0": Decimal(3), "15min": Decimal("2.5"), "diff": Decimal("0.5")}]


# --- end to end ------------------------------------------------------------


def _register_response() -> MeterReadings:
    return _payload(
        _block(
            "A_PLUS_T0_DAILY",
            [
                ("2026-10-23T00:00:00+02:00", "990.0"),
                ("2026-10-24T00:00:00+02:00", "1000.0"),
                ("2026-10-25T00:00:00+02:00", "1045.4"),
                ("2026-10-26T00:00:00+01:00", "1045.6"),
            ],
        ),
        _block(
            "A_MINUS_T0_DAILY",
            [
                ("2026-10-24T00:00:00+02:00", "5.0"),
                ("2026-10-25T00:00:00+02:00", "5.0"),
                ("2026-10-26T00:00:00+01:00", "6.5"),
            ],
        ),
    )


def test_daily_command_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DAILY_TYPES_ENVVAR, "A_PLUS_T0_DAILY,A_MINUS_T0_DAILY")
    with respx.mock(base_url=Server.TEST.base_url) as router:
        route = router.get("/meter-readings").respond(200, json=dict(_register_response()))
        result = CliRunner().invoke(
            app,
            [
                *("--token", "t", "--server", "test", "-f", "json"),
                *("daily", _GSRN, "--start", "2026-10-23", "--end", "2026-10-25"),
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert route.call_count == 1
    params = httpx.QueryParams(route.calls[0].request.url.query)
    assert params["startTime"] == "2026-10-22"
    assert params["endTime"] == "2026-10-27"
    assert params.get_list("option") == [
        A_PLUS_T0.code.value,
        BY_NAME["A_MINUS_T0_DAILY"].code.value,
    ]
    assert json.loads(result.stdout) == [
        {"date": "2026-10-23", "A+_T0": 10.0, "A-_T0": None},
        {"date": "2026-10-24", "A+_T0": 45.4, "A-_T0": 0.0},
        {"date": "2026-10-25", "A+_T0": 0.2, "A-_T0": 1.5},
    ]


def test_daily_command_chunks_long_ranges() -> None:
    with respx.mock(base_url=Server.TEST.base_url) as router:
        route = router.get("/meter-readings").respond(200, json=dict(_register_response()))
        result = CliRunner().invoke(
            app,
            [
                *("--token", "t", "--server", "test"),
                *("daily", _GSRN, "-t", "A_PLUS_T0_DAILY", "--start", "2026-09-01"),
                *("--end", "2026-10-25"),
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert route.call_count == 2
    assert "2026-10-24  45.4" in result.stdout
