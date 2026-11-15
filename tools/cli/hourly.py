from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import typer
import yaml

from cli._daily import (
    LOCAL_TZ,
    days_between,
    register_by_day,
    sum_by_hour,
    usage_by_day,
)
from cli._env import USAGE_POINT_ENVVAR
from cli._format import OutputFormat, render_aligned_lines
from cli.daily import fetch_payloads, resolve_days
from mojelektro_api.models import MeterReadings
from mojelektro_api.reading_types import BY_NAME, ReadingTypeInfo

HOURLY_TYPES_ENVVAR = "MOJELEKTRO_HOURLY_TYPES"
DEFAULT_HOURLY_TYPES: tuple[str, ...] = ("A_PLUS_15MIN", "A_MINUS_15MIN")
# 15-minute energy (KOLICINA) type -> the daily register it should add up to.
REGISTER_FOR: dict[str, str] = {
    "A_PLUS_15MIN": "A_PLUS_T0_DAILY",
    "A_MINUS_15MIN": "A_MINUS_T0_DAILY",
    "R_PLUS_15MIN": "R_PLUS_T0_DAILY",
    "R_MINUS_15MIN": "R_MINUS_T0_DAILY",
}


def resolve_hourly_types(names: list[str] | None, env_value: str | None) -> list[ReadingTypeInfo]:
    """Pick 15-minute energy types: -t > MOJELEKTRO_HOURLY_TYPES > defaults.

    Power types (P/Q) are averages, not energy, so they can't be summed
    into hours or compared with a register and are rejected.
    """
    if names:
        chosen = list(names)
    elif env_value and env_value.strip():
        chosen = [n for n in re.split(r"[,\s]+", env_value.strip()) if n]
    else:
        chosen = list(DEFAULT_HOURLY_TYPES)

    infos: list[ReadingTypeInfo] = []
    for name in chosen:
        if name not in REGISTER_FOR:
            raise typer.BadParameter(
                f"{name!r} is not a 15-minute energy type. Valid: {', '.join(REGISTER_FOR)}",
                param_hint=f"--type / {HOURLY_TYPES_ENVVAR}",
            )
        info = BY_NAME[name]
        if info not in infos:
            infos.append(info)
    return infos


def hours_of(day: date) -> list[datetime]:
    """Every hour start of local ``day`` (23, 24 or 25 of them), in UTC to
    match `sum_by_hour` keys."""
    start = datetime.combine(day, time.min, tzinfo=LOCAL_TZ).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LOCAL_TZ).astimezone(UTC)
    count = int((end - start) / timedelta(hours=1))
    return [start + timedelta(hours=i) for i in range(count)]


