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
from cli._daily import LOCAL_TZ, closing_hour
from cli._format import OutputFormat
from cli.hourly import (
    DEFAULT_HOURLY_TYPES,
    HOURLY_TYPES_ENVVAR,
    compute_hourly,
    hours_of,
    render_hourly,
    resolve_hourly_types,
)
from mojelektro_api import Server
from mojelektro_api.models import IntervalBlock, MeterReadings
from mojelektro_api.reading_types import BY_NAME

_GSRN = "100000000000000000"
A_PLUS_15 = BY_NAME["A_PLUS_15MIN"]


def _block(name: str, readings: list[tuple[str, str]]) -> IntervalBlock:
    raw = BY_NAME[name].code.value.removeprefix("ReadingType=")
    return {
        "readingType": raw,
        "intervalReadings": [{"timestamp": ts, "value": v} for ts, v in readings],
    }


def _payload(*blocks: IntervalBlock) -> MeterReadings:
    return {"usagePoint": _GSRN, "intervalBlocks": list(blocks)}


def _quarter_hours(day: date, value: str) -> list[tuple[str, str]]:
    """Every 15-minute interval of a local day, stamped at its end."""
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ).astimezone(UTC)
    end_local = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL_TZ)
    slots = int((end_local.astimezone(UTC) - start) / timedelta(minutes=15))
    return [
        ((start + timedelta(minutes=15 * (i + 1))).astimezone(LOCAL_TZ).isoformat(), value)
        for i in range(slots)
    ]


# --- hour attribution ------------------------------------------------------


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-06-01T00:15:00+02:00", "2026-06-01T00:00:00+02:00"),
        ("2026-06-01T01:00:00+02:00", "2026-06-01T00:00:00+02:00"),
        # The repeated 02:00 hour on the autumn DST day stays two hours.
        ("2026-10-25T02:15:00+02:00", "2026-10-25T02:00:00+02:00"),
        ("2026-10-25T02:15:00+01:00", "2026-10-25T02:00:00+01:00"),
    ],
)
def test_closing_hour(timestamp: str, expected: str) -> None:
    hour = closing_hour(timestamp)
    assert hour is not None
    assert hour.tzinfo is UTC
    assert hour.astimezone(LOCAL_TZ).isoformat() == expected


@pytest.mark.parametrize(
    ("day", "count"),
    [(date(2026, 6, 1), 24), (date(2026, 3, 29), 23), (date(2026, 10, 25), 25)],
)
def test_hours_of_follows_dst(day: date, count: int) -> None:
    hours = hours_of(day)
    assert len(hours) == count
    assert hours[0].astimezone(LOCAL_TZ).hour == 0
    assert len(set(hours)) == count


# --- type resolution -------------------------------------------------------


def test_default_types() -> None:
    assert [t.name for t in resolve_hourly_types(None, None)] == list(DEFAULT_HOURLY_TYPES)


def test_env_types() -> None:
    types = resolve_hourly_types(None, "A_PLUS_15MIN R_PLUS_15MIN")
    assert [t.name for t in types] == ["A_PLUS_15MIN", "R_PLUS_15MIN"]


@pytest.mark.parametrize("name", ["P_PLUS_15MIN", "A_PLUS_T0_DAILY", "NOPE"])
def test_rejects_non_energy_interval_types(name: str) -> None:
    with pytest.raises(typer.BadParameter, match="not a 15-minute energy type"):
        resolve_hourly_types([name], None)


# --- compute + render ------------------------------------------------------


def _dst_day_payload(register_close: str) -> MeterReadings:
    day = date(2026, 10, 25)  # 25 hours, 100 quarter-hours
    return _payload(
        _block("A_PLUS_15MIN", _quarter_hours(day, "0.1")),
        _block(
            "A_PLUS_T0_DAILY",
            [
                ("2026-10-25T00:00:00+02:00", "100.0"),  # closes Oct 24
                ("2026-10-26T00:00:00+01:00", register_close),  # closes Oct 25
            ],
        ),
    )


def test_hours_add_up_to_register_on_a_25_hour_day() -> None:
    report = compute_hourly([_dst_day_payload("110.0")], [A_PLUS_15], [date(2026, 10, 25)])
    assert len(report.hours) == 25
    assert all(values["A+"] == Decimal("0.4") for _, values in report.hours)
    summary = report.days[0]
    assert summary.hours["A+"] == Decimal("10.0")
    assert summary.register["A+"] == Decimal("10.0")
    assert summary.diff["A+"] == Decimal(0)
    out = render_hourly(report, OutputFormat.TABLE)
    assert "differ" not in out
    assert "2026-10-25 02:00+0200" in out
    assert "2026-10-25 02:00+0100" in out


def test_mismatch_is_flagged() -> None:
    report = compute_hourly([_dst_day_payload("111.0")], [A_PLUS_15], [date(2026, 10, 25)])
    assert report.days[0].diff["A+"] == Decimal("1.0")
    out = render_hourly(report, OutputFormat.TABLE)
    assert out.splitlines()[-1] == "hours and register differ on: 2026-10-25 A+"


def test_missing_hours_stay_blank() -> None:
    payload = _payload(_block("A_PLUS_15MIN", [("2026-06-01T00:15:00+02:00", "0.5")]))
    report = compute_hourly([payload], [A_PLUS_15], [date(2026, 6, 1)])
    assert report.hours[0][1]["A+"] == Decimal("0.5")
    assert report.hours[1][1]["A+"] is None
    assert report.days[0].register["A+"] is None
    assert report.days[0].diff["A+"] is None


# --- end to end ------------------------------------------------------------


def test_hourly_command_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HOURLY_TYPES_ENVVAR, "A_PLUS_15MIN")
    with respx.mock(base_url=Server.TEST.base_url) as router:
        route = router.get("/meter-readings").respond(200, json=dict(_dst_day_payload("110.0")))
        result = CliRunner().invoke(
            app,
            [
                *("--token", "t", "--server", "test", "-f", "json"),
                *("hourly", _GSRN, "--start", "2026-10-25"),
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    params = httpx.QueryParams(route.calls[0].request.url.query)
    assert params.get_list("option") == [
        A_PLUS_15.code.value,
        BY_NAME["A_PLUS_T0_DAILY"].code.value,
    ]
    out = json.loads(result.stdout)
    assert len(out["hours"]) == 25
    assert out["days"] == [
        {"date": "2026-10-25", "A+": {"hours": 10.0, "register": 10.0, "diff": 0.0}}
    ]