@dataclass(frozen=True, slots=True)
class DaySummary:
    day: date
    hours: dict[str, Decimal | None]
    register: dict[str, Decimal | None]
    diff: dict[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class HourlyReport:
    labels: list[str]
    hours: list[tuple[datetime, dict[str, Decimal | None]]]
    days: list[DaySummary]


def compute_hourly(
    payloads: list[MeterReadings], types: list[ReadingTypeInfo], days: list[date]
) -> HourlyReport:
    labels = [info.oznaka for info in types]
    per_hour = {info.oznaka: sum_by_hour(payloads, info) for info in types}
    per_register = {
        info.oznaka: usage_by_day(register_by_day(payloads, BY_NAME[REGISTER_FOR[info.name]]), days)
        for info in types
    }

    hour_rows: list[tuple[datetime, dict[str, Decimal | None]]] = []
    summaries: list[DaySummary] = []
    for day in days:
        day_hours = hours_of(day)
        for hour in day_hours:
            hour_rows.append((hour, {label: per_hour[label].get(hour) for label in labels}))
        totals: dict[str, Decimal | None] = {}
        registers: dict[str, Decimal | None] = {}
        diffs: dict[str, Decimal | None] = {}
        for label in labels:
            present = [v for h in day_hours if (v := per_hour[label].get(h)) is not None]
            total = sum(present, Decimal(0)) if present else None
            register = per_register[label].get(day)
            totals[label] = total
            registers[label] = register
            diffs[label] = None if total is None or register is None else register - total
        summaries.append(DaySummary(day, totals, registers, diffs))
    return HourlyReport(labels, hour_rows, summaries)


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _cell(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def render_hourly(report: HourlyReport, fmt: OutputFormat) -> str:
    if fmt in (OutputFormat.JSON, OutputFormat.YAML):
        payload = {
            "hours": [
                {
                    "hour": hour.astimezone(LOCAL_TZ).isoformat(),
                    **{k: _num(v) for k, v in values.items()},
                }
                for hour, values in report.hours
            ],
            "days": [
                {
                    "date": s.day.isoformat(),
                    **{
                        label: {
                            "hours": _num(s.hours[label]),
                            "register": _num(s.register[label]),
                            "diff": _num(s.diff[label]),
                        }
                        for label in report.labels
                    },
                }
                for s in report.days
            ],
        }
        if fmt is OutputFormat.JSON:
            return json.dumps(payload, indent=2) + "\n"
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    rows: list[list[str]] = []
    for hour, values in report.hours:
        rows.append(
            [
                hour.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M%z"),
                *(_cell(values[lb]) for lb in report.labels),
            ]
        )
    for s in report.days:
        rows.append([f"{s.day.isoformat()} hours", *(_cell(s.hours[lb]) for lb in report.labels)])
        rows.append(
            [f"{s.day.isoformat()} register", *(_cell(s.register[lb]) for lb in report.labels)]
        )
        rows.append([f"{s.day.isoformat()} diff", *(_cell(s.diff[lb]) for lb in report.labels)])
    header, data = render_aligned_lines(["hour", *report.labels], rows)

    # Hour rows, then one summary block per day under a separator.
    n_hours = len(report.hours)
    lines = [*header, *data[:n_hours]]
    for i in range(len(report.days)):
        block = data[n_hours + 3 * i : n_hours + 3 * i + 3]
        lines.extend([header[1], *block])
    mismatched = [
        f"{s.day.isoformat()} {label}"
        for s in report.days
        for label in report.labels
        if (d := s.diff[label]) is not None and abs(d) > Decimal("0.01")
    ]
    if mismatched:
        lines.append("hours and register differ on: " + ", ".join(mismatched))
    return "\n".join(lines) + "\n"


def _hourly(
    ctx: typer.Context,
    usage_point: str = typer.Argument(
        ..., envvar=USAGE_POINT_ENVVAR, help="identifikator or gsrnMm."
    ),
    type_: list[str] = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "15-minute energy type (repeatable). Default: "
            f"${HOURLY_TYPES_ENVVAR} (comma-separated) or {', '.join(DEFAULT_HOURLY_TYPES)}."
        ),
    ),
    start: datetime | None = typer.Option(
        None, "--start", formats=["%Y-%m-%d"], help="First day (YYYY-MM-DD, inclusive)."
    ),
    end: datetime | None = typer.Option(
        None, "--end", formats=["%Y-%m-%d"], help="Last day (YYYY-MM-DD, inclusive)."
    ),
    days: int = typer.Option(1, "--days", help="Number of days, ending yesterday by default."),
) -> None:
    """Hourly usage from 15-minute readings, checked against the daily register."""
    types = resolve_hourly_types(type_, os.environ.get(HOURLY_TYPES_ENVVAR))
    today = datetime.now(LOCAL_TZ).date()
    first, last = resolve_days(
        start.date() if start else None, end.date() if end else None, days, today
    )
    options = [info.code.value for info in types]
    options += [BY_NAME[REGISTER_FOR[info.name]].code.value for info in types]

    payloads = asyncio.run(fetch_payloads(ctx, usage_point, options, first, last))
    report = compute_hourly(payloads, types, days_between(first, last))
    typer.echo(render_hourly(report, OutputFormat(ctx.obj["format"])), nl=False)


from cli import handle_errors  # noqa: E402

hourly_cmd = handle_errors(_hourly)
